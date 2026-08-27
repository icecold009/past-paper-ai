from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.analyze_questions import analyze_questions


class AnalyzeQuestionScopeTests(unittest.TestCase):
    def test_analysis_filters_stale_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            questions_csv = temp_path / "questions.csv"
            rows = []
            for variant, question_id in (("11", "q11"), ("12", "q12")):
                rows.append(
                    {
                        "question_id": question_id,
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "variant": variant,
                        "doc_type": "qp",
                        "question_text": f"Question {variant}",
                        "question_text_length": 10,
                    }
                )
            pd.DataFrame(rows).to_csv(questions_csv, index=False)

            stats, representative, _ = analyze_questions(
                subject="9618",
                planned_papers=["p1"],
                questions_csv=questions_csv,
                stats_csv=temp_path / "stats.csv",
                representative_csv=temp_path / "representative.csv",
                blueprint_json=temp_path / "blueprint.json",
                allowed_variants={"2"},
            )

        self.assertEqual(int(stats.loc[0, "question_count"]), 1)
        self.assertEqual(representative["question_id"].tolist(), ["q12"])


if __name__ == "__main__":
    unittest.main()
