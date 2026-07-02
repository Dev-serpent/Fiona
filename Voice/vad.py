"""Voice Activity Detection for Fiona's conversational voice loop.

Provides a pluggable VAD backend that can be used to detect when a
human is speaking (endpoint detection, barge-in support).

Backends (tried in order):
1. ``webrtcvad`` — WebRTC VAD (requires ``webrtcvad`` package)
2. Silero VAD via ``silero-vad`` (if available)
3. Energy-based fallback (always works, no deps)
"""

from __future__ import annotations

import array
import logging
import struct
import warnings
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class VADConfig:
    """Configuration for voice activity detection.

    Attributes:
        sample_rate: Audio sample rate in Hz (default 16000).
        frame_duration_ms: Duration of each VAD frame in ms (default 30).
        threshold: Energy threshold (0.0–1.0) for speech detection when
            using the energy-based fallback. Higher = louder required.
        min_speech_frames: Minimum consecutive frames classified as speech
            before trigger (debounce).
        min_silence_frames: Minimum consecutive frames classified as silence
            before end-of-speech is declared.
    """

    sample_rate: int = 16000
    frame_duration_ms: int = 30
    threshold: float = 0.03
    min_speech_frames: int = 3
    min_silence_frames: int = 10


@dataclass
class VADResult:
    """Result of a VAD frame classification.

    Attributes:
        is_speech: Whether speech was detected in this frame.
        energy: RMS energy of the frame (0.0–1.0).
        frame_number: Sequential frame counter.
    """

    is_speech: bool
    energy: float
    frame_number: int


# ---------------------------------------------------------------------------
# VAD Backend Protocol
# ---------------------------------------------------------------------------


class VADBackend(Protocol):
    """Protocol for VAD backend implementations."""

    def is_speech(self, audio_frame: bytes, sample_rate: int) -> bool:
        """Return True if *audio_frame* contains speech."""
        ...


# ---------------------------------------------------------------------------
# WebRTC VAD Backend
# ---------------------------------------------------------------------------


class WebRTCVADBackend:
    """VAD backend using ``webrtcvad``."""

    def __init__(self, mode: int = 1) -> None:
        """Initialise the WebRTC VAD.

        Args:
            mode: Aggressiveness mode (0–3). 0 = least aggressive,
                3 = most aggressive. Default 1.
        """
        self._mode = mode
        self._vad: Any = None
        self._available = False

    def _ensure_loaded(self) -> bool:
        if self._vad is not None:
            return self._available
        try:
            import webrtcvad  # type: ignore[import-untyped]  # noqa: PLC0415

            self._vad = webrtcvad.Vad(self._mode)
            self._available = True
        except ImportError:
            self._vad = False
            self._available = False
        return self._available

    def is_speech(self, audio_frame: bytes, sample_rate: int) -> bool:
        if not self._ensure_loaded():
            raise RuntimeError("webrtcvad not available")
        return self._vad.is_speech(audio_frame, sample_rate)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Energy-Based VAD Backend (fallback, no deps)
# ---------------------------------------------------------------------------


class EnergyVADBackend:
    """VAD using RMS energy threshold — no external dependencies."""

    def __init__(self, threshold: float = 0.03) -> None:
        """Initialise energy-based VAD.

        Args:
            threshold: Energy threshold (0.0–1.0). Higher = louder required.
        """
        self.threshold = threshold

    def is_speech(self, audio_frame: bytes, sample_rate: int) -> bool:
        """Return True if *audio_frame* energy exceeds threshold.

        Accepts 16-bit PCM mono audio in raw bytes.  Computes RMS energy
        normalized to 0.0–1.0.
        """
        if len(audio_frame) < 2:
            return False

        # Parse 16-bit signed PCM samples
        count = len(audio_frame) // 2
        samples = struct.unpack_from("<" + "h" * count, audio_frame)

        # Compute RMS
        sum_sq = sum(s * s for s in samples)
        rms = (sum_sq / count) ** 0.5 if count > 0 else 0.0

        # Normalize: max 16-bit amplitude = 32767
        normalized = rms / 32767.0
        return normalized > self.threshold


