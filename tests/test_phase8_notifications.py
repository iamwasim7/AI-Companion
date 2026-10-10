"""Phase 8 tests: notification policy (cooldown/dedup/ignore) + service wiring."""

from __future__ import annotations

import unittest

from app.detection.models import DetectedError, DetectionCategory
from app.services.notification_service import (
    NotificationPolicy,
    NotificationService,
    signature_for_error,
)


class PolicyTests(unittest.TestCase):
    def test_first_notification_allowed(self) -> None:
        policy = NotificationPolicy(cooldown_seconds=30, dedup_seconds=180)
        allowed, reason = policy.should_allow("abc", 100.0)
        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")

    def test_cooldown_suppresses_different_error(self) -> None:
        policy = NotificationPolicy(cooldown_seconds=30, dedup_seconds=180)
        policy.record("sig-a", 100.0)
        allowed, reason = policy.should_allow("sig-b", 110.0)
        self.assertFalse(allowed)
        self.assertEqual(reason, "cooldown")

    def test_cooldown_expires(self) -> None:
        policy = NotificationPolicy(cooldown_seconds=30, dedup_seconds=180)
        policy.record("sig-a", 100.0)
        allowed, _ = policy.should_allow("sig-b", 140.0)
        self.assertTrue(allowed)

    def test_duplicate_suppressed_within_window(self) -> None:
        policy = NotificationPolicy(cooldown_seconds=0, dedup_seconds=180)
        policy.record("same", 100.0)
        allowed, reason = policy.should_allow("same", 150.0)
        self.assertFalse(allowed)
        self.assertEqual(reason, "duplicate")

    def test_duplicate_expires_after_window(self) -> None:
        policy = NotificationPolicy(cooldown_seconds=0, dedup_seconds=180)
        policy.record("same", 100.0)
        allowed, _ = policy.should_allow("same", 300.0)
        self.assertTrue(allowed)

    def test_ignore_suppresses(self) -> None:
        policy = NotificationPolicy()
        policy.ignore("sig-x")
        allowed, reason = policy.should_allow("sig-x", 999.0)
        self.assertFalse(allowed)
        self.assertEqual(reason, "ignored")

    def test_signature_stable(self) -> None:
        self.assertEqual(
            signature_for_error("NameError", "x", "a.py", 1),
            signature_for_error("NameError", "x", "a.py", 1),
        )
        self.assertNotEqual(
            signature_for_error("NameError", "x"),
            signature_for_error("TypeError", "x"),
        )


class FakeResult:
    def __init__(self, confidence: float = 0.9, error_type: str = "NameError") -> None:
        self.confidence = confidence
        self.error_type = error_type
        self.problem = "A variable is used before it exists."
        self.is_fallback = False

    def short_summary(self) -> str:
        return self.problem


def _detected() -> DetectedError:
    return DetectedError(
        category=DetectionCategory.CONFIRMED_ERROR,
        language="Python",
        error_type="NameError",
        error_message="name 'username' is not defined",
        file_path="main.py",
        line_number=12,
        raw_context="NameError: name 'username' is not defined",
    )


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        # Zero cooldown/dedup for deterministic unit tests unless overridden.
        self.service = NotificationService(policy=NotificationPolicy(0, 0))

    def test_analysis_completed_creates_notification(self) -> None:
        shown: list = []
        from app.core.events import bus

        bus.subscribe("notification.show", lambda notification=None, **kw: shown.append(notification))
        try:
            self.service._on_analysis_completed(result=FakeResult(), detected=_detected())
        finally:
            # Unsubscribe to avoid cross-test leakage (bus has no weak refs).
            from app.core.events import bus as b2

            subs = list(b2._subscribers.get("notification.show", []))
            for handler in subs:
                try:
                    b2.unsubscribe("notification.show", handler)
                except Exception:
                    pass
        self.assertEqual(len(self.service.active), 1)
        self.assertIn("NameError", self.service.active[0].title)

    def test_low_confidence_skipped(self) -> None:
        self.service._on_analysis_completed(result=FakeResult(confidence=0.1), detected=_detected())
        self.assertEqual(len(self.service.active), 0)

    def test_general_context_skipped(self) -> None:
        general = DetectedError(category=DetectionCategory.GENERAL_CONTEXT, language="General")
        self.service._on_analysis_completed(result=FakeResult(), detected=general)
        self.assertEqual(len(self.service.active), 0)

    def test_dismiss_and_ignore(self) -> None:
        created = self.service.notify("T", "B", signature="sig-1")
        assert created is not None
        self.assertEqual(len(self.service.active), 1)
        self.service.dismiss(created.id)
        self.assertEqual(len(self.service.active), 0)
        created2 = self.service.notify("T2", "B2", signature="sig-2")
        assert created2 is not None
        self.service.ignore(created2.id)
        self.assertEqual(len(self.service.active), 0)
        allowed, _ = self.service.policy.should_allow("sig-2", 99999.0)
        self.assertFalse(allowed)

    def test_max_active_bounded(self) -> None:
        for i in range(5):
            self.service.notify(f"T{i}", f"B{i}", signature=f"sig-{i}")
        self.assertLessEqual(len(self.service.active), 3)


