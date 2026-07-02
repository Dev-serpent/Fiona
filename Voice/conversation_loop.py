"""Full-duplex conversational voice loop for Fiona.

Orchestrates the complete pipeline:

    Wake word / PTT
         ↓
    ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ LISTENING│────→│PROCESSING│────→│ SPEAKING │────→│LISTENING │
    │ (VAD)   │     │ (STT+LLM)│     │ (TTS)    │     │ (VAD)    │
    └──────────┘     └──────────┘     └──────────┘     └──────────┘
         ↑                                                │
         └────────────── barge-in ────────────────────────┘

Usage::

    from Voice.conversation_loop import ConversationLoop

    loop = ConversationLoop()
    loop.on_tts_chunk = lambda chunk: websocket.send(chunk)
    loop.on_transcription = lambda text: print(f"User: {text}")
    loop.on_response = lambda text: print(f"Fiona: {text}")
    loop.on_state_change = lambda old, new: update_ui(old, new)

    # Feed audio from microphone
    loop.feed_audio(audio_bytes)

    # Start/stop
    loop.start()
    loop.stop()
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from Voice.turn_state import TurnConfig, TurnState, TurnStateMachine
from Voice.vad import VADConfig, VADEngine

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    """Configuration for the conversation loop.

    Attributes:
        vad: VAD configuration.
        turn: Turn-taking configuration.
        stt_model: Whisper model size ("tiny", "base", "small", "medium").
        stt_language: Language code for STT (None = auto-detect).
        llm_timeout: Max seconds to wait for LLM response.
        tts_enabled: If False, skip TTS (text-only mode for debugging).
    """

    vad: VADConfig = field(default_factory=VADConfig)
    turn: TurnConfig = field(default_factory=TurnConfig)
    stt_model: str = "tiny"
    stt_language: str | None = None
    llm_timeout: float = 30.0
    tts_enabled: bool = True


class ConversationLoop:
    """Full-duplex conversational voice loop.

    Thread-safe: ``feed_audio()`` may be called from any thread.
    """

    def __init__(self, config: LoopConfig | None = None, llm_callback: Callable[[str], str] | None = None) -> None:
        """Initialise the conversation loop.

        Args:
            config: Loop configuration (defaults used if None).
            llm_callback: Synchronous function that takes a user utterance
                string and returns a response string.  If None, the loop
                echoes the transcription.
        """
        self.config = config or LoopConfig()
        self._llm_callback = llm_callback or self._default_llm

        # Sub-components
        self.vad = VADEngine(config=self.config.vad)
        self.turn = TurnStateMachine(config=self.config.turn)
        self._tts: Any = None  # Lazy-imported StreamingTTS

        # State
        self._lock = threading.Lock()
        self._running = False
        self._audio_buffer: list[bytes] = []
        self._speech_active = False

        # Callbacks
        self.on_tts_chunk: Callable[[bytes], None] | None = None
        self.on_transcription: Callable[[str], None] | None = None
        self.on_response: Callable[[str], None] | None = None
        self.on_state_change: Callable[[TurnState, TurnState], None] | None = None
        self.on_error: Callable[[Exception], None] | None = None
        self.on_tts_started: Callable[[], None] | None = None
        self.on_tts_stopped: Callable[[], None] | None = None
        self.on_listening_started: Callable[[], None] | None = None
        self.on_listening_stopped: Callable[[], None] | None = None

        # Wire turn state machine callbacks
        self.turn.on_state_change = self._handle_state_change
        self.turn.on_speech_ended = self._handle_speech_ended
        self.turn.on_barge_in_triggered = self._handle_barge_in

    # -- Public API ---------------------------------------------------------

    @property
    def running(self) -> bool:
        """``True`` if the conversation loop is active."""
        return self._running

    @property
    def state(self) -> TurnState:
        """Current turn state."""
        return self.turn.state

    def start(self) -> None:
        """Start the conversation loop (begins listening)."""
        if self._running:
            return
        self._running = True
        self._audio_buffer.clear()
        self.vad.reset()
        self.turn.start_listening()
        logger.info("Conversation loop started")

    def stop(self) -> None:
        """Stop the conversation loop."""
        if not self._running:
            return
        self._running = False
        self.turn.stop()
        self._stop_tts()
        logger.info("Conversation loop stopped")

    def feed_audio(self, audio_frame: bytes) -> None:
        """Feed an incoming audio frame from the microphone.

        Args:
            audio_frame: Raw 16-bit PCM mono audio (at sample rate
                from VAD config, default 16000 Hz).
        """
        if not self._running:
            return

        # Run VAD on the frame
        result = self.vad.classify_frame(audio_frame)

        # If in SPEAKING state, check for barge-in
        if self.turn.is_speaking() and result.is_speech and self.config.turn.barge_in_enabled:
            logger.debug("Barge-in detected")
            self.turn.on_barge_in()
            return

        if not self.turn.is_listening():
            return

        # Buffer audio while listening
        if result.is_speech or self._speech_active:
            self._audio_buffer.append(audio_frame)

        # Track speech state transitions
        if self.vad.speech_started:
            self._speech_active = True
            self.turn.on_speech_detected()
            logger.debug("Speech started")

        if self.vad.speech_ended:
            self._speech_active = False
            self.vad.mark_speech_active(False)
            logger.debug("Speech ended — buffered %d frames", len(self._audio_buffer))
            # Will be processed via the on_speech_ended callback

    def send_llm_response(self, response: str) -> None:
        """Send an LLM response text to be spoken via TTS.

        This is the output path: after the loop transcribes audio and
        gets an LLM response, it calls this internally.  You can also
        call it from outside to inject a response to speak.

        Args:
            response: The text to speak.
        """
        if not response or not self._running:
            return

        if self.on_response:
            self.on_response(response)

        if self.config.tts_enabled:
            self._speak_response(response)

    def interrupt(self) -> None:
        """Interrupt ongoing TTS (barge-in from external trigger)."""
        self._stop_tts()
        if self.turn.state == TurnState.SPEAKING:
            self.turn.on_speech_complete()

    def set_llm_callback(self, callback: Callable[[str], str]) -> None:
        """Set or replace the LLM callback function."""
        self._llm_callback = callback

    # -- Internal -----------------------------------------------------------

    def _handle_state_change(self, old: TurnState, new: TurnState) -> None:
        """Internal handler for turn state changes."""
        logger.debug("Turn state: %s → %s", old.value, new.value)

        # Fire external callbacks
        if self.on_state_change:
            try:
                self.on_state_change(old, new)
            except Exception as e:
                logger.error("State change callback error: %s", e)

        if new == TurnState.LISTENING and old != TurnState.LISTENING:
            if self.on_listening_started:
                try:
                    self.on_listening_started()
                except Exception as e:
                    logger.error("Listening started callback error: %s", e)
        elif old == TurnState.LISTENING and new != TurnState.LISTENING:
            if self.on_listening_stopped:
                try:
                    self.on_listening_stopped()
                except Exception as e:
                    logger.error("Listening stopped callback error: %s", e)

    def _handle_speech_ended(self) -> None:
        """Called when the turn state machine detects speech ended.

        Transcribes the buffered audio and sends to LLM.
        """
        # Join buffered audio
        audio_data = b"".join(self._audio_buffer)
        self._audio_buffer.clear()

        if not audio_data:
            logger.debug("Empty audio buffer — returning to listen")
            self.turn.start_listening()
            return

        # Transcribe in a background thread
        threading.Thread(
            target=self._process_audio,
            args=(audio_data,),
            daemon=True,
        ).start()

    def _process_audio(self, audio_data: bytes) -> None:
        """Transcribe audio and feed to LLM (runs in background thread)."""
        try:
            text = self._transcribe(audio_data)
            if not text or not text.strip():
                logger.debug("No transcription — returning to listen")
                self.turn.start_listening()
                return

            if self.on_transcription:
                self.on_transcription(text)

            # Get LLM response
            response = self._llm_callback(text)

            # Speak the response
            self.send_llm_response(response)

        except Exception as e:
            logger.exception("Audio processing error")
            if self.on_error:
                self.on_error(e)
            self.turn.start_listening()

    def _transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio bytes to text using Whisper.

        Args:
            audio_data: Raw 16-bit PCM mono audio.

        Returns:
            Transcribed text, or empty string on failure.
        """
        try:
            from FionaCore.voice_engine import WhisperEngine  # noqa: PLC0415

            engine = WhisperEngine(model_size=self.config.stt_model)
            # Convert bytes to numpy float32 array
            import numpy as np  # noqa: PLC0415

            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            result = engine.transcribe_audio_buffer(
                samples,
                language=self.config.stt_language,
            )
            return result.strip()
        except ImportError:
            logger.warning("Whisper not available — using placeholder transcription")
            return "[transcription unavailable]"
        except Exception as e:
            logger.error("Transcription error: %s", e)
            return ""

    def _speak_response(self, text: str) -> None:
        """Stream TTS for the given text in a background thread."""
        if self.on_tts_started:
            try:
                self.on_tts_started()
            except Exception:
                pass

        self.turn.start_speaking()

        def _speak_thread() -> None:
            try:
                tts = self._get_tts()
                if not tts.available:
                    logger.warning("TTS not available — skipping speech")
                    self.turn.on_speech_complete()
                    return

                for chunk in tts.synthesize(text):
                    if not self._running or self.turn.state != TurnState.SPEAKING:
                        break
                    if self.on_tts_chunk:
                        try:
                            self.on_tts_chunk(chunk)
                        except Exception:
                            break
            except Exception as e:
                logger.error("TTS error: %s", e)
            finally:
                self.turn.on_speech_complete()
                if self.on_tts_stopped:
                    try:
                        self.on_tts_stopped()
                    except Exception:
                        pass

        threading.Thread(target=_speak_thread, daemon=True).start()

    def _get_tts(self) -> Any:
        """Lazy-import and return the StreamingTTS instance."""
        if self._tts is None:
            from Voice.streaming_tts import StreamingTTS, TTSConfig  # noqa: PLC0415
            self._tts = StreamingTTS()
        return self._tts

    def _stop_tts(self) -> None:
        """Stop any ongoing TTS synthesis."""
        if self._tts is not None:
            try:
                self._tts.stop()
            except Exception:
                pass

    def _handle_barge_in(self) -> None:
        """Handle barge-in by stopping TTS and clearing buffer."""
        self._stop_tts()
        self._audio_buffer.clear()
        self.vad.reset()
        self._speech_active = False
        logger.debug("Barge-in handled — back to listening")

    @staticmethod
    def _default_llm(text: str) -> str:
        """Default LLM callback: echo with a prefix."""
        return f"I heard you say: {text}"
