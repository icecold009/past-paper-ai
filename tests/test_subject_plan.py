from __future__ import annotations

import unittest

from src.subject_plan import (
    SUBJECT_PAPER_MARKS,
    load_subject_plan,
    load_variant_scope,
    variant_in_scope,
)


class SubjectPlanTests(unittest.TestCase):
    def test_configured_subject_papers_match_release_scope(self) -> None:
        self.assertEqual(
            load_subject_plan(),
            {
                "9618": ["p1", "p2", "p3", "p4"],
                "9709": ["p1", "p3", "p4", "p5"],
                "9231": ["p1", "p2", "p3", "p4"],
                "9702": ["p1", "p2", "p3", "p4", "p5"],
            },
        )
        self.assertEqual(load_variant_scope(), {"2"})

    def test_paper_marks_match_configured_syllabuses(self) -> None:
        self.assertEqual(
            SUBJECT_PAPER_MARKS,
            {
                "9618": {"p1": 75, "p2": 75, "p3": 75, "p4": 75},
                "9709": {"p1": 75, "p3": 75, "p4": 50, "p5": 50},
                "9231": {"p1": 75, "p2": 75, "p3": 50, "p4": 50},
                "9702": {"p1": 40, "p2": 60, "p3": 40, "p4": 100, "p5": 30},
            },
        )

    def test_variant_scope_matches_two_digit_codes_ending_in_two(self) -> None:
        self.assertTrue(variant_in_scope("12", {"2"}))
        self.assertTrue(variant_in_scope("22", {"2"}))
        self.assertFalse(variant_in_scope("11", {"2"}))
        self.assertFalse(variant_in_scope("13", {"2"}))
        self.assertTrue(variant_in_scope("12", {"12"}))
        self.assertFalse(variant_in_scope("22", {"12"}))
        self.assertTrue(variant_in_scope("11", None))


if __name__ == "__main__":
    unittest.main()
