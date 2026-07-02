"""Conversation turn-taking state machine for Fiona's voice loop.

Manages the speaking/listening state with barge-in support (interruption).

States::

    IDLE → LISTENING → PROCESSING → SPEAKING → LISTENING (or → IDLE)
      ↑                                            │
      └────────────────── barge-in ────────────────┘

- **IDLE**: No conversation active. Wake word or PTT can start.
- **LISTENING**: Microphone is live, VAD is running. Transitions to
  PROCESSING when speech ends or a timeout fires.
- **PROCESSING**: STT (Whisper) is running on captured audio.
  Transitions to SPEAKING with the LLM response, or back to LISTENING.
- **SPEAKING**: TTS is playing. Barge-in (new speech detected) returns
  to LISTENING immediately.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class TurnState(Enum):
    """Conversation turn state."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class TurnConfig:
    """Configuration for the turn-taking state machine.

    Attributes:
        listener_timeout: Max seconds to wait for speech before
            transitioning back to IDLE.
        barge_in_enabled: Allow interruption of speech by new speech input.
        auto_restart: After SPEAKING finishes, restart LISTENING (vs go IDLE).
    """

    listener_timeout: float = 15.0
    barge_in_enabled: bool = True
    auto_restart: bool = True


class TurnStateMachine:
    """Thread-safe conversation turn-taking state machine.

    Usage::

        tsm = TurnStateMachine()
        tsm.on_state_change = lambda old, new: print(f"{old} → {new}")

        tsm.start_listening()
        # ... VAD detects speech end ...
        tsm.start_processing()
        # ... LLM generates response ...
        tsm.start_speaking()
        # ... speech completes or barge-in occurs ...
        tsm.on_barge_in()
    """

    def __init__(self, config: TurnConfig | None = None) -> None:
        self.config = config or TurnConfig()
        self._lock = threading.Lock()
        self._state = TurnState.IDLE

        # Callbacks
        self.on_state_change: Callable[[TurnState, TurnState], None] | None = None
        self.on_barge_in_triggered: Callable[[], None] | None = None
        self.on_listener_timeout: Callable[[], None] | None = None
        self.on_speech_ended: Callable[[], None] | None = None

        # Internal
        self._timer: threading.Timer | None = None
        self._listener_timeout_cb: Callable[[], None] | None = None

    # -- Public API ---------------------------------------------------------

    @property
    def state(self) -> TurnState:
        """Return the current :class:`TurnState`."""
        with self._lock:
            return self._state

    def is_active(self) -> bool:
        """``True`` if conversation is active (not IDLE)."""
        return self.state != TurnState.IDLE

    def is_listening(self) -> bool:
        """``True`` if the system is currently listening for speech."""
        return self.state == TurnState.LISTENING

    def is_speaking(self) -> bool:
        """``True`` if TTS is currently playing."""
        return self.state == TurnState.SPEAKING

    # -- State transitions --------------------------------------------------

    def start_listening(self) -> None:
        """Transition to LISTENING state.

        Safe to call from any state — forces IDLE/LISTENING if currently
        SPEAKING (barge-in).
        """
        with self._lock:
            was = self._state

            if was == TurnState.LISTENING:
                return  # Already listening — no-op
            if was == TurnState.SPEAKING:
                if self.config.barge_in_enabled:
                    self._handle_barge_in_locked()
                    return
                else:
                    # Barge-in disabled — stay in SPEAKING
                    return
            if was == TurnState.PROCESSING:
                # Don't interrupt processing — the results will arrive soon
                logger.debug("Ignoring start_listening() while processing")
                return

            self._state = TurnState.LISTENING
            self._start_listener_timer_locked()

        self._fire_state_change(was, TurnState.LISTENING)

    def on_speech_detected(self) -> None:
        """Call when VAD detects speech start.

        Resets the listener timeout.
        """
        with self._lock:
            if self._state == TurnState.LISTENING:
                self._restart_listener_timer_locked()

    def notify_speech_ended(self) -> None:
        """Call when VAD detects speech end (silence after speech).

        Transitions to PROCESSING.
        """
        with self._lock:
            if self._state != TurnState.LISTENING:
                return
            self._cancel_listener_timer_locked()
            self._state = TurnState.PROCESSING

        self._fire_state_change(TurnState.LISTENING, TurnState.PROCESSING)
        if self.on_speech_ended:
            self.on_speech_ended()

    def start_processing(self) -> None:
        """Transition to PROCESSING state."""
        with self._lock:
            was = self._state
            self._cancel_listener_timer_locked()
            self._state = TurnState.PROCESSING
        self._fire_state_change(was, TurnState.PROCESSING)

    def start_speaking(self) -> None:
        """Transition to SPEAKING state to play TTS."""
        with self._lock:
            was = self._state
            self._state = TurnState.SPEAKING
        self._fire_state_change(was, TurnState.SPEAKING)

    def on_speech_complete(self) -> None:
        """Call when TTS playback finishes.

        Transitions to LISTENING (if auto_restart) or IDLE.
        """
        with self._lock:
            was = self._state
            if self.config.auto_restart:
                self._state = TurnState.LISTENING
                self._start_listener_timer_locked()
            else:
                self._state = TurnState.IDLE
        self._fire_state_change(was, self._state)

    def on_barge_in(self) -> None:
        """Handle barge-in (interruption) when speech is detected during TTS."""
        with self._lock:
            was = self._state
            self._handle_barge_in_locked()
        self._fire_state_change(was, TurnState.LISTENING)
        if self.on_barge_in_triggered:
            self.on_barge_in_triggered()

    def stop(self) -> None:
        """Stop the conversation and return to IDLE."""
        with self._lock:
            was = self._state
            self._cancel_listener_timer_locked()
            self._state = TurnState.IDLE
        self._fire_state_change(was, TurnState.IDLE)

    # -- Internal -----------------------------------------------------------

    def _handle_barge_in_locked(self) -> None:
        """Handle barge-in (caller must hold lock)."""
        self._cancel_listener_timer_locked()
        self._state = TurnState.LISTENING
        self._start_listener_timer_locked()

    def _start_listener_timer_locked(self) -> None:
        """Start the listener timeout timer (caller must hold lock)."""
        self._cancel_listener_timer_locked()
        if self.config.listener_timeout > 0:
            self._timer = threading.Timer(
                self.config.listener_timeout,
                self._on_listener_timeout,
            )
            self._timer.daemon = True
            self._timer.start()

    def _restart_listener_timer_locked(self) -> None:
        """Reset the listener timeout (caller must hold lock)."""
        self._start_listener_timer_locked()

    def _cancel_listener_timer_locked(self) -> None:
        """Cancel the listener timeout timer (caller must hold lock)."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_listener_timeout(self) -> None:
        """Called when the listener timeout fires — no speech heard."""
        logger.debug("Listener timeout — no speech detected")
        with self._lock:
            self._state = TurnState.IDLE
            self._timer = None
        if self.on_listener_timeout:
            self.on_listener_timeout()

    def _fire_state_change(self, old: TurnState, new: TurnState) -> None:
        """Fire the state change callback (outside the lock)."""
        if self.on_state_change and old != new:
            try:
                self.on_state_change(old, new)
            except Exception as e:
                logger.error("State change callback error: %s", e)
