import unittest
from datetime import UTC, datetime

from app.advisories import draft_advisory, lint_advisory


class AdvisoryTests(unittest.TestCase):
    def test_bilingual_templates_preserve_alert_and_require_approval(self) -> None:
        start = datetime(2026, 5, 1, 6, tzinfo=UTC)
        end = datetime(2026, 5, 1, 12, tzinfo=UTC)

        english = draft_advisory("orange", "Ahmedabad", start, end, "en")
        hindi = draft_advisory("orange", "Ahmedabad", start, end, "hi")

        self.assertEqual(english.alert_level, "orange")
        self.assertEqual(english.status, "pending_approval")
        self.assertIn("11:30 IST", english.text)
        self.assertIn("17:30 IST", english.text)
        self.assertIn("गर्मी चेतावनी", hindi.text)
        self.assertTrue(lint_advisory(english))
        self.assertTrue(lint_advisory(hindi))

    def test_linter_rejects_content_outside_approved_template(self) -> None:
        draft = draft_advisory(
            "yellow",
            "Ahmedabad",
            datetime(2026, 5, 1, tzinfo=UTC),
            datetime(2026, 5, 2, tzinfo=UTC),
            "en",
        )
        tampered = draft.__class__(**{**draft.__dict__, "text": draft.text + " Take unapproved medicine."})
        with self.assertRaisesRegex(ValueError, "approved template"):
            lint_advisory(tampered)

    def test_rejects_untrusted_slots_and_invalid_alert_inputs(self) -> None:
        start = datetime(2026, 5, 1, tzinfo=UTC)
        end = datetime(2026, 5, 2, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "locality"):
            draft_advisory("yellow", "Ahmedabad {level}", start, end, "en")
        with self.assertRaisesRegex(ValueError, "alert level"):
            draft_advisory("purple", "Ahmedabad", start, end, "en")
        with self.assertRaisesRegex(ValueError, "language"):
            draft_advisory("yellow", "Ahmedabad", start, end, "gu")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            draft_advisory("yellow", "Ahmedabad", start.replace(tzinfo=None), end, "en")


if __name__ == "__main__":
    unittest.main()
