"""add access metadata, diagnostics, and retry-safe practice sessions"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_access_and_practice_foundation"
down_revision: Union[str, None] = "0003_personalization_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "curriculum_chapters",
        sa.Column("map_version", sa.String(length=64), nullable=False, server_default="unversioned"),
    )
    op.add_column("users", sa.Column("role", sa.String(length=32), nullable=False, server_default="student"))
    op.add_column("users", sa.Column("school_id", sa.String(length=64)))
    op.add_column("users", sa.Column("grade_stage", sa.String(length=64)))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_table(
        "diagnostics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grade_stage", sa.String(length=64)),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("idempotency_key", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('active', 'submitted', 'abandoned')",
            name="ck_diagnostic_state",
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_diagnostic_idempotency"),
    )
    op.create_table(
        "diagnostic_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diagnostic_id", sa.Integer(), sa.ForeignKey("diagnostics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answer_text", sa.Text()),
        sa.Column("marks_earned", sa.Float()),
        sa.Column("marks_possible", sa.Float()),
        sa.Column("feedback", sa.Text()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("diagnostic_id", "question_id", name="uq_diagnostic_response_question"),
    )
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="SET NULL")),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("idempotency_key", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('draft', 'active', 'submitted', 'abandoned', 'expired')",
            name="ck_practice_session_state",
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_practice_session_idempotency"),
    )
    op.create_table(
        "practice_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("attempts.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "question_id", name="uq_practice_answer_question"),
    )


def downgrade() -> None:
    op.drop_table("practice_answers")
    op.drop_table("practice_sessions")
    op.drop_table("diagnostic_responses")
    op.drop_table("diagnostics")
    op.drop_column("users", "is_active")
    op.drop_column("users", "grade_stage")
    op.drop_column("users", "school_id")
    op.drop_column("users", "role")
    op.drop_column("curriculum_chapters", "map_version")