# ---------------------------------------------------------------------------
# VAD Engine (unified interface)
# ---------------------------------------------------------------------------


class VADEngine:
    """Voice Activity Detection engine with pluggable backends.

    Uses WebRTC VAD if available, falls back to energy-based detection.

    Usage::

        engine = VADEngine(config=VADConfig())
        if engine.is_speech(audio_bytes):
            print("Speech detected!")
    """

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()
        self._backend: VADBackend | None = None
        self._frame_counter = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._speech_active = False

    # -- Backend selection --------------------------------------------------

    @property
    def backend(self) -> VADBackend:
        """Lazily initialise and return the best available VAD backend."""
        if self._backend is not None:
            return self._backend

        # Try WebRTC VAD first
        try:
            backend: VADBackend = WebRTCVADBackend()
            # Quick self-test with silence (all zeros)
            backend.is_speech(b"\x00" * 640, 16000)
            self._backend = backend
            logger.info("VAD using WebRTC backend")
            return self._backend
        except Exception:
            pass

        # Fallback: energy-based
        self._backend = EnergyVADBackend(threshold=self.config.threshold)
        logger.info("VAD using energy-based fallback (threshold=%.3f)", self.config.threshold)
        return self._backend

    # -- Frame-level classification -----------------------------------------

    def classify_frame(self, audio_bytes: bytes) -> VADResult:
        """Classify a single audio frame as speech or silence.

        Args:
            audio_bytes: Raw 16-bit PCM mono audio frame.

        Returns:
            A :class:`VADResult` with the classification.
        """
        # Compute energy for the frame (works with any backend)
        energy = self._frame_energy(audio_bytes)

        try:
            is_speech = self.backend.is_speech(audio_bytes, self.config.sample_rate)
        except Exception:
            # If backend fails, fall back to energy threshold
            is_speech = energy > self.config.threshold

        result = VADResult(
            is_speech=is_speech,
            energy=energy,
            frame_number=self._frame_counter,
        )
        self._frame_counter += 1

        # Track speech/silence runs for state management
        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._speech_frames = 0
            self._silence_frames += 1

        return result

    # -- State-level helpers -------------------------------------------------

    @property
    def speech_started(self) -> bool:
        """``True`` when enough consecutive speech frames have been seen."""
        return (
            self._speech_frames >= self.config.min_speech_frames
            and not self._speech_active
        )

    @property
    def speech_ended(self) -> bool:
        """``True`` when enough consecutive silence frames terminate speech."""
        return (
            self._silence_frames >= self.config.min_silence_frames
            and self._speech_active
        )

    def mark_speech_active(self, active: bool) -> None:
        """Update the active-speech tracking state."""
        self._speech_active = active
        if not active:
            # Reset silence counter when speech ends
            self._silence_frames = 0

    def reset(self) -> None:
        """Reset all frame counters."""
        self._frame_counter = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._speech_active = False

    # -- Internal -----------------------------------------------------------

    @staticmethod
    def _frame_size_bytes(sample_rate: int, frame_duration_ms: int) -> int:
        """Return the number of bytes in a single audio frame.

        16-bit PCM mono = 2 bytes per sample.
        """
        samples_per_frame = int(sample_rate * frame_duration_ms / 1000)
        return samples_per_frame * 2

    @staticmethod
    def _frame_energy(audio_bytes: bytes) -> float:
        """Compute normalized RMS energy for an audio frame (0.0–1.0)."""
        if len(audio_bytes) < 2:
            return 0.0
        count = len(audio_bytes) // 2
        samples = struct.unpack_from("<" + "h" * count, audio_bytes)
        sum_sq = sum(s * s for s in samples)
        rms = (sum_sq / count) ** 0.5 if count > 0 else 0.0
        return rms / 32767.0
