"""Phase 8 — Companion intelligence: central state reactions + safe auto-idle.

Previously every UI module emitted ``companion.state`` with its own
``QTimer.singleShot`` to return to IDLE, which could fight (e.g. pipeline
sets ANALYZING while chat sets RESPONDING). This service observes all
state requests and guarantees:

* every transient state (THINKING/ANALYZING/ALERT/RESPONDING/ERROR)
  eventually returns to IDLE if nothing else happens (safety net);
* rapid duplicate requests don't stack timers;
* transitions are logged with a reason for debugging.

It does NOT change the bus interface — existing ``bus.emit("companion.state")``
calls keep working; this service just enforces the return-to-IDLE policy.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state

logger = get_logger("services.companion")

# Safety-net delays (ms) if the owner forgets to return to IDLE.
# Owners (chat/analysis/pipeline) usually return faster themselves.
_RETURN_DELAY_MS = {
    "THINKING": 30_000,
    "ANALYZING": 60_000,
    "ALERT": 45_000,
    "RESPONDING": 8_000,
    "ERROR": 10_000,
}


class CompanionService(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._timer: QTimer | None = None
        self._expected: str = ""
        bus.subscribe("companion.state", self._on_state)
        bus.subscribe("monitoring.stop", self._on_monitoring_stop)
        logger.info("Companion service ready")

    def _on_state(self, state: str, **_payload: object) -> None:
        if state not in ("IDLE", "THINKING", "ANALYZING", "ALERT", "RESPONDING", "ERROR"):
            return
        self._cancel_timer()
        logger.info("Companion → %s", state)
        if state == "IDLE":
            return
        delay = _RETURN_DELAY_MS.get(state, 8_000)
        self._expected = state
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._return_idle_if(state))
        timer.start(delay)
        self._timer = timer

    def _on_monitoring_stop(self, **_payload: object) -> None:
        self.force_idle("monitoring stopped")

    def _return_idle_if(self, expected: str) -> None:
        if app_state.companion_state == expected:
            app_state.set_companion_state("IDLE")
            bus.emit("companion.state.silent", state="IDLE")
            bus.emit("state.changed")
            logger.info("Companion auto-return to IDLE (was %s)", expected)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None
            self._expected = ""

    def force_idle(self, reason: str = "") -> None:
        self._cancel_timer()
        if app_state.companion_state != "IDLE":
            app_state.set_companion_state("IDLE")
            bus.emit("state.changed")
            logger.info("Companion forced IDLE (%s)", reason)


_service: CompanionService | None = None


def get_companion_service() -> CompanionService:
    global _service
    if _service is None:
        _service = CompanionService()
    return _service


def reset_companion_service() -> None:
    global _service
    _service = None
