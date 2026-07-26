"""initial database schema

Revision ID: 0001_initial_schema
Revises:
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("code", name="uq_subject_code"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("paper", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("session", sa.String(length=32), nullable=False),
        sa.Column("variant", sa.String(length=8), nullable=False),
        sa.Column("question_number", sa.String(length=16), nullable=False),
        sa.Column("sub_label", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("topic", sa.String(length=255)),
        sa.Column("subtopic", sa.String(length=255)),
        sa.Column("command_word", sa.String(length=64)),
        sa.Column("difficulty", sa.String(length=16)),
        sa.Column("marks", sa.Integer()),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "subject_id",
            "paper",
            "year",
            "session",
            "variant",
            "question_number",
            "sub_label",
            name="uq_question_natural_key",
        ),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
            name="ck_question_difficulty",
        ),
    )
    op.create_table(
        "mark_scheme_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("point_text", sa.Text(), nullable=False),
        sa.Column("marks_value", sa.Integer()),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("question_id", "point_text", "marks_value", name="uq_mark_scheme_point"),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("submitted_answer_text", sa.Text(), nullable=False),
        sa.Column("points_awarded", _jsonb_type(), nullable=False),
        sa.Column("marks_earned", sa.Float()),
        sa.Column("marks_possible", sa.Float()),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "mastery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("subtopic", sa.String(length=255), nullable=False),
        sa.Column("command_word", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("next_review_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "topic", "subtopic", "command_word", name="uq_mastery_dimension"),
    )
    op.create_table(
        "papers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="generated"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "paper_questions",
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id", "question_id"),
    )


def downgrade() -> None:
    op.drop_table("paper_questions")
    op.drop_table("papers")
    op.drop_table("mastery")
    op.drop_table("attempts")
    op.drop_table("mark_scheme_points")
    op.drop_table("questions")
    op.drop_table("users")
    op.drop_table("subjects")
