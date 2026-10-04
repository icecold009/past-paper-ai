from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from starlette.requests import Request

from api.auth import AuthContext, issue_token
from api.grading import GeminiGrade, grade_answer
from api.main import app as api_app, create_app, create_attempt, get_mastery, list_questions, list_subjects
from api.schemas import AttemptCreate, GeneratedPaperResponse, SubjectResponse
from src.db.models import (
    Attempt,
    Base,
    CurriculumChapter,
    MarkSchemePoint,
    Mastery,
    Question,
    QuestionChapterMapping,
    Subject,
    User,
)


class _FakeGrader:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> GeminiGrade:
        self.calls.append(kwargs)
        return GeminiGrade(
            points_hit=["Uses a cache"],
            points_missed=["Explains the performance benefit"],
            marks_earned=1,
            feedback="Good identification; add the effect on access time.",
        )


class _FakeGeminiModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def generate_content(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(text=next(self.responses))


def _request(
    app: object,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, object] | None = None,
) -> SimpleNamespace:
    parsed = urlsplit(path)
    body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
    request_headers = {key.lower(): value for key, value in (headers or {}).items()}
    if json_body is not None:
        request_headers.setdefault("content-type", "application/json")
        request_headers.setdefault("content-length", str(len(body)))
    response_status: int | None = None
    response_body = bytearray()
    body_sent = False

    async def receive() -> dict[str, object]:
        nonlocal body_sent
        if body_sent:
            return {"type": "http.disconnect"}
        body_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = int(message["status"])
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": parsed.path,
        "raw_path": parsed.path.encode("ascii"),
        "query_string": parsed.query.encode("ascii"),
        "root_path": "",
        "headers": [(key.encode("latin-1"), value.encode("latin-1")) for key, value in request_headers.items()],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }
    asyncio.run(app(scope, receive, send))
    return SimpleNamespace(
        status_code=response_status,
        json=lambda: json.loads(response_body.decode("utf-8")),
    )


