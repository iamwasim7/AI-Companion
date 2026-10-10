"""Ask-AI prefill tests: chat handoff must carry the detected code (pure, no Qt)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace


def _notification(summary="The code has an unterminated string literal error at line 4.",
                  code='print("Hello Python)', file_path="test.py", line_number=4):
    detected = SimpleNamespace(
        relevant_code=code,
        file_path=file_path,
        line_number=line_number,
    )
    return SimpleNamespace(result_summary=summary, body=summary, detected=detected)


class AskPrefillTests(unittest.TestCase):
    def test_prefill_contains_code_and_location(self) -> None:
        from app.ui.companion import build_ask_prefill

        text = build_ask_prefill(_notification())
        self.assertIn("Explain this error in simple terms:", text)
        self.assertIn('print("Hello Python)', text)
        self.assertIn("test.py, line 4", text)

    def test_prefill_without_detected_matches_old_shape(self) -> None:
        from app.ui.companion import build_ask_prefill

        note = SimpleNamespace(result_summary="Some summary", body="Some summary", detected=None)
        self.assertEqual(
            build_ask_prefill(note),
            "Explain this error in simple terms:\nSome summary",
        )

    def test_prefill_empty_when_nothing_to_send(self) -> None:
        from app.ui.companion import build_ask_prefill

        note = SimpleNamespace(result_summary="", body="", detected=None)
        self.assertEqual(build_ask_prefill(note), "")

    def test_prefill_code_without_location(self) -> None:
        from app.ui.companion import build_ask_prefill

        text = build_ask_prefill(_notification(file_path="", line_number=None))
        self.assertIn("Code:", text)
        self.assertIn('print("Hello Python)', text)
        self.assertNotIn("line None", text)

    def test_prefill_falls_back_to_nearby_lines_without_code(self) -> None:
        # Live case: OCR lost the code line, so relevant_code is empty but
        # raw_context still holds nearby text.
        from app.ui.companion import build_ask_prefill

        detected = SimpleNamespace(
            relevant_code="",
            error_type="SyntaxError",
            file_path="test.py",
            line_number=4,
            raw_context='PS C:\\x>\nFile "test.py", line 4\nprint("Hello)\n^\nSyntaxError: unterminated string literal',
        )
        note = SimpleNamespace(result_summary="Unterminated string.", body="Unterminated string.", detected=detected)
        text = build_ask_prefill(note)
        self.assertIn("Unterminated string.", text)
        self.assertIn("unverified OCR", text)
        self.assertIn('print("Hello)', text)

    def test_prefill_no_nearby_without_raw_context(self) -> None:
        from app.ui.companion import build_ask_prefill

        detected = SimpleNamespace(relevant_code="", error_type="SyntaxError")
        note = SimpleNamespace(result_summary="S.", body="S.", detected=detected)
        text = build_ask_prefill(note)
        self.assertIn("S.", text)
        self.assertNotIn("unverified OCR", text)


if __name__ == "__main__":
    unittest.main()
