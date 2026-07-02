"""Streaming Text-to-Speech engine for Fiona.

Uses Piper TTS as the primary local back-end for natural streaming
speech synthesis.  Falls back to ``spd-say`` (speech-dispatcher) when
Piper is not available.

Usage::

    from Voice.streaming_tts import StreamingTTS

    tts = StreamingTTS()
    for audio_chunk in tts.synthesize("Hello, I am Fiona."):
        # audio_chunk is raw 16-bit PCM 22050 Hz mono
        play(audio_chunk)
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Piper produces 16-bit PCM at 22050 Hz by default
PIPER_SAMPLE_RATE = 22050
PIPER_SAMPLE_WIDTH = 2  # 16-bit
PIPER_CHANNELS = 1  # mono

# Duration of each audio chunk yielded to the caller (seconds)
CHUNK_DURATION_S = 0.5


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class TTSConfig:
    """Configuration for the streaming TTS engine.

    Attributes:
        voice: Voice name/model for Piper (default "en_US-less-medium").
            See https://github.com/rhasspy/piper-tts for available voices.
        piper_binary: Path to the ``piper`` binary. If None, discovered
            via ``shutil.which("piper")``.
        speed: Speech speed factor (1.0 = normal). Piper doesn't directly
            support speed; we use ``--length-scale`` where 0.8≈faster, 1.2≈slower.
        sample_rate: Output sample rate (default 22050).
        use_spd_say: If True, skip Piper and always use spd-say fallback.
        spd_say_voice: Voice name for spd-say (e.g. "en+f4").
    """

    voice: str = "en_US-less-medium"
    piper_binary: str | None = None
    speed: float = 1.0
    sample_rate: int = PIPER_SAMPLE_RATE
    use_spd_say: bool = False
    spd_say_voice: str = "en+us3+f1"


# ---------------------------------------------------------------------------
# StreamingTTS Engine
# ---------------------------------------------------------------------------


class StreamingTTS:
    """Streaming Text-to-Speech with Piper TTS (primary) and spd-say fallback.

    Thread-safe: ``synthesize()`` may be called from different threads
    (each call creates a fresh subprocess).
    """

    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()
        self._lock = threading.Lock()
        self._piper_path: str | None = None
        self._current_process: subprocess.Popen[bytes] | None = None
        self._stop_event = threading.Event()

    # -- Public API ---------------------------------------------------------

    @property
    def available(self) -> bool:
        """``True`` if Piper binary is available or spd-say fallback works."""
        return self._piper_path is not None or self._spd_say_available()

    @property
    def is_speaking(self) -> bool:
        """``True`` if synthesis is currently in progress."""
        with self._lock:
            return self._current_process is not None

    def synthesize(
        self,
        text: str,
        *,
        blocking: bool = True,
    ) -> Generator[bytes, None, None] | list[bytes]:
        """Synthesize *text* into streaming audio chunks.

        Args:
            text: The text to speak.
            blocking: If True (default), returns a generator that yields
                audio chunks.  If False, starts synthesis in a background
                thread and returns immediately.

        Returns:
            A generator of raw 16-bit PCM 22050 Hz mono chunks, or an
            empty list if ``blocking=False``.

        Raises:
            RuntimeError: If no TTS backend is available.
        """
        self._stop_event.clear()

        if not blocking:
            threading.Thread(
                target=lambda: list(self._synthesize_internal(text)),
                daemon=True,
            ).start()
            return []

        return self._synthesize_internal(text)

    def stop(self) -> None:
        """Stop any ongoing synthesis immediately."""
        self._stop_event.set()
        with self._lock:
            self._stop_process()

    # -- Internal -----------------------------------------------------------

    def _synthesize_internal(self, text: str) -> Generator[bytes, None, None]:
        """Internal streaming synthesis — always blocking/generator."""
        if not text.strip():
            return

        # Try Piper first
        piper = self._resolve_piper()
        if piper and not self.config.use_spd_say:
            yield from self._synthesize_piper(text, piper)
            return

        # Fallback to spd-say
        if self._spd_say_available():
            yield self._synthesize_spd_say(text)
            return

        raise RuntimeError(
            "No TTS backend available. Install piper-tts or speech-dispatcher."
        )

    def _resolve_piper(self) -> str | None:
        """Find the Piper binary path (cached after first lookup)."""
        if self._piper_path is not None:
            return self._piper_path

        import shutil  # noqa: PLC0415

        path = self.config.piper_binary or shutil.which("piper") or shutil.which("piper-tts")
        if path:
            self._piper_path = path
            logger.info("Piper TTS found at %s", path)
        return self._piper_path

    def _synthesize_piper(self, text: str, piper_path: str) -> Generator[bytes, None, None]:
        """Stream audio from Piper TTS subprocess.

        Yields raw 16-bit PCM 22050 Hz mono chunks.
        """
        # Piper needs a voice model file or uses --voice flag
        voice_model = self._resolve_voice_model(piper_path)

        try:
            proc = subprocess.Popen(
                [
                    piper_path,
                    "--model",
                    voice_model,
                    "--output-raw",
                    *(["--length-scale", str(self.config.speed)] if self.config.speed != 1.0 else []),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("Piper binary not found at %s, falling back", piper_path)
            return

        with self._lock:
            self._current_process = proc

        # Write text to stdin and close it
        proc.stdin.write(text.encode("utf-8"))
        proc.stdin.close()

        chunk_size = int(PIPER_SAMPLE_RATE * PIPER_SAMPLE_WIDTH * CHUNK_DURATION_S)

        try:
            while True:
                if self._stop_event.is_set():
                    proc.terminate()
                    break

                chunk = proc.stdout.read(chunk_size)
                if not chunk:
                    break

                yield chunk

            # Read remaining audio
            remaining = proc.stdout.read()
            while remaining:
                if self._stop_event.is_set():
                    break
                yield remaining[:chunk_size]
                remaining = remaining[chunk_size:]
        finally:
            proc.wait(timeout=5)
            with self._lock:
                if self._current_process is proc:
                    self._current_process = None

    def _resolve_voice_model(self, piper_path: str) -> str:
        """Resolve the Piper voice model path.

        Checks (in order):
        1. Direct path if voice contains a slash
        2. ~/.local/share/piper/voices/{voice}.onnx
        3. /usr/share/piper/voices/{voice}.onnx
        4. Returns voice name as-is (Piper will look in its own paths)
        """
        voice = self.config.voice

        # If it looks like a path, use it directly
        if "/" in voice:
            return voice

        # Check standard locations
        home_dir = Path.home()
        candidates = [
            home_dir / ".local" / "share" / "piper" / "voices" / f"{voice}.onnx",
            Path("/usr/share/piper/voices") / f"{voice}.onnx",
            Path("/usr/local/share/piper/voices") / f"{voice}.onnx",
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        # Not found — return voice name, Piper will use its own resolution
        if not Path(voice).exists():
            logger.debug("Voice model '%s' not found locally; trying Piper resolution", voice)
        return voice

    def _synthesize_spd_say(self, text: str) -> bytes:
        """Fallback: synthesize via speech-dispatcher (spd-say) and capture.

        Returns the audio as a single WAV bytes object.
        """
        import tempfile  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            subprocess.run(
                [
                    "spd-say",
                    "-o",
                    wav_path,
                    "-w",
                    "-l",
                    self.config.spd_say_voice,
                    text,
                ],
                capture_output=True,
                timeout=30,
            )
            audio_bytes = Path(wav_path).read_bytes()
            return audio_bytes
        except Exception as e:
            logger.warning("spd-say synthesis failed: %s", e)
            return b""
        finally:
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _spd_say_available(self) -> bool:
        """Check if speech-dispatcher is available."""
        import shutil  # noqa: PLC0415

        return shutil.which("spd-say") is not None

    def _stop_process(self) -> None:
        """Terminate any running synthesis process."""
        proc = self._current_process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
                proc.wait(timeout=3)
        self._current_process = None
