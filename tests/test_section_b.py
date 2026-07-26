from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.guidance import get_guidance
from src.content_pack import ingest_content_pack
from src.db.models import Base, Mastery, User


class SectionBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(User(id=1, email="section-b@example.test"))
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_content_pack_loads_questions_and_mark_schemes(self) -> None:
        summary = ingest_content_pack(
            Path("content/packs/starter_bank.json"),
            engine=self.engine,
        )
        self.assertEqual(summary, {"questions": 5, "mark_scheme_points": 10})

        with Session(self.engine) as session:
            guidance = get_guidance(session, user_id=1, subject_code="9618")

        self.assertEqual(guidance.status, "start_diagnostic")
        self.assertIsNotNone(guidance.recommendation)
        self.assertEqual(guidance.recommendation.topic, "Algorithms")

    def test_guidance_prioritises_low_mastery_cell(self) -> None:
        ingest_content_pack(Path("content/packs/starter_bank.json"), engine=self.engine)
        with Session(self.engine) as session:
            session.add(
                Mastery(
                    user_id=1,
                    topic="Data representation",
                    subtopic="Memory",
                    command_word="Explain",
                    score=0.25,
                )
            )
            session.add(
                Mastery(
                    user_id=1,
                    topic="Algorithms",
                    subtopic="Searching",
                    command_word="Describe",
                    score=0.9,
                )
            )
            session.commit()
            guidance = get_guidance(session, user_id=1, subject_code="9618")

        self.assertEqual(guidance.status, "needs_practice")
        self.assertEqual(guidance.recommendation.topic, "Data representation")
        self.assertEqual(guidance.recommendation.command_word, "Explain")


if __name__ == "__main__":
    unittest.main()
