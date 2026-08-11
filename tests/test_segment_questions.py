from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.segment_questions import parse_question_structure, segment_questions


class ParseQuestionStructureTests(unittest.TestCase):
    def test_multi_part_question_attaches_marks_to_each_part(self) -> None:
        text = "1. Explain the system. (a) State two features. [2] (b) Explain one benefit. [4]"

        subquestions, top_level_marks, total_marks = parse_question_structure(text)

        self.assertEqual(top_level_marks, 0)
        self.assertEqual(total_marks, 6)
        self.assertEqual(
            subquestions,
            [
                {"label": "(a)", "text": "State two features.", "marks": 2},
                {"label": "(b)", "text": "Explain one benefit.", "marks": 4},
            ],
        )

    def test_nested_label_is_preserved(self) -> None:
        text = "2. Consider the algorithm. (a)(i) State its purpose. [2] (b) Give one limitation. [3]"

        subquestions, top_level_marks, total_marks = parse_question_structure(text)

        self.assertEqual(top_level_marks, 0)
        self.assertEqual(total_marks, 5)
        self.assertEqual(subquestions[0]["label"], "(a)(i)")
        self.assertEqual(subquestions[0]["marks"], 2)
        self.assertEqual(subquestions[1]["label"], "(b)")

    def test_single_part_question_uses_top_level_marks(self) -> None:
        text = "3. State one use of an array. [1]"

        subquestions, top_level_marks, total_marks = parse_question_structure(text)

        self.assertEqual(subquestions, [])
        self.assertEqual(top_level_marks, 1)
        self.assertEqual(total_marks, 1)

    def test_unlabeled_multiple_marks_are_summed(self) -> None:
        text = "4. Discuss the two implementation choices. [2] Include a justified comparison. [3]"

        subquestions, top_level_marks, total_marks = parse_question_structure(text)

        self.assertEqual(subquestions, [])
        self.assertEqual(top_level_marks, 5)
        self.assertEqual(total_marks, 5)

    def test_question_without_marks_is_supported(self) -> None:
        subquestions, top_level_marks, total_marks = parse_question_structure(
            "5. Describe the purpose of this component."
        )

        self.assertEqual(subquestions, [])
        self.assertEqual(top_level_marks, 0)
        self.assertEqual(total_marks, 0)


class SegmentQuestionsCsvTests(unittest.TestCase):
    def test_csv_keeps_existing_columns_and_writes_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pages_csv = temp_path / "pages.csv"
            output_csv = temp_path / "questions.csv"
            pd.DataFrame(
                [
                    {
                        "filename": "9618_p1_2023_mj_11_qp.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                        "doc_type": "qp",
                        "page": 1,
                        "text": "1. Explain the process. (a) State one step. [2] (b) Explain another step. [4]",
                    }
                ]
            ).to_csv(pages_csv, index=False)

            questions = segment_questions("9618", pages_csv=pages_csv, output_csv=output_csv)
            written = pd.read_csv(output_csv)
            subquestions = json.loads(written.loc[0, "subquestions"])

        self.assertIn("question_text", written.columns)
        self.assertIn("question_text_length", written.columns)
        self.assertIn("subquestions", written.columns)
        self.assertIn("total_marks", written.columns)
        self.assertEqual(questions.loc[0, "total_marks"], 6)
        self.assertEqual(subquestions[1]["label"], "(b)")
        self.assertEqual(subquestions[1]["marks"], 4)

    def test_filters_pages_to_allowed_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pages_csv = temp_path / "pages.csv"
            output_csv = temp_path / "questions.csv"
            pd.DataFrame(
                [
                    {
                        "filename": "9618_p1_2023_mj_11_qp.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                        "doc_type": "qp",
                        "page": 1,
                        "text": "1. Out-of-scope question. [1]",
                    },
                    {
                        "filename": "9618_p1_2023_mj_12_qp.pdf",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "12",
                        "doc_type": "qp",
                        "page": 1,
                        "text": "1. In-scope question. [2]",
                    },
                ]
            ).to_csv(pages_csv, index=False)

            questions = segment_questions(
                "9618",
                pages_csv=pages_csv,
                output_csv=output_csv,
                allowed_variants={"2"},
            )

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions.loc[0, "variant"], 12)


if __name__ == "__main__":
    unittest.main()
