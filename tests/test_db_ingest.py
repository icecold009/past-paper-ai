from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.db.ingest import ingest_subject
from src.db.models import Base, MarkSchemePoint, Question, Subject


class DatabaseIngestTests(unittest.TestCase):
    def test_ingest_is_idempotent_and_loads_subquestions_and_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tagged_csv = temp_path / "tagged.csv"
            pairs_csv = temp_path / "pairs.csv"
            pd.DataFrame(
                [
                    {
                        "question_id": "q1",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                        "question_number": "1",
                        "question_text": "Question text",
                        "subquestions": json.dumps(
                            [{"label": "(a)", "text": "State one thing.", "marks": 2}]
                        ),
                        "total_marks": 2,
                        "subquestion_tags": json.dumps(
                            [
                                {
                                    "label": "(a)",
                                    "text": "State one thing.",
                                    "marks": 2,
                                    "topic": "Memory",
                                    "subtopic": "Cache",
                                    "command_word": "State",
                                    "difficulty": "easy",
                                }
                            ]
                        ),
                        "mark_scheme_points": json.dumps(["Reduces access time"]),
                    }
                ]
            ).to_csv(tagged_csv, index=False)
            pd.DataFrame(
                [
                    {
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                    }
                ]
            ).to_csv(pairs_csv, index=False)

            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            first = ingest_subject(
                "9618",
                engine=engine,
                tagged_csv=tagged_csv,
                pairs_csv=pairs_csv,
            )
            second = ingest_subject(
                "9618",
                engine=engine,
                tagged_csv=tagged_csv,
                pairs_csv=pairs_csv,
            )

            with Session(engine) as session:
                subject_count = session.scalar(select(func.count()).select_from(Subject))
                question_count = session.scalar(select(func.count()).select_from(Question))
                point_count = session.scalar(select(func.count()).select_from(MarkSchemePoint))

        self.assertEqual(first, {"subjects": 1, "questions": 2, "mark_scheme_points": 1})
        self.assertEqual(second, first)
        self.assertEqual((subject_count, question_count, point_count), (1, 2, 1))


if __name__ == "__main__":
    unittest.main()
