from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.db.models import Attempt, MarkSchemePoint, Question, Subject, User


class OrphanGeneratedQuestionMigrationTests(unittest.TestCase):
    def test_upgrade_scrubs_orphans_preserves_referenced_ids_and_shared_questions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=repo_root) as tempdir:
            database_path = Path(tempdir) / "privacy-migration.sqlite"
            database_url = f"sqlite:///{database_path.as_posix()}"
            config = Config(str(repo_root / "alembic.ini"))

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "0006_typesafe_recommendation_provenance")
                engine = create_engine(database_url)
                with Session(engine) as session:
                    subject = Subject(code="9618", name="Computer Science")
                    user = User(id=7, email="student@example.test")
                    session.add_all([subject, user])
                    session.flush()
                    orphan = Question(
                        id=101,
                        subject_id=subject.id,
                        paper="ai_generated",
                        year=2026,
                        session="AI generated",
                        variant="7",
                        question_number="AI-1",
                        sub_label="",
                        topic="Private topic",
                        subtopic="Private subtopic",
                        command_word="Explain",
                        difficulty="easy",
                        marks=2,
                        raw_text="Orphaned generated question text",
                    )
                    referenced = Question(
                        id=102,
                        subject_id=subject.id,
                        paper="ai_generated",
                        year=2026,
                        session="AI generated",
                        variant="7",
                        question_number="AI-2",
                        sub_label="",
                        topic="Private topic",
                        subtopic="Private subtopic",
                        command_word="Explain",
                        difficulty="easy",
                        marks=2,
                        raw_text="Referenced generated question text",
                    )
                    shared = Question(
                        id=103,
                        subject_id=subject.id,
                        paper="p1",
                        year=2023,
                        session="May/June",
                        variant="12",
                        question_number="1",
                        sub_label="",
                        topic="Data representation",
                        command_word="Explain",
                        marks=2,
                        raw_text="Shared source question text",
                    )
                    session.add_all([orphan, referenced, shared])
                    session.flush()
                    session.add_all(
                        [
                            MarkSchemePoint(question_id=101, point_text="Orphan point", marks_value=1),
                            MarkSchemePoint(question_id=102, point_text="Referenced point", marks_value=1),
                            MarkSchemePoint(question_id=103, point_text="Shared point", marks_value=1),
                            Attempt(
                                user_id=7,
                                question_id=102,
                                submitted_answer_text="A recorded answer",
                            ),
                        ]
                    )
                    session.commit()
                engine.dispose()

                command.upgrade(config, "head")
                engine = create_engine(database_url)
                with Session(engine) as session:
                    self.assertIsNone(session.get(Question, 101))
                    referenced_after = session.get(Question, 102)
                    self.assertIsNotNone(referenced_after)
                    self.assertEqual(referenced_after.raw_text, "")
                    self.assertIsNone(referenced_after.topic)
                    self.assertIsNone(referenced_after.marks)
                    self.assertEqual(
                        session.scalar(
                            select(func.count()).select_from(MarkSchemePoint).where(
                                MarkSchemePoint.question_id.in_([101, 102])
                            )
                        ),
                        0,
                    )
                    self.assertEqual(
                        session.get(Question, 103).raw_text,
                        "Shared source question text",
                    )
                    self.assertEqual(
                        session.scalar(
                            select(func.count()).select_from(MarkSchemePoint).where(
                                MarkSchemePoint.question_id == 103
                            )
                        ),
                        1,
                    )
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
