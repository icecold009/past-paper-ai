"""add reviewed curriculum and explainable personalization entities"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_personalization_foundation"
down_revision: Union[str, None] = "0002_paper_question_source_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "curriculum_chapters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grade_stage", sa.String(length=64), nullable=False),
        sa.Column("syllabus_revision", sa.String(length=64), nullable=False),
        sa.Column("chapter_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(length=320)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "subject_id", "grade_stage", "syllabus_revision", "chapter_code",
            name="uq_curriculum_chapter_version",
        ),
    )
    op.create_table(
        "question_chapter_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("curriculum_chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reviewer_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("question_id", "chapter_id", name="uq_question_chapter_mapping"),
    )
    op.create_table(
        "diagnostic_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("curriculum_chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("attempts.id", ondelete="SET NULL")),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float()),
        sa.Column("confidence", sa.Float()),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="not_enough_evidence"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("curriculum_chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float()),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("diagnostic_evidence")
    op.drop_table("question_chapter_mappings")
    op.drop_table("curriculum_chapters")
