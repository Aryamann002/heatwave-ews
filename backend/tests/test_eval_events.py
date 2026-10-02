import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models.eval_events import _is_event
from models.train_bias import build_samples


class EventEvaluationTests(unittest.TestCase):
    def test_event_label_follows_imd_zone_minimum_and_departure(self) -> None:
        self.assertTrue(_is_event("plains", 44.0, 38.0))  # >= 40 C and departure 6 C
        self.assertFalse(_is_event("plains", 44.0, 42.5))  # hot but departure only 1.5 C
        self.assertFalse(_is_event("plains", 35.0, 28.0))  # large departure, below zone minimum

    def test_cached_only_never_touches_the_network(self) -> None:
        with tempfile.TemporaryDirectory() as empty, patch("models.train_bias.urlopen") as urlopen:
            self.assertEqual(build_samples(Path(empty), cached_only=True), [])
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
