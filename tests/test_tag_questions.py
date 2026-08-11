from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.tag_questions import tag_questions


class _FakeModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def generate_content(self, prompt: str) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(text=next(self.responses))


class TagQuestionsTests(unittest.TestCase):
    def _write_inputs(self, temp_path: Path) -> tuple[Path, Path, Path]:
        questions_csv = temp_path / "9618_questions.csv"
        pairs_csv = temp_path / "9618_qp_ms_pairs.csv"
        output_csv = temp_path / "9618_tagged_questions.csv"
        pd.DataFrame(
            [
                {
                    "question_id": "q1",
                    "subject": "9618",
                    "filename": "9618_p1_2023_mj_11_qp.pdf",
                    "paper": "p1",
                    "year": 2023,
                    "session": "May/June",
                    "variant": "11",
                    "question_number": "1",
                    "question_text": "1. State one use of cache memory. [1]",
                    "subquestions": "[]",
                }
            ]
        ).to_csv(questions_csv, index=False)
        pd.DataFrame(
            [
                {
                    "subject": "9618",
                    "paper": "p1",
                    "year": 2023,
                    "session": "May/June",
                    "variant": "11",
                    "qp_text": "Question",
                    "ms_text": "Accept: reduces access time",
                }
            ]
        ).to_csv(pairs_csv, index=False)
        return questions_csv, pairs_csv, output_csv

    def test_dry_run_prints_prompts_without_model_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            questions_csv, pairs_csv, output_csv = self._write_inputs(Path(temp_dir))
            tagged = tag_questions(
                "9618",
                questions_csv=questions_csv,
                pairs_csv=pairs_csv,
                output_csv=output_csv,
                limit=1,
                dry_run=True,
                delay_seconds=0,
            )
            self.assertTrue(output_csv.exists())

        self.assertEqual(len(tagged), 1)
        self.assertEqual(json.loads(tagged.loc[0, "subquestion_tags"]), [])

    def test_retries_malformed_classification_response_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            questions_csv, pairs_csv, output_csv = self._write_inputs(Path(temp_dir))
            model = _FakeModel(
                [
                    "not json",
                    '{"topic":"Memory","subtopic":"Cache","command_word":"State","difficulty":"easy"}',
                    '{"points":["Reduces access time"]}',
                ]
            )
            tagged = tag_questions(
                "9618",
                questions_csv=questions_csv,
                pairs_csv=pairs_csv,
                output_csv=output_csv,
                delay_seconds=0,
                model=model,
            )

        self.assertEqual(model.calls, 3)
        self.assertEqual(tagged.loc[0, "topic"], "Memory")
        self.assertEqual(json.loads(tagged.loc[0, "mark_scheme_points"]), ["Reduces access time"])

    def test_variant_scope_filters_questions_and_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            questions_csv, pairs_csv, output_csv = self._write_inputs(Path(temp_dir))
            questions = pd.read_csv(questions_csv)
            second_question = questions.iloc[0].copy()
            second_question["question_id"] = "q2"
            second_question["variant"] = "12"
            pd.concat([questions, pd.DataFrame([second_question])], ignore_index=True).to_csv(
                questions_csv,
                index=False,
            )
            pairs = pd.read_csv(pairs_csv)
            second_pair = pairs.iloc[0].copy()
            second_pair["variant"] = "12"
            pd.concat([pairs, pd.DataFrame([second_pair])], ignore_index=True).to_csv(
                pairs_csv,
                index=False,
            )

            tagged = tag_questions(
                "9618",
                questions_csv=questions_csv,
                pairs_csv=pairs_csv,
                output_csv=output_csv,
                dry_run=True,
                delay_seconds=0,
                allowed_variants={"2"},
            )

        self.assertEqual(len(tagged), 1)
        self.assertEqual(str(tagged.loc[0, "variant"]), "12")


if __name__ == "__main__":
    unittest.main()
