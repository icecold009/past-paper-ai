from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from api.main import create_app, create_paper
from api.papers import generate_weak_spot_paper
from api.schemas import PaperGenerateRequest
from src.db.models import Attempt, Base, MarkSchemePoint, Mastery, PaperQuestion, Question, Subject, User


class _PaperGemini:
    def __init__(self) -> None:
        self.responses = iter(
            [
                '{"question_text":"Explain how a sorting algorithm can improve efficiency.","marks":2,"mark_scheme_points":["Identifies reduced comparisons","Links this to efficiency"]}',
                '{"question_text":"Explain one use of an algorithm in a computer system.","marks":2,"mark_scheme_points":["Describes a valid use","Explains the outcome"]}',
                '{"question_text":"Describe a way to represent data in memory.","marks":2,"mark_scheme_points":["Identifies a representation","Describes how it stores data"]}',
            ]
        )

    def generate_content(self, prompt: str) -> SimpleNamespace:
        return SimpleNamespace(text=next(self.responses))


class PaperGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            subject = Subject(code="9618", name="Computer Science")
            session.add(subject)
            session.flush()
            session.add(User(id=7, email="paper-student@example.test"))

            questions = [
                Question(
                    id=101, subject_id=subject.id, paper="p1", year=2023, session="May/June", variant="11",
                    question_number="1", sub_label="", topic="Algorithms", subtopic="Sorting",
                    command_word="Explain", difficulty="easy", marks=2, raw_text="Explain a sorting algorithm.",
                ),
                Question(
                    id=102, subject_id=subject.id, paper="p1", year=2022, session="May/June", variant="11",
                    question_number="2", sub_label="", topic="Data representation", subtopic="Memory",
                    command_word="Describe", difficulty="easy", marks=2, raw_text="Describe data in memory.",
                ),
                Question(
                    id=103, subject_id=subject.id, paper="p1", year=2021, session="May/June", variant="11",
                    question_number="3", sub_label="", topic="Data representation", subtopic="Memory",
                    command_word="Describe", difficulty="easy", marks=2, raw_text="Describe a representation used in memory.",
                ),
            ]
            session.add_all(questions)
            session.flush()
            session.add_all(
                [
                    MarkSchemePoint(question_id=question.id, point_text=f"Point for {question.id}", marks_value=1)
                    for question in questions
                ]
            )
            session.add_all(
                [
                    Attempt(
                        user_id=7, question_id=101, submitted_answer_text="weak", points_awarded={},
                        marks_earned=0, marks_possible=2,
                    ),
                    Attempt(
                        user_id=7, question_id=102, submitted_answer_text="strong", points_awarded={},
                        marks_earned=2, marks_possible=2,
                    ),
                ]
            )
            session.add_all(
                [
                    Mastery(user_id=7, topic="Algorithms", subtopic="Sorting", command_word="Explain", score=0.0),
                    Mastery(user_id=7, topic="Data representation", subtopic="Memory", command_word="Describe", score=1.0),
                ]
            )
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_weak_spot_paper_persists_real_and_ai_mix(self) -> None:
        with Session(self.engine) as session:
            paper = generate_weak_spot_paper(
                session,
                PaperGenerateRequest(user_id=7, subject="9618", target_marks=8, min_real_questions_per_cell=2),
                model=_PaperGemini(),
                prompt_builder=lambda subject: f"Reviewed {subject} syllabus context.",
            )

        source_types = [question.source_type for question in paper.questions]
        self.assertIn("real", source_types)
        self.assertIn("ai_generated", source_types)
        self.assertLessEqual(paper.total_marks, paper.target_marks)
        self.assertEqual(len(source_types), 4)
        with Session(self.engine) as session:
            links = session.scalars(select(PaperQuestion)).all()
            self.assertEqual(len(links), 4)
            self.assertEqual(len(session.scalars(select(Question).where(Question.paper == "ai_generated")).all()), 3)

        print("SAMPLE_WEAK_SPOT_PAPER=" + json.dumps(paper.model_dump(), sort_keys=True, default=str))

    def test_generate_endpoint_returns_labeled_paper(self) -> None:
        app = create_app(engine=self.engine)
        app.state.paper_model = _PaperGemini()
        app.state.paper_prompt_builder = lambda subject: f"Reviewed {subject} syllabus context."
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/papers/generate",
                "headers": [],
                "query_string": b"",
                "app": app,
            }
        )

        with Session(self.engine) as session:
            result = create_paper(
                PaperGenerateRequest(user_id=7, subject="9618", target_marks=8),
                request,
                session,
            )

        self.assertEqual(result.mode, "weak_spot")
        self.assertIn("ai_generated", {question.source_type for question in result.questions})
        self.assertIn("real", {question.source_type for question in result.questions})


if __name__ == "__main__":
    unittest.main()
