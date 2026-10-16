"""add owner-scoped mistake review and append-only retry attempts"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_mistake_review_journey"
down_revision: Union[str, None] = "0007_scrub_orphan_generated_questions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "practice_sessions",
        sa.Column("session_type", sa.String(length=32), nullable=False, server_default="practice"),
    )
    with op.batch_alter_table("practice_answers") as batch_op:
        batch_op.add_column(
            sa.Column(
                "original_attempt_id",
                sa.Integer(),
                sa.ForeignKey(
                    "attempts.id",
                    ondelete="SET NULL",
                    name="fk_practice_answers_original_attempt_id_attempts",
                ),
            )
        )
        batch_op.add_column(sa.Column("previous_answer_revealed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_practice_answers_original_attempt_id", "practice_answers", ["original_attempt_id"])

    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "retry_of_attempt_id",
                sa.Integer(),
                sa.ForeignKey(
                    "attempts.id",
                    ondelete="SET NULL",
                    name="fk_attempts_retry_of_attempt_id_attempts",
                ),
            )
        )
        batch_op.add_column(sa.Column("retry_submission_key", sa.String(length=128)))
        batch_op.add_column(sa.Column("self_assessment", sa.String(length=32)))
    op.create_index("uq_attempt_retry_submission", "attempts", ["user_id", "retry_submission_key"], unique=True)
    op.create_index("ix_attempts_retry_of_attempt_id", "attempts", ["retry_of_attempt_id"])

    op.create_table(
        "mistake_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "original_attempt_id",
            sa.Integer(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "state IN ('open', 'revisit', 'resolved', 'reopened')",
            name="ck_mistake_review_state",
        ),
        sa.CheckConstraint(
            "source IN ('scored_miss', 'user_confirmed')",
            name="ck_mistake_review_source",
        ),
        sa.UniqueConstraint("user_id", "original_attempt_id", name="uq_mistake_review_owner_attempt"),
    )


def downgrade() -> None:
    op.drop_table("mistake_reviews")
    op.drop_index("ix_attempts_retry_of_attempt_id", table_name="attempts")
    op.drop_index("uq_attempt_retry_submission", table_name="attempts")
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_column("self_assessment")
        batch_op.drop_column("retry_submission_key")
        batch_op.drop_column("retry_of_attempt_id")
    op.drop_index("ix_practice_answers_original_attempt_id", table_name="practice_answers")
    with op.batch_alter_table("practice_answers") as batch_op:
        batch_op.drop_column("previous_answer_revealed_at")
        batch_op.drop_column("original_attempt_id")
    op.drop_column("practice_sessions", "session_type")