class PreliminaryTests(unittest.TestCase):
    """Item 1+5: early signal on detection.updated, in-place upgrade, skip surfacing."""

    def setUp(self) -> None:
        self.service = NotificationService(policy=NotificationPolicy(0, 0))

    def test_preliminary_shown_immediately(self) -> None:
        self.service._on_detection_updated(detected=_detected())
        self.assertEqual(len(self.service.active), 1)
        card = self.service.active[0]
        self.assertTrue(card.preliminary)
        self.assertIn("analyzing", card.body.lower())
        self.assertIn("NameError", card.title)
        # Preliminary costs no policy record, so the final is never blocked by it.
        self.assertEqual(self.service.policy._last_notify_at, 0.0)

    def test_general_context_never_preliminary(self) -> None:
        general = DetectedError(category=DetectionCategory.GENERAL_CONTEXT, language="General")
        self.service._on_detection_updated(detected=general)
        self.service._on_detection_updated(detected=None)
        self.assertEqual(len(self.service.active), 0)

    def test_ignored_signature_never_preliminary(self) -> None:
        from app.services.notification_service import signature_for_error

        detected = _detected()
        self.service.policy.ignore(signature_for_error(detected.error_type, detected.error_message, detected.file_path, detected.line_number))
        self.service._on_detection_updated(detected=detected)
        self.assertEqual(len(self.service.active), 0)

    def test_repeat_detection_no_duplicate_card(self) -> None:
        self.service._on_detection_updated(detected=_detected())
        self.service._on_detection_updated(detected=_detected())
        self.assertEqual(len(self.service.active), 1)

    def test_completed_upgrades_same_card(self) -> None:
        self.service._on_detection_updated(detected=_detected())
        first_id = self.service.active[0].id
        self.service._on_analysis_completed(result=FakeResult(), detected=_detected())
        self.assertEqual(len(self.service.active), 1)
        card = self.service.active[0]
        self.assertEqual(card.id, first_id)
        self.assertFalse(card.preliminary)
        self.assertIn("NameError", card.title)
        self.assertNotIn("analyzing", card.body.lower())

    def test_completed_without_preliminary_unchanged(self) -> None:
        self.service._on_analysis_completed(result=FakeResult(), detected=_detected())
        self.assertEqual(len(self.service.active), 1)
        self.assertFalse(self.service.active[0].preliminary)

    def test_skipped_finalizes_preliminary_quietly(self) -> None:
        self.service._on_detection_updated(detected=_detected())
        self.service._on_analysis_skipped(detected=_detected(), reason="cooldown")
        self.assertEqual(len(self.service.active), 1)
        card = self.service.active[0]
        self.assertFalse(card.preliminary)
        self.assertIn("quota", card.body.lower())

    def test_skipped_duplicate_note(self) -> None:
        self.service._on_detection_updated(detected=_detected())
        self.service._on_analysis_skipped(detected=_detected(), reason="duplicate")
        self.assertIn("already reported", self.service.active[0].body.lower())

    def test_skipped_without_preliminary_is_noop(self) -> None:
        self.service._on_analysis_skipped(detected=_detected(), reason="cooldown")
        self.assertEqual(len(self.service.active), 0)

    def test_low_confidence_finalizes_preliminary(self) -> None:
        # Screenshot scenario: fallback result (confidence 0.3) must still
        # finalize the visible preliminary instead of leaving it stuck.
        self.service._on_detection_updated(detected=_detected())
        self.service._on_analysis_completed(result=FakeResult(confidence=0.3), detected=_detected())
        self.assertEqual(len(self.service.active), 1)
        card = self.service.active[0]
        self.assertFalse(card.preliminary)
        self.assertNotIn("analyzing", card.body.lower())


if __name__ == "__main__":
    unittest.main()