class ApiTests(unittest.TestCase):
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
            session.add(User(id=7, email="student@example.test"))
            question = Question(
                id=11,
                subject_id=subject.id,
                paper="p1",
                year=2023,
                session="May/June",
                variant="11",
                question_number="1",
                sub_label="",
                topic="Data representation",
                subtopic="Cache",
                command_word="Explain",
                difficulty="easy",
                marks=2,
                raw_text="Explain one benefit of cache memory.",
            )
            session.add(question)
            session.flush()
            chapter = CurriculumChapter(
                subject_id=subject.id,
                grade_stage="AS",
                syllabus_revision="2025",
                map_version="approved-v1",
                chapter_code="1.1",
                name="Data representation",
                position=1,
                review_status="approved",
            )
            session.add(chapter)
            session.flush()
            session.add(
                QuestionChapterMapping(
                    question_id=question.id,
                    chapter_id=chapter.id,
                    confidence=1.0,
                    review_status="approved",
                )
            )
            session.add(
                MarkSchemePoint(
                    question_id=question.id,
                    point_text="Uses a cache",
                    marks_value=1,
                )
            )
            session.commit()

        self.grader = _FakeGrader()
        self.app = create_app(engine=self.engine, grader=self.grader, auth_secret="test-secret")
        self.app.router.routes = list(api_app.router.routes)
        self.auth = AuthContext(
            user_id=7,
            role="student",
            school_id=None,
            expires_at=4_000_000_000,
        )
        self.request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/attempts",
                "headers": [],
                "query_string": b"",
                "app": self.app,
            }
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def _headers_for(self, user_id: int) -> dict[str, str]:
        token = issue_token(user_id=user_id, secret="test-secret")
        return {"Authorization": f"Bearer {token}"}

    def test_legacy_personal_routes_reject_anonymous_requests(self) -> None:
        with patch("api.main.generate_weak_spot_paper") as generate:
            attempts = _request(
                self.app,
                "POST",
                "/attempts",
                json_body={"user_id": 7, "question_id": 11, "submitted_answer_text": "answer"},
            )
            mastery = _request(self.app, "GET", "/mastery/7?subject=9618")
            paper = _request(
                self.app,
                "POST",
                "/papers/generate",
                json_body={"user_id": 7, "subject": "9618"},
            )

        self.assertEqual(
            [attempts.status_code, mastery.status_code, paper.status_code],
            [401, 401, 401],
        )
        self.assertEqual(self.grader.calls, [])
        generate.assert_not_called()

    def test_legacy_personal_routes_reject_cross_user_tokens_before_side_effects(self) -> None:
        headers = self._headers_for(user_id=8)
        with patch("api.main.generate_weak_spot_paper") as generate:
            attempts = _request(
                self.app,
                "POST",
                "/attempts",
                headers=headers,
                json_body={"user_id": 7, "question_id": 11, "submitted_answer_text": "answer"},
            )
            mastery = _request(self.app, "GET", "/mastery/7?subject=9618", headers=headers)
            paper = _request(
                self.app,
                "POST",
                "/papers/generate",
                headers=headers,
                json_body={"user_id": 7, "subject": "9618"},
            )

        self.assertEqual(
            [attempts.status_code, mastery.status_code, paper.status_code],
            [403, 403, 403],
        )
        self.assertEqual(self.grader.calls, [])
        generate.assert_not_called()

    def test_legacy_personal_routes_allow_the_signed_owner(self) -> None:
        headers = self._headers_for(user_id=7)
        attempt = _request(
            self.app,
            "POST",
            "/attempts",
            headers=headers,
            json_body={
                "user_id": 7,
                "question_id": 11,
                "submitted_answer_text": "It stores frequently used data.",
            },
        )
        mastery = _request(self.app, "GET", "/mastery/7?subject=9618", headers=headers)
        generated = GeneratedPaperResponse(
            id=19,
            user_id=7,
            subject=SubjectResponse(id=1, code="9618", name="Computer Science"),
            mode="weak_spot",
            paper="p1",
            target_marks=20,
            total_marks=0,
            questions=[],
        )
        with patch("api.main.generate_weak_spot_paper", return_value=generated) as generate:
            paper = _request(
                self.app,
                "POST",
                "/papers/generate",
                headers=headers,
                json_body={"user_id": 7, "subject": "9618", "target_marks": 20},
            )

        self.assertEqual(attempt.status_code, 201)
        self.assertEqual(mastery.status_code, 200)
        self.assertEqual(mastery.json()["user_id"], 7)
        self.assertEqual(paper.status_code, 201)
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[1].user_id, 7)
        self.assertEqual(len(self.grader.calls), 1)

    def test_gemini_grading_validates_json_and_retries_once(self) -> None:
        model = _FakeGeminiModel(
            [
                "not json",
                '```json\n{"points_hit":["Uses a cache"],"points_missed":[],"marks_earned":1,"feedback":"Correct."}\n```',
            ]
        )

        result = grade_answer(
            question_text="Explain cache memory.",
            mark_scheme_points=[{"point_text": "Uses a cache", "marks_value": 1}],
            submitted_answer_text="It stores frequently used data.",
            marks_possible=2,
            model=model,
        )

        self.assertEqual(result.marks_earned, 1)
        self.assertEqual(len(model.prompts), 2)
        self.assertIn("Uses a cache", model.prompts[0])

    def test_subject_and_filtered_question_reads(self) -> None:
        with Session(self.engine) as session:
            subjects = list_subjects(session)
            questions = list_questions(
                subject="9618",
                topic="Data representation",
                command_word="Explain",
                limit=10,
                session=session,
            )

        self.assertEqual(subjects[0].code, "9618")
        self.assertEqual(questions[0].id, 11)

    def test_chapter_filter_uses_only_approved_mapping(self) -> None:
        with Session(self.engine) as session:
            chapter = session.scalar(select(CurriculumChapter))
            assert chapter is not None
            questions = list_questions(
                subject="9618",
                chapter_id=chapter.id,
                session=session,
            )

        self.assertEqual([question.id for question in questions], [11])

    def test_attempt_is_stored_and_updates_mastery(self) -> None:
        with Session(self.engine) as session:
            result = create_attempt(
                AttemptCreate(
                    user_id=7,
                    question_id=11,
                    submitted_answer_text="It stores frequently used data.",
                ),
                self.request,
                auth=self.auth,
                session=session,
            )

        self.assertEqual(result.marks_earned, 1.0)
        self.assertTrue(result.mastery_updated)
        self.assertEqual(len(self.grader.calls), 1)
        self.assertEqual(
            self.grader.calls[0]["mark_scheme_points"],
            [{"point_text": "Uses a cache", "marks_value": 1}],
        )

        with Session(self.engine) as session:
            mastery = get_mastery(user_id=7, subject="9618", auth=self.auth, session=session)
        cell = mastery.cells[0]
        self.assertEqual(cell.topic, "Data representation")
        self.assertEqual(cell.command_word, "Explain")
        self.assertEqual(cell.score, 0.5)
        self.assertTrue(cell.has_evidence)

        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(Attempt)).all()), 1)
            self.assertEqual(len(session.scalars(select(Mastery)).all()), 1)

    def test_attempt_rejects_missing_mark_scheme(self) -> None:
        with Session(self.engine) as session:
            question = session.get(Question, 11)
            assert question is not None
            question.mark_scheme_points.clear()
            session.commit()

        with Session(self.engine) as session:
            with self.assertRaises(HTTPException) as raised:
                create_attempt(
                    AttemptCreate(
                        user_id=7,
                        question_id=11,
                        submitted_answer_text="answer",
                    ),
                    self.request,
                    auth=self.auth,
                    session=session,
                )
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
