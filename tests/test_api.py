from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
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
    Diagnostic,
    DiagnosticEvidence,
    DiagnosticResponse,
    MarkSchemePoint,
    Mastery,
    Paper,
    PaperQuestion,
    PracticeAnswer,
    PracticeSession,
    Question,
    QuestionChapterMapping,
    Recommendation,
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
    response_headers: dict[str, str] = {}
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
            response_headers.update(
                {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
            )
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
        headers=response_headers,
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
            session.add(User(id=8, email="other-student@example.test"))
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
        # This test fixture uses a local fake grader; the shipped app remains default-off.
        self.app.state.student_data_ai_approved = True
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

    def _seed_private_records(self, user_id: int) -> None:
        with Session(self.engine) as session:
            subject = session.scalar(select(Subject).where(Subject.code == "9618"))
            chapter = session.scalar(select(CurriculumChapter))
            question = session.get(Question, 11)
            assert subject is not None and chapter is not None and question is not None

            attempt = Attempt(
                user_id=user_id,
                question_id=question.id,
                submitted_answer_text=f"private answer for {user_id}",
                points_awarded={"feedback": f"private feedback for {user_id}"},
                marks_earned=1,
                marks_possible=2,
            )
            paper = Paper(user_id=user_id, subject_id=subject.id, mode="weak_spot")
            diagnostic = Diagnostic(
                user_id=user_id,
                subject_id=subject.id,
                grade_stage="AS",
                state="submitted",
                idempotency_key=f"diagnostic-{user_id}",
            )
            recommendation = Recommendation(
                user_id=user_id,
                chapter_id=chapter.id,
                state="needs_practice",
                reason=f"private reason for {user_id}",
                evidence_count=2,
                confidence=0.8,
                activity_type="targeted_practice",
                rule_version="test-v1",
                curriculum_version="approved-v1",
            )
            practice = PracticeSession(
                user_id=user_id,
                subject_id=subject.id,
                state="submitted",
                idempotency_key=f"practice-{user_id}",
            )
            session.add_all([attempt, paper, diagnostic, recommendation, practice])
            session.flush()
            session.add_all(
                [
                    PaperQuestion(
                        paper_id=paper.id,
                        question_id=question.id,
                        position=1,
                        source_type="real",
                    ),
                    DiagnosticResponse(
                        diagnostic_id=diagnostic.id,
                        question_id=question.id,
                        answer_text=f"diagnostic answer for {user_id}",
                    ),
                    DiagnosticEvidence(
                        user_id=user_id,
                        chapter_id=chapter.id,
                        attempt_id=attempt.id,
                        source_type="attempt",
                        evidence_count=1,
                        score=0.5,
                        confidence=0.5,
                        state="developing",
                    ),
                    PracticeAnswer(
                        session_id=practice.id,
                        question_id=question.id,
                        answer_text=f"practice answer for {user_id}",
                        status="submitted",
                        attempt_id=attempt.id,
                    ),
                ]
            )
            session.add(
                Mastery(
                    user_id=user_id,
                    topic="Data representation",
                    subtopic=f"Private {user_id}",
                    command_word="Explain",
                    score=0.5,
                )
            )
            session.commit()

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

    def test_student_answer_grading_is_default_denied_before_provider_call(self) -> None:
        app = create_app(engine=self.engine, grader=self.grader, auth_secret="test-secret")
        app.router.routes = list(api_app.router.routes)
        response = _request(
            app,
            "POST",
            "/attempts",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "question_id": 11, "submitted_answer_text": "private answer"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.grader.calls, [])
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Attempt)), 0)

    def test_unapproved_guidance_provider_never_receives_derived_student_state(self) -> None:
        class _CountingSelector:
            def __init__(self) -> None:
                self.calls = 0

            def choose(self, context: object) -> object:
                self.calls += 1
                raise AssertionError("unapproved selector must not be called")

        selector = _CountingSelector()
        app = create_app(engine=self.engine, auth_secret="test-secret", guidance_selector=selector)
        app.router.routes = list(api_app.router.routes)
        response = _request(
            app,
            "GET",
            "/guidance/7?subject=9618",
            headers=self._headers_for(7),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(selector.calls, 0)

    def test_privacy_export_is_owner_scoped_complete_and_non_cacheable(self) -> None:
        self._seed_private_records(7)
        self._seed_private_records(8)
        with Session(self.engine) as session:
            inactive_owner = session.get(User, 7)
            assert inactive_owner is not None
            inactive_owner.is_active = False
            session.commit()

        response = _request(
            self.app,
            "GET",
            "/privacy/export",
            headers=self._headers_for(7),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertIn("attachment", response.headers["content-disposition"])
        exported = response.json()
        self.assertEqual(exported["profile"]["id"], 7)
        self.assertEqual(
            set(exported["records"]),
            {
                "attempts", "mastery", "papers", "paper_questions", "diagnostic_evidence",
                "recommendations", "diagnostics", "diagnostic_responses", "practice_sessions",
                "practice_answers",
            },
        )
        self.assertEqual(exported["records"]["attempts"][0]["submitted_answer_text"], "private answer for 7")
        self.assertEqual(exported["records"]["diagnostic_responses"][0]["answer_text"], "diagnostic answer for 7")
        self.assertNotIn("raw_text", json.dumps(exported))
        self.assertNotIn("private answer for 8", json.dumps(exported))

        other = _request(
            self.app,
            "GET",
            "/privacy/export",
            headers=self._headers_for(8),
        ).json()
        self.assertEqual(other["profile"]["id"], 8)
        self.assertEqual(other["records"]["attempts"][0]["submitted_answer_text"], "private answer for 8")
        self.assertNotIn("private answer for 7", json.dumps(other))

    def test_privacy_deletion_requires_confirmation_and_erases_only_owner_rows(self) -> None:
        self._seed_private_records(7)
        self._seed_private_records(8)
        with Session(self.engine) as session:
            inactive_owner = session.get(User, 7)
            assert inactive_owner is not None
            inactive_owner.is_active = False
            session.commit()
        headers = self._headers_for(7)

        rejected = _request(
            self.app,
            "DELETE",
            "/privacy/account",
            headers=headers,
            json_body={"confirmation": "DELETE"},
        )
        self.assertEqual(rejected.status_code, 422)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(User, 7))

        deleted = _request(
            self.app,
            "DELETE",
            "/privacy/account",
            headers=headers,
            json_body={"confirmation": "DELETE MY DATA"},
        )
        repeated = _request(
            self.app,
            "DELETE",
            "/privacy/account",
            headers=headers,
            json_body={"confirmation": "DELETE MY DATA"},
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(repeated.status_code, 204)

        with Session(self.engine) as session:
            self.assertIsNone(session.get(User, 7))
            self.assertIsNotNone(session.get(User, 8))
            for model in (Attempt, Mastery, Paper, Diagnostic, DiagnosticEvidence, Recommendation, PracticeSession):
                self.assertEqual(
                    session.scalar(select(func.count()).select_from(model).where(model.user_id == 7)),
                    0,
                    model.__name__,
                )
            diagnostic_ids = select(Diagnostic.id).where(Diagnostic.user_id == 7)
            practice_session_ids = select(PracticeSession.id).where(PracticeSession.user_id == 7)
            user_paper_ids = select(Paper.id).where(Paper.user_id == 7)
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(DiagnosticResponse).where(
                        DiagnosticResponse.diagnostic_id.in_(diagnostic_ids)
                    )
                ),
                0,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(PracticeAnswer).where(
                        PracticeAnswer.session_id.in_(practice_session_ids)
                    )
                ),
                0,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(PaperQuestion).where(
                        PaperQuestion.paper_id.in_(user_paper_ids)
                    )
                ),
                0,
            )
            self.assertEqual(session.scalar(select(func.count()).select_from(Attempt).where(Attempt.user_id == 8)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(PaperQuestion)), 1)
            self.assertIsNotNone(session.get(Question, 11))
            self.assertIsNotNone(session.scalar(select(MarkSchemePoint).where(MarkSchemePoint.question_id == 11)))

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
