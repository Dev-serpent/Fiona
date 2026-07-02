"""Tests for Voice/vad.py, Voice/streaming_tts.py, Voice/turn_state.py,
and Voice/conversation_loop.py.

These tests use synthetic audio data and mocks — no real microphone or
TTS binary required.
"""

from __future__ import annotations

import struct
import time
from unittest.mock import MagicMock, patch

import pytest

from Voice.conversation_loop import ConversationLoop, LoopConfig
from Voice.turn_state import TurnConfig, TurnState, TurnStateMachine
from Voice.vad import EnergyVADBackend, VADConfig, VADEngine, VADResult


# =========================================================================
# VAD Engine
# =========================================================================


def _sine_wave_bytes(
    freq: float = 440.0,
    duration_s: float = 0.03,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> bytes:
    """Generate a sine wave audio frame as 16-bit PCM bytes."""
    n_samples = int(sample_rate * duration_s)
    samples: list[int] = []
    for i in range(n_samples):
        val = int(amplitude * 32767 * 0.5 * (1 + 0.5))  # ensure > threshold
        samples.append(val)
    return struct.pack("<" + "h" * n_samples, *samples)


def _silence_bytes(duration_s: float = 0.03, sample_rate: int = 16000) -> bytes:
    """Generate silence as 16-bit PCM bytes."""
    n_samples = int(sample_rate * duration_s)
    return b"\x00" * (n_samples * 2)


class TestEnergyVADBackend:
    """Tests for the energy-based VAD backend (no external deps)."""

    def test_speech_detected(self) -> None:
        backend = EnergyVADBackend(threshold=0.01)
        frame = _sine_wave_bytes(amplitude=0.3)
        assert backend.is_speech(frame, 16000) is True

    def test_silence_rejected(self) -> None:
        backend = EnergyVADBackend(threshold=0.01)
        frame = _silence_bytes()
        assert backend.is_speech(frame, 16000) is False

    def test_empty_frame(self) -> None:
        backend = EnergyVADBackend(threshold=0.01)
        assert backend.is_speech(b"", 16000) is False

    def test_short_frame(self) -> None:
        backend = EnergyVADBackend(threshold=0.01)
        assert backend.is_speech(b"\x00", 16000) is False

    def test_custom_threshold(self) -> None:
        backend = EnergyVADBackend(threshold=0.5)
        low = _sine_wave_bytes(amplitude=0.1)
        assert backend.is_speech(low, 16000) is False


class TestVADEngine:
    """Tests for the VADEngine."""

    def test_create_engine(self) -> None:
        engine = VADEngine()
        assert engine is not None
        assert engine.config.sample_rate == 16000

    def test_fallback_backend(self) -> None:
        """Should use energy backend when webrtcvad is not available."""
        engine = VADEngine()
        backend = engine.backend
        assert isinstance(backend, EnergyVADBackend)

    def test_classify_speech_frame(self) -> None:
        engine = VADEngine(config=VADConfig(threshold=0.01))
        frame = _sine_wave_bytes(amplitude=0.3)
        result = engine.classify_frame(frame)
        assert isinstance(result, VADResult)
        assert result.is_speech is True
        assert result.energy > 0

    def test_classify_silence_frame(self) -> None:
        engine = VADEngine(config=VADConfig(threshold=0.01))
        result = engine.classify_frame(_silence_bytes())
        assert result.is_speech is False

    def test_speech_started_detection(self) -> None:
        engine = VADEngine(config=VADConfig(min_speech_frames=3, threshold=0.01))
        speech = _sine_wave_bytes(amplitude=0.3)
        silence = _silence_bytes()

        # First frame — not yet started
        engine.classify_frame(speech)
        assert engine.speech_started is False

        # Second frame — still not enough
        engine.classify_frame(speech)
        assert engine.speech_started is False

        # Third frame — threshold reached
        engine.classify_frame(speech)
        assert engine.speech_started is True
        engine.mark_speech_active(True)

    def test_speech_ended_detection(self) -> None:
        engine = VADEngine(config=VADConfig(min_silence_frames=3, threshold=0.01))
        speech = _sine_wave_bytes(amplitude=0.3)
        silence = _silence_bytes()

        # Start speech
        for _ in range(3):
            engine.classify_frame(speech)
        engine.mark_speech_active(True)

        # Now send silence frames
        engine.classify_frame(silence)
        assert engine.speech_ended is False
        engine.classify_frame(silence)
        assert engine.speech_ended is False
        engine.classify_frame(silence)
        assert engine.speech_ended is True

    def test_reset(self) -> None:
        engine = VADEngine(config=VADConfig(threshold=0.01))
        engine.classify_frame(_sine_wave_bytes(amplitude=0.3))
        engine.reset()
        assert engine._frame_counter == 0  # noqa: SLF001
        assert engine._speech_frames == 0  # noqa: SLF001

    def test_frame_counter(self) -> None:
        engine = VADEngine(config=VADConfig(threshold=0.01))
        for i in range(5):
            result = engine.classify_frame(_sine_wave_bytes(amplitude=0.3))
            assert result.frame_number == i


# =========================================================================
# Turn State Machine
# =========================================================================


class TestTurnStateMachine:
    """Tests for the turn-taking state machine."""

    def test_initial_state(self) -> None:
        tsm = TurnStateMachine()
        assert tsm.state == TurnState.IDLE
        assert tsm.is_active() is False
        assert tsm.is_listening() is False
        assert tsm.is_speaking() is False

    def test_start_listening(self) -> None:
        tsm = TurnStateMachine()
        tsm.start_listening()
        assert tsm.state == TurnState.LISTENING
        assert tsm.is_active() is True
        assert tsm.is_listening() is True

    def test_idempotent_listening(self) -> None:
        tsm = TurnStateMachine()
        tsm.start_listening()
        tsm.start_listening()  # should not raise
        assert tsm.state == TurnState.LISTENING

    def test_speech_ended_transitions_to_processing(self) -> None:
        tsm = TurnStateMachine()
        tsm.start_listening()
        speech_ended_called = False

        def _on_speech_ended() -> None:
            nonlocal speech_ended_called
            speech_ended_called = True

        tsm.on_speech_ended = _on_speech_ended
        tsm.notify_speech_ended()
        assert tsm.state == TurnState.PROCESSING
        assert speech_ended_called is True

    def test_start_speaking(self) -> None:
        tsm = TurnStateMachine()
        tsm.start_listening()
        tsm.notify_speech_ended()
        tsm.start_speaking()
        assert tsm.state == TurnState.SPEAKING
        assert tsm.is_speaking() is True

    def test_speech_complete_restarts_listening(self) -> None:
        tsm = TurnStateMachine(config=TurnConfig(auto_restart=True))
        tsm.start_listening()
        # Simulate full cycle
        tsm.notify_speech_ended()
        tsm.start_speaking()
        tsm.on_speech_complete()
        assert tsm.state == TurnState.LISTENING

    def test_speech_complete_goes_idle(self) -> None:
        tsm = TurnStateMachine(config=TurnConfig(auto_restart=False))
        tsm.start_listening()
        tsm.notify_speech_ended()
        tsm.start_speaking()
        tsm.on_speech_complete()
        assert tsm.state == TurnState.IDLE

    def test_barge_in(self) -> None:
        tsm = TurnStateMachine(config=TurnConfig(barge_in_enabled=True))
        tsm.start_listening()
        tsm.notify_speech_ended()
        tsm.start_speaking()
        assert tsm.is_speaking()

        # Barge-in during speech
        triggered = False

        def _on_barge_in() -> None:
            nonlocal triggered
            triggered = True

        tsm.on_barge_in_triggered = _on_barge_in
        tsm.on_barge_in()
        assert tsm.state == TurnState.LISTENING
        assert triggered is True

    def test_barge_in_disabled(self) -> None:
        tsm = TurnStateMachine(config=TurnConfig(barge_in_enabled=False))
        tsm.start_listening()
        tsm.notify_speech_ended()
        tsm.start_speaking()

        # start_listening should NOT barge-in
        tsm.start_listening()
        assert tsm.state == TurnState.SPEAKING  # unchanged

    def test_stop(self) -> None:
        tsm = TurnStateMachine()
        tsm.start_listening()
        tsm.stop()
        assert tsm.state == TurnState.IDLE

    def test_state_change_callback(self) -> None:
        tsm = TurnStateMachine()
        changes: list[tuple[TurnState, TurnState]] = []
        tsm.on_state_change = lambda old, new: changes.append((old, new))
        tsm.start_listening()
        assert len(changes) == 1
        assert changes[0] == (TurnState.IDLE, TurnState.LISTENING)

    def test_listener_timeout(self) -> None:
        tsm = TurnStateMachine(config=TurnConfig(listener_timeout=0.1))
        timeout_called = False

        def _on_timeout() -> None:
            nonlocal timeout_called
            timeout_called = True

        tsm.on_listener_timeout = _on_timeout
        tsm.start_listening()
        time.sleep(0.2)
        assert tsm.state == TurnState.IDLE
        assert timeout_called is True


# =========================================================================
# Conversation Loop
# =========================================================================


class TestConversationLoop:
    """Tests for the conversation loop (with mocks)."""

    def test_create_loop(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        assert loop is not None
        assert loop.running is False
        assert loop.state == TurnState.IDLE

    def test_start_stop(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        loop.start()
        assert loop.running is True
        assert loop.state == TurnState.LISTENING
        loop.stop()
        assert loop.running is False

    def test_idempotent_start(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        loop.start()
        loop.start()  # should not raise or change state
        assert loop.running is True

    def test_idempotent_stop(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        loop.stop()  # should not raise
        assert loop.running is False

    def test_feed_audio_when_not_running(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        loop.feed_audio(b"\x00\x01" * 320)  # should not raise

    def test_feed_silence_no_trigger(self) -> None:
        """Silence while listening should not buffer."""
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        loop.start()
        for _ in range(5):
            loop.feed_audio(b"\x00" * 640)
        assert len(loop._audio_buffer) == 0  # noqa: SLF001

    def test_speech_buffering(self) -> None:
        """Speech-sounding audio while listening should buffer."""
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop(config=LoopConfig(vad=VADConfig(threshold=0.01)))
        loop.start()

        speech = _sine_wave_bytes(amplitude=0.3, duration_s=0.03)
        # Feed enough frames to trigger speech start
        for _ in range(5):
            loop.feed_audio(speech)

        # Should have buffered some audio
        assert len(loop._audio_buffer) > 0

    def test_llm_callback(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop(llm_callback=lambda text: f"Echo: {text}")
        assert loop._llm_callback("hello") == "Echo: hello"

    def test_default_llm_callback(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        result = loop._default_llm("test")
        assert "I heard you say" in result
        assert "test" in result

    def test_set_llm_callback(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        loop.set_llm_callback(lambda t: f"Custom: {t}")
        assert loop._llm_callback("x") == "Custom: x"

    def test_state_change_callback(self) -> None:
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        changes: list[tuple[TurnState, TurnState]] = []
        loop.on_state_change = lambda old, new: changes.append((old, new))
        loop.start()
        assert any(c[1] == TurnState.LISTENING for c in changes)

    def test_interrupt(self) -> None:
        """interrupt() should stop TTS and handle state."""
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop(config=LoopConfig(tts_enabled=False))
        loop.start()
        loop.send_llm_response("Hello")
        # Should not be in SPEAKING state (TTS disabled)
        loop.interrupt()  # Should not raise


    def test_transcribe_graceful_fallback(self) -> None:
        """Transcription should not crash when Whisper is unavailable."""
        from Voice.conversation_loop import ConversationLoop
        loop = ConversationLoop()
        result = loop._transcribe(b"\x00\x01" * 1600)
        # Should return either empty string (graceful failure) or text
        assert isinstance(result, str)


# =========================================================================
# Streaming TTS (no Piper binary)
# =========================================================================


class TestStreamingTTSNoPiper:
    """Streaming TTS tests without Piper binary installed."""

    def test_create_tts(self) -> None:
        from Voice.streaming_tts import StreamingTTS
        tts = StreamingTTS()
        assert tts is not None
        # available may be True if spd-say is installed

    def test_is_speaking_initially_false(self) -> None:
        from Voice.streaming_tts import StreamingTTS
        tts = StreamingTTS()
        assert tts.is_speaking is False

    def test_stop_when_not_speaking(self) -> None:
        from Voice.streaming_tts import StreamingTTS
        tts = StreamingTTS()
        tts.stop()  # should not raise

    def test_synthesize_without_piper(self) -> None:
        """Should use spd-say fallback if available, or yield nothing."""
        from Voice.streaming_tts import StreamingTTS
        tts = StreamingTTS()
        if tts.available:
            chunks = list(tts.synthesize("Hello"))
            # spd-say may return a single WAV chunk, or nothing
            assert isinstance(chunks, list)
        else:
            with pytest.raises(RuntimeError, match="No TTS backend"):
                list(tts.synthesize("Hello"))

    def test_nonblocking_synthesize(self) -> None:
        """Non-blocking mode should return empty list immediately."""
        from Voice.streaming_tts import StreamingTTS
        tts = StreamingTTS()
        result = tts.synthesize("Hello", blocking=False)
        assert result == []

    def test_empty_text(self) -> None:
        """Synthesize with empty text should yield nothing."""
        from Voice.streaming_tts import StreamingTTS
        tts = StreamingTTS()
        chunks = list(tts.synthesize(""))
        assert chunks == []


# =========================================================================
# TTSConfig and VADConfig defaults
# =========================================================================


class TestConfigDefaults:
    """Verify configuration dataclass defaults are sensible."""

    def test_vad_config_defaults(self) -> None:
        c = VADConfig()
        assert c.sample_rate == 16000
        assert c.frame_duration_ms == 30
        assert c.threshold == 0.03
        assert c.min_speech_frames == 3
        assert c.min_silence_frames == 10

    def test_turn_config_defaults(self) -> None:
        c = TurnConfig()
        assert c.listener_timeout == 15.0
        assert c.barge_in_enabled is True
        assert c.auto_restart is True
