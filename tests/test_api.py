from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timezone
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
    MistakeReview,
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
                MistakeReview(
                    user_id=user_id,
                    original_attempt_id=attempt.id,
                    source="user_confirmed",
                    state="open",
                )
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

    def _seed_generated_question(
        self,
        *,
        user_id: int,
        question_id: int,
        raw_text: str,
        linked: bool = True,
    ) -> None:
        with Session(self.engine) as session:
            subject = session.scalar(select(Subject).where(Subject.code == "9618"))
            assert subject is not None
            paper = Paper(user_id=user_id, subject_id=subject.id, mode="weak_spot")
            session.add(paper)
            session.flush()
            question = Question(
                id=question_id,
                subject_id=subject.id,
                paper="ai_generated",
                year=2026,
                session="AI generated",
                variant=str(user_id),
                question_number=f"AI-{question_id}",
                sub_label="",
                topic="Data representation",
                subtopic="Cache",
                command_word="Explain",
                difficulty="easy",
                marks=2,
                raw_text=raw_text,
            )
            session.add(question)
            session.flush()
            session.add(
                MarkSchemePoint(
                    question_id=question.id,
                    point_text=f"Private mark point for {user_id}",
                    marks_value=1,
                )
            )
            if linked:
                session.add(
                    PaperQuestion(
                        paper_id=paper.id,
                        question_id=question.id,
                        position=1,
                        source_type="ai_generated",
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
                "practice_answers", "mistake_reviews",
            },
        )
        self.assertEqual(exported["records"]["mistake_reviews"][0]["state"], "open")
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
            for model in (Attempt, Mastery, Paper, Diagnostic, DiagnosticEvidence, Recommendation, PracticeSession, MistakeReview):
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

    def test_generated_questions_are_hidden_and_owner_scoped_for_attempts_and_sessions(self) -> None:
        self._seed_generated_question(
            user_id=7,
            question_id=12,
            raw_text="Private question for student 7",
        )
        self._seed_generated_question(
            user_id=7,
            question_id=13,
            raw_text="Orphaned private question",
            linked=False,
        )
        self._seed_generated_question(
            user_id=7,
            question_id=15,
            raw_text="Ambiguously owned generated question",
        )
        with Session(self.engine) as session:
            private_question = session.get(Question, 12)
            assert private_question is not None
            private_question.topic = "Private generated dimension"
            private_question.subtopic = "Student 7 only"
            private_question.command_word = "Classify"
            chapter = session.scalar(select(CurriculumChapter))
            subject = session.scalar(select(Subject).where(Subject.code == "9618"))
            assert chapter is not None and subject is not None
            session.add(
                QuestionChapterMapping(
                    question_id=12,
                    chapter_id=chapter.id,
                    confidence=1.0,
                    review_status="approved",
                )
            )
            other_paper = Paper(user_id=8, subject_id=subject.id, mode="weak_spot")
            session.add(other_paper)
            session.flush()
            session.add(
                PaperQuestion(
                    paper_id=other_paper.id,
                    question_id=15,
                    position=1,
                    source_type="ai_generated",
                )
            )
            legacy_diagnostic = Diagnostic(
                user_id=8,
                subject_id=subject.id,
                grade_stage="AS",
                state="active",
                idempotency_key="legacy-private-question",
            )
            session.add(legacy_diagnostic)
            session.flush()
            legacy_diagnostic_id = legacy_diagnostic.id
            session.add(DiagnosticResponse(diagnostic_id=legacy_diagnostic.id, question_id=12))
            session.commit()

        other_mastery = _request(
            self.app,
            "GET",
            "/mastery/8?subject=9618",
            headers=self._headers_for(8),
        )
        owner_mastery = _request(
            self.app,
            "GET",
            "/mastery/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertNotIn(
            "Private generated dimension",
            json.dumps(other_mastery.json()["cells"]),
        )
        self.assertIn(
            "Private generated dimension",
            json.dumps(owner_mastery.json()["cells"]),
        )

        with Session(self.engine) as session:
            questions = list_questions(subject="9618", limit=10, session=session)
        self.assertEqual([question.id for question in questions], [11])

        diagnostic = _request(
            self.app,
            "POST",
            "/diagnostics",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "subject": "9618", "grade_stage": "AS", "question_limit": 10},
        )
        self.assertEqual(diagnostic.status_code, 201)
        self.assertEqual([question["id"] for question in diagnostic.json()["questions"]], [11])
        legacy_diagnostic = _request(
            self.app,
            "POST",
            f"/diagnostics/{legacy_diagnostic_id}/submit?user_id=8",
            headers=self._headers_for(8),
        )
        self.assertEqual(legacy_diagnostic.status_code, 200)
        self.assertEqual(legacy_diagnostic.json()["questions"], [])

        owner_attempt = _request(
            self.app,
            "POST",
            "/attempts",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "question_id": 12, "submitted_answer_text": "My answer"},
        )
        other_attempt = _request(
            self.app,
            "POST",
            "/attempts",
            headers=self._headers_for(8),
            json_body={"user_id": 8, "question_id": 12, "submitted_answer_text": "Try to read it"},
        )
        orphan_attempt = _request(
            self.app,
            "POST",
            "/attempts",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "question_id": 13, "submitted_answer_text": "No owner"},
        )
        ambiguous_owner_attempt = _request(
            self.app,
            "POST",
            "/attempts",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "question_id": 15, "submitted_answer_text": "Ambiguous owner"},
        )
        self.assertEqual(owner_attempt.status_code, 201)
        self.assertEqual(other_attempt.status_code, 404)
        self.assertEqual(orphan_attempt.status_code, 404)
        self.assertEqual(ambiguous_owner_attempt.status_code, 404)

        owner_session = _request(
            self.app,
            "POST",
            "/practice/sessions",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "subject": "9618", "question_ids": [12]},
        )
        other_session = _request(
            self.app,
            "POST",
            "/practice/sessions",
            headers=self._headers_for(8),
            json_body={"user_id": 8, "subject": "9618", "question_ids": [12]},
        )
        orphan_session = _request(
            self.app,
            "POST",
            "/practice/sessions",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "subject": "9618", "question_ids": [13]},
        )
        ambiguous_owner_session = _request(
            self.app,
            "POST",
            "/practice/sessions",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "subject": "9618", "question_ids": [15]},
        )
        self.assertEqual(owner_session.status_code, 201)
        self.assertEqual(other_session.status_code, 422)
        self.assertEqual(orphan_session.status_code, 422)
        self.assertEqual(ambiguous_owner_session.status_code, 422)

    def test_privacy_export_includes_only_the_owners_generated_content(self) -> None:
        self._seed_generated_question(
            user_id=7,
            question_id=12,
            raw_text="Private question for student 7",
        )
        self._seed_generated_question(
            user_id=8,
            question_id=13,
            raw_text="Private question for student 8",
        )
        self._seed_generated_question(
            user_id=7,
            question_id=14,
            raw_text="Ambiguously owned question",
        )
        with Session(self.engine) as session:
            subject = session.scalar(select(Subject).where(Subject.code == "9618"))
            assert subject is not None
            other_paper = Paper(user_id=8, subject_id=subject.id, mode="weak_spot")
            session.add(other_paper)
            session.flush()
            session.add(
                PaperQuestion(
                    paper_id=other_paper.id,
                    question_id=14,
                    position=1,
                    source_type="ai_generated",
                )
            )
            session.commit()

        response = _request(
            self.app,
            "GET",
            "/privacy/export",
            headers=self._headers_for(7),
        )
        self.assertEqual(response.status_code, 200)
        paper_questions = response.json()["records"]["paper_questions"]
        exported_by_question = {row["question_id"]: row for row in paper_questions}
        self.assertEqual(set(exported_by_question), {12, 14})
        self.assertEqual(
            exported_by_question[12]["generated_content"],
            {
                "raw_text": "Private question for student 7",
                "marks": 2,
                "mark_scheme_points": [
                    {"point_text": "Private mark point for 7", "marks_value": 1}
                ],
            },
        )
        self.assertIsNone(exported_by_question[14]["generated_content"])
        self.assertEqual(
            exported_by_question[14]["generated_content_status"],
            "unavailable_ambiguous_or_missing_owner",
        )
        self.assertNotIn("Private question for student 8", json.dumps(paper_questions))
        self.assertNotIn("Private mark point for 8", json.dumps(paper_questions))

    def test_account_deletion_erases_owned_generated_content_and_redacts_referenced_content(self) -> None:
        self._seed_generated_question(
            user_id=7,
            question_id=12,
            raw_text="Delete this private question",
        )
        self._seed_generated_question(
            user_id=8,
            question_id=13,
            raw_text="Keep the other student's private question",
        )
        self._seed_generated_question(
            user_id=7,
            question_id=14,
            raw_text="Redact this cross-referenced question",
        )
        with Session(self.engine) as session:
            session.add(
                Attempt(
                    user_id=8,
                    question_id=14,
                    submitted_answer_text="Legacy cross-owner answer",
                )
            )
            session.commit()

        response = _request(
            self.app,
            "DELETE",
            "/privacy/account",
            headers=self._headers_for(7),
            json_body={"confirmation": "DELETE MY DATA"},
        )
        self.assertEqual(response.status_code, 204)

        with Session(self.engine) as session:
            self.assertIsNone(session.get(Question, 12))
            other_owner_question = session.get(Question, 13)
            self.assertIsNotNone(other_owner_question)
            self.assertEqual(other_owner_question.raw_text, "Keep the other student's private question")
            referenced_question = session.get(Question, 14)
            self.assertIsNotNone(referenced_question)
            self.assertEqual(referenced_question.raw_text, "")
            self.assertIsNone(referenced_question.topic)
            self.assertIsNone(referenced_question.marks)
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(MarkSchemePoint).where(
                        MarkSchemePoint.question_id.in_([12, 14])
                    )
                ),
                0,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(MarkSchemePoint).where(
                        MarkSchemePoint.question_id == 13
                    )
                ),
                1,
            )
            self.assertEqual(session.get(Question, 11).raw_text, "Explain one benefit of cache memory.")

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

    def _seed_mistake_attempt(
        self,
        *,
        user_id: int,
        question_id: int,
        marks_earned: float | None,
        marks_possible: float | None,
        grading_status: str = "graded",
        answer_text: str = "Synthetic original answer",
    ) -> int:
        with Session(self.engine) as session:
            subject = session.scalar(select(Subject).where(Subject.code == "9618"))
            assert subject is not None
            if session.get(Question, question_id) is None:
                session.add(
                    Question(
                        id=question_id,
                        subject_id=subject.id,
                        paper="p1",
                        year=2025,
                        session="Synthetic fixture",
                        variant="12",
                        question_number=f"SYN-{question_id}",
                        sub_label="",
                        topic="Synthetic review topic",
                        subtopic="Eligibility fixture",
                        command_word="Explain",
                        marks=2,
                        raw_text=f"Synthetic 9618 fixture question {question_id}.",
                    )
                )
            session.flush()
            attempt = Attempt(
                user_id=user_id,
                question_id=question_id,
                submitted_answer_text=answer_text,
                points_awarded={
                    "points_hit": ["Synthetic point"],
                    "points_missed": ["Synthetic missed point"],
                    "feedback": "Synthetic previous feedback.",
                },
                marks_earned=marks_earned,
                marks_possible=marks_possible,
                grading_status=grading_status,
                attempted_at=datetime.now(timezone.utc),
            )
            session.add(attempt)
            session.commit()
            return attempt.id

    def test_mistake_queue_uses_scored_misses_or_explicit_owner_confirmation(self) -> None:
        missed = self._seed_mistake_attempt(
            user_id=7, question_id=21, marks_earned=1, marks_possible=2, answer_text="Do not reveal this answer"
        )
        full_credit = self._seed_mistake_attempt(user_id=7, question_id=22, marks_earned=2, marks_possible=2)
        unscored = self._seed_mistake_attempt(user_id=7, question_id=23, marks_earned=None, marks_possible=None)
        disputed = self._seed_mistake_attempt(
            user_id=7, question_id=24, marks_earned=0, marks_possible=2, grading_status="disputed"
        )
        other_owner = self._seed_mistake_attempt(
            user_id=8, question_id=25, marks_earned=0, marks_possible=2
        )

        queue = _request(
            self.app,
            "GET",
            "/mistakes/queue/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(queue.status_code, 200)
        self.assertEqual([item["original_attempt_id"] for item in queue.json()["items"]], [missed])
        self.assertNotIn("Do not reveal this answer", json.dumps(queue.json()))
        self.assertNotIn("Synthetic previous feedback", json.dumps(queue.json()))

        wrong_owner_queue = _request(
            self.app,
            "GET",
            "/mistakes/queue/8?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(wrong_owner_queue.status_code, 403)
        wrong_owner_confirm = _request(
            self.app,
            "POST",
            "/mistakes/reviews/confirm",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "attempt_id": other_owner},
        )
        self.assertEqual(wrong_owner_confirm.status_code, 404)

        confirmed = _request(
            self.app,
            "POST",
            "/mistakes/reviews/confirm",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "attempt_id": full_credit},
        )
        self.assertEqual(confirmed.status_code, 201)
        self.assertEqual(confirmed.json()["source"], "user_confirmed")
        after_confirmation = _request(
            self.app,
            "GET",
            "/mistakes/queue/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(
            {item["original_attempt_id"] for item in after_confirmation.json()["items"]},
            {missed, full_credit},
        )
        self.assertNotIn(unscored, {item["original_attempt_id"] for item in after_confirmation.json()["items"]})
        self.assertNotIn(disputed, {item["original_attempt_id"] for item in after_confirmation.json()["items"]})

    def test_mistake_retry_is_idempotent_append_only_and_reveals_history_after_retry(self) -> None:
        original_id = self._seed_mistake_attempt(
            user_id=7, question_id=31, marks_earned=1, marks_possible=2, answer_text="Original answer hidden first"
        )
        create_payload = {
            "user_id": 7,
            "subject": "9618",
            "attempt_ids": [original_id],
            "idempotency_key": "review-session-7-1",
        }
        created = _request(
            self.app,
            "POST",
            "/mistakes/sessions",
            headers=self._headers_for(7),
            json_body=create_payload,
        )
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["id"]
        item = created.json()["items"][0]
        review_id = item["review_id"]
        self.assertIn("Synthetic 9618 fixture question 31", item["question"]["raw_text"])
        self.assertNotIn("Original answer hidden first", json.dumps(created.json()))
        self.assertNotIn("Synthetic previous feedback", json.dumps(created.json()))
        cross_owner_session = _request(
            self.app,
            "POST",
            "/mistakes/sessions",
            headers=self._headers_for(8),
            json_body={
                "user_id": 8,
                "subject": "9618",
                "attempt_ids": [original_id],
                "idempotency_key": "cross-owner-session",
            },
        )
        self.assertEqual(cross_owner_session.status_code, 404)
        cross_owner_read = _request(
            self.app,
            "GET",
            f"/mistakes/sessions/{session_id}?user_id=8",
            headers=self._headers_for(8),
        )
        self.assertEqual(cross_owner_read.status_code, 403)
        hidden = _request(
            self.app,
            "GET",
            f"/mistakes/sessions/{session_id}/items/{review_id}/reveal?user_id=7",
            headers=self._headers_for(7),
        )
        self.assertEqual(hidden.status_code, 409)

        active = _request(
            self.app,
            "GET",
            "/mistakes/sessions/active/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(active.json()["id"], session_id)
        duplicate_session = _request(
            self.app,
            "POST",
            "/mistakes/sessions",
            headers=self._headers_for(7),
            json_body=create_payload,
        )
        self.assertEqual(duplicate_session.status_code, 201)
        self.assertEqual(duplicate_session.json()["id"], session_id)

        draft = _request(
            self.app,
            "PUT",
            f"/mistakes/sessions/{session_id}/answers/{review_id}",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "answer_text": "My fresh retry draft"},
        )
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.json()["items"][0]["answer_text"], "My fresh retry draft")
        self.assertNotIn("Original answer hidden first", json.dumps(draft.json()))

        retry_payload = {
            "user_id": 7,
            "answer_text": "A new answer, not sent to the grader",
            "self_assessment": "partly",
            "idempotency_key": "review-retry-7-1",
        }
        retry_path = f"/mistakes/sessions/{session_id}/items/{review_id}/retry"
        retry = _request(
            self.app,
            "POST",
            retry_path,
            headers=self._headers_for(7),
            json_body=retry_payload,
        )
        duplicate_retry = _request(
            self.app,
            "POST",
            retry_path,
            headers=self._headers_for(7),
            json_body=retry_payload,
        )
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(duplicate_retry.json()["attempt_id"], retry.json()["attempt_id"])
        self.assertEqual(retry.json()["grading_status"], "self_assessed")
        self.assertEqual(self.grader.calls, [])
        conflict = _request(
            self.app,
            "POST",
            retry_path,
            headers=self._headers_for(7),
            json_body={**retry_payload, "answer_text": "Changed payload"},
        )
        self.assertEqual(conflict.status_code, 409)

        with Session(self.engine) as session:
            original = session.get(Attempt, original_id)
            retry_row = session.get(Attempt, retry.json()["attempt_id"])
            self.assertIsNotNone(original)
            self.assertIsNotNone(retry_row)
            assert original is not None and retry_row is not None
            self.assertEqual(original.submitted_answer_text, "Original answer hidden first")
            self.assertEqual(original.marks_earned, 1)
            self.assertEqual(original.points_awarded["feedback"], "Synthetic previous feedback.")
            self.assertEqual(retry_row.retry_of_attempt_id, original_id)
            self.assertEqual(retry_row.marks_earned, None)
            self.assertEqual(retry_row.grading_status, "self_assessed")
            self.assertEqual(session.scalar(select(func.count()).select_from(Attempt).where(Attempt.user_id == 7)), 2)

        revealed = _request(
            self.app,
            "GET",
            f"/mistakes/sessions/{session_id}/items/{review_id}/reveal?user_id=7",
            headers=self._headers_for(7),
        )
        self.assertEqual(revealed.status_code, 200)
        self.assertEqual(revealed.json()["original_answer_text"], "Original answer hidden first")
        self.assertEqual(revealed.json()["feedback"], "Synthetic previous feedback.")
        self.assertEqual(revealed.json()["retries"][0]["answer_text"], "A new answer, not sent to the grader")

    def test_mistake_review_resolve_revisit_reopen_and_resume(self) -> None:
        original_id = self._seed_mistake_attempt(
            user_id=7, question_id=41, marks_earned=0, marks_possible=2
        )
        created = _request(
            self.app,
            "POST",
            "/mistakes/sessions",
            headers=self._headers_for(7),
            json_body={
                "user_id": 7,
                "subject": "9618",
                "attempt_ids": [original_id],
                "idempotency_key": "review-session-7-2",
            },
        )
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["id"]
        review_id = created.json()["items"][0]["review_id"]
        saved = _request(
            self.app,
            "PUT",
            f"/mistakes/sessions/{session_id}/answers/{review_id}",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "answer_text": "Saved before leaving"},
        )
        self.assertEqual(saved.status_code, 200)
        resumed = _request(
            self.app,
            "GET",
            "/mistakes/sessions/active/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(resumed.json()["id"], session_id)
        self.assertEqual(resumed.json()["items"][0]["answer_text"], "Saved before leaving")

        retry = _request(
            self.app,
            "POST",
            f"/mistakes/sessions/{session_id}/items/{review_id}/retry",
            headers=self._headers_for(7),
            json_body={
                "user_id": 7,
                "answer_text": "Retry response",
                "self_assessment": "still_unsure",
                "idempotency_key": "review-retry-7-2",
            },
        )
        self.assertEqual(retry.status_code, 201)
        revisit = _request(
            self.app,
            "PATCH",
            f"/mistakes/reviews/{review_id}",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "state": "revisit"},
        )
        self.assertEqual(revisit.status_code, 200)
        self.assertEqual(revisit.json()["state"], "revisit")
        completed = _request(
            self.app,
            "POST",
            f"/mistakes/sessions/{session_id}/submit?user_id=7",
            headers=self._headers_for(7),
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["state"], "submitted")
        queue = _request(
            self.app,
            "GET",
            "/mistakes/queue/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(queue.json()["items"][0]["state"], "revisit")

        resolved = _request(
            self.app,
            "PATCH",
            f"/mistakes/reviews/{review_id}",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "state": "resolved"},
        )
        self.assertEqual(resolved.status_code, 200)
        empty = _request(
            self.app,
            "GET",
            "/mistakes/queue/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(empty.json()["items"], [])
        reopened = _request(
            self.app,
            "PATCH",
            f"/mistakes/reviews/{review_id}",
            headers=self._headers_for(7),
            json_body={"user_id": 7, "state": "reopened"},
        )
        self.assertEqual(reopened.json()["state"], "reopened")
        requeued = _request(
            self.app,
            "GET",
            "/mistakes/queue/7?subject=9618",
            headers=self._headers_for(7),
        )
        self.assertEqual(requeued.json()["items"][0]["state"], "reopened")


if __name__ == "__main__":
    unittest.main()
