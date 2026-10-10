"""Phase 8 — Notification service: debounced, deduplicated user alerts.

Spec §26 requires:

* ``View analysis`` / ``Ask AI`` / ``Ignore`` / ``Dismiss`` actions
* Cooldown + debouncing + duplicate-error detection

Flow::

    detection.updated (has_error)
        ↓
    preliminary "analyzing…" card shown immediately (no API spent)
        ↓
    analysis.completed → same card upgraded in place (no duplicate)
    analysis.skipped  → same card finalized with the skip reason (no popup)

Only concise titles/bodies are ever stored. No screenshots, no API keys.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from typing import Any

from PySide6.QtCore import QObject

from app.core.events import bus
from app.core.logger import get_logger

logger = get_logger("services.notifications")

NOTIFY_COOLDOWN_SECONDS = 30.0
DEDUP_WINDOW_SECONDS = 180.0
MAX_ACTIVE = 3
MIN_CONFIDENCE_TO_NOTIFY = 0.4

_ids = count(1)


def signature_for_error(error_type: str, message: str, file_path: str = "", line: Any = "") -> str:
    basis = f"{error_type}|{message}|{file_path}|{line}"
    return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()[:16]


@dataclass
class AppNotification:
    """Single user-facing alert. Detected/result refs are in-memory only."""

    id: int
    title: str
    body: str
    severity: str = "warn"  # info | warn | error
    signature: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    detected: Any = None
    result_summary: str = ""
    preliminary: bool = False  # True until analysis.completed upgrades it.


class NotificationPolicy:
    """Pure cooldown/dedup/ignore logic — fully unit-testable without Qt."""

    def __init__(
        self,
        cooldown_seconds: float = NOTIFY_COOLDOWN_SECONDS,
        dedup_seconds: float = DEDUP_WINDOW_SECONDS,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.dedup_seconds = dedup_seconds
        self._last_notify_at: float = 0.0
        self._last_signature: str = ""
        self._last_signature_at: float = 0.0
        self._ignored: set[str] = set()

    def ignore(self, signature: str) -> None:
        if signature:
            self._ignored.add(signature)

    def unignore_all(self) -> None:
        self._ignored.clear()

    def is_ignored(self, signature: str) -> bool:
        return bool(signature) and signature in self._ignored

    def should_allow(self, signature: str, now: float) -> tuple[bool, str]:
        """Return (allowed, reason). Reasons: ok | ignored | duplicate | cooldown."""
        if self.is_ignored(signature):
            return False, "ignored"
        if (
            signature
            and signature == self._last_signature
            and (now - self._last_signature_at) < self.dedup_seconds
        ):
            return False, "duplicate"
        if self._last_notify_at > 0 and (now - self._last_notify_at) < self.cooldown_seconds:
            return False, "cooldown"
        return True, "ok"

    def record(self, signature: str, now: float) -> None:
        self._last_notify_at = now
        if signature:
            self._last_signature = signature
            self._last_signature_at = now


class NotificationService(QObject):
    """Owns active notifications and suppresses spam."""

    def __init__(self, policy: NotificationPolicy | None = None) -> None:
        super().__init__()
        self.policy = policy or NotificationPolicy()
        self.active: list[AppNotification] = []
        bus.subscribe("detection.updated", self._on_detection_updated)
        bus.subscribe("analysis.completed", self._on_analysis_completed)
        bus.subscribe("analysis.skipped", self._on_analysis_skipped)
        bus.subscribe("companion.notify", self._on_legacy_notify)
        logger.info("Notification service ready")

    # ── Public API ─────────────────────────────────────────────────────

    def notify(
        self,
        title: str,
        body: str,
        *,
        severity: str = "warn",
        signature: str = "",
        detected: Any = None,
        result_summary: str = "",
    ) -> AppNotification | None:
        now = time.monotonic()
        allowed, reason = self.policy.should_allow(signature, now)
        if not allowed:
            logger.info("Notification suppressed (%s, sig=%s)", reason, signature[:8] if signature else "-")
            return None
        notification = AppNotification(
            id=next(_ids),
            title=title[:120],
            body=body[:300],
            severity=severity if severity in {"info", "warn", "error"} else "warn",
            signature=signature,
            detected=detected,
            result_summary=result_summary[:300],
        )
        self.active.insert(0, notification)
        del self.active[MAX_ACTIVE:]
        self.policy.record(signature, now)
        bus.emit("notification.show", notification=notification)
        bus.emit("notifications.changed")
        bus.emit("companion.state", state="ALERT")
        logger.info("Notify #%d: %s", notification.id, notification.title[:80])
        return notification

    def dismiss(self, notification_id: int) -> None:
        before = len(self.active)
        self.active = [n for n in self.active if n.id != notification_id]
        if len(self.active) != before:
            bus.emit("notifications.changed")

    def dismiss_all(self) -> None:
        if self.active:
            self.active.clear()
            bus.emit("notifications.changed")

    def ignore(self, notification_id: int) -> None:
        for item in self.active:
            if item.id == notification_id and item.signature:
                self.policy.ignore(item.signature)
                logger.info("Ignored signature %s", item.signature[:8])
        self.dismiss(notification_id)

    # ── Event handlers ─────────────────────────────────────────────────

    def _find_active(self, signature: str) -> AppNotification | None:
        for item in self.active:
            if item.signature and item.signature == signature:
                return item
        return None

    def _on_detection_updated(self, detected: Any = None, **_kw: object) -> None:
        """Show a clearly-labeled preliminary card the moment an error is seen.

        Costs no API call. Never records into the cooldown policy, so the
        later ``analysis.completed`` upgrade is never blocked by it.
        """
        try:
            if detected is None or not getattr(detected, "has_error", False):
                return
            sig = signature_for_error(
                getattr(detected, "error_type", ""),
                getattr(detected, "error_message", ""),
                getattr(detected, "file_path", ""),
                getattr(detected, "line_number", ""),
            )
            if self.policy.is_ignored(sig):
                return
            allowed, _ = self.policy.should_allow(sig, time.monotonic())
            if not allowed:
                return
            if self._find_active(sig) is not None:
                return  # Already showing this exact error; no duplicate card.
            title = f"🔍 {detected.display_title}" if hasattr(detected, "display_title") else "🔍 Possible error detected"
            detail = (getattr(detected, "error_message", "") or "").strip()[:200]
            body = (detail + "\nAnalyzing… (preliminary — AI explanation pending)" if detail else "Analyzing… (preliminary — AI explanation pending)")
            notification = AppNotification(
                id=next(_ids),
                title=title[:120],
                body=body[:300],
                severity="warn",
                signature=sig,
                detected=detected,
                preliminary=True,
            )
            self.active.insert(0, notification)
            del self.active[MAX_ACTIVE:]
            bus.emit("notification.show", notification=notification)
            bus.emit("notifications.changed")
            bus.emit("companion.state", state="ALERT")
            logger.info("Preliminary #%d: %s", notification.id, notification.title[:80])
        except Exception:
            logger.exception("Failed to build preliminary notification")

    def _on_analysis_completed(self, result: Any = None, detected: Any = None, **_kw: object) -> None:
        try:
            if detected is None or result is None:
                return
            if not getattr(detected, "has_error", False):
                return
            detected_msg = getattr(detected, "error_message", "")
            # Match the preliminary by detection fields (not the AI's wording,
            # which may rename the error type) so the same card is upgraded.
            # This runs BEFORE the confidence gate: a visible preliminary must
            # always be finalized, even when the result is too weak to notify.
            detected_sig = signature_for_error(
                getattr(detected, "error_type", ""),
                detected_msg,
                getattr(detected, "file_path", ""),
                getattr(detected, "line_number", ""),
            )
            existing = self._find_active(detected_sig)
            if existing is not None and existing.preliminary:
                title = f"⚠️ {detected.display_title}" if hasattr(detected, "display_title") else "⚠️ Possible error detected"
                body = getattr(result, "short_summary", lambda: "")()
                if not body:
                    body = getattr(result, "problem", "") or detected_msg or "An error was detected on screen."
                # Upgrade the visible preliminary card in place — same entry,
                # never a duplicate. The user already sees it, so this is not
                # new popup spam; still record to preserve future cooldowns.
                existing.title = title[:120]
                existing.body = body[:300]
                existing.severity = "warn"
                existing.result_summary = body[:300]
                existing.preliminary = False
                self.policy.record(detected_sig, time.monotonic())
                bus.emit("notification.show", notification=existing)
                bus.emit("notifications.changed")
                bus.emit("companion.state", state="ALERT")
                logger.info("Upgraded preliminary #%d to final: %s", existing.id, existing.title[:80])
                return
            confidence = float(getattr(result, "confidence", 0.0) or 0.0)
            if confidence < MIN_CONFIDENCE_TO_NOTIFY:
                logger.info("Notification skipped: low confidence %.2f", confidence)
                return
            error_type = getattr(result, "error_type", "") or getattr(detected, "error_type", "")
            sig = signature_for_error(
                error_type,
                detected_msg,
                getattr(detected, "file_path", ""),
                getattr(detected, "line_number", ""),
            )
            title = f"⚠️ {detected.display_title}" if hasattr(detected, "display_title") else "⚠️ Possible error detected"
            body = getattr(result, "short_summary", lambda: "")()
            if not body:
                body = getattr(result, "problem", "") or detected_msg or "An error was detected on screen."
            self.notify(title, body, severity="warn", signature=sig, detected=detected, result_summary=body)
        except Exception:
            logger.exception("Failed to build analysis notification")

    def _on_analysis_skipped(self, detected: Any = None, reason: str = "", **_kw: object) -> None:
        """Finalize a visible preliminary when the API call was skipped.

        Dashboard hint only (``notifications.changed``) — deliberately no new
        popup, so cooldown/dedup protections are not weakened.
        """
        try:
            if detected is None:
                return
            sig = signature_for_error(
                getattr(detected, "error_type", ""),
                getattr(detected, "error_message", ""),
                getattr(detected, "file_path", ""),
                getattr(detected, "line_number", ""),
            )
            existing = self._find_active(sig)
            if existing is None or not existing.preliminary:
                return
            if reason == "duplicate":
                note = "Already reported recently — see the current result."
            else:
                note = "AI analysis skipped to protect API quota (another analysis just ran)."
            title = existing.title.replace("🔍 ", "⚠️ ").replace(" (analyzing…)", "")
            existing.title = title[:120]
            existing.body = (existing.body.split("\n")[0] + "\n" + note)[:300]
            existing.preliminary = False
            bus.emit("notifications.changed")
            logger.info("Preliminary #%d finalized as skipped (%s)", existing.id, reason or "unknown")
        except Exception:
            logger.exception("Failed to finalize skipped notification")

    def _on_legacy_notify(self, title: str = "Notification", body: str = "", **_kw: object) -> None:
        sig = signature_for_error(title, body)
        self.notify(str(title), str(body), severity="warn", signature=sig)


_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    global _service
    if _service is None:
        _service = NotificationService()
    return _service


def reset_notification_service() -> None:
    global _service
    _service = None
