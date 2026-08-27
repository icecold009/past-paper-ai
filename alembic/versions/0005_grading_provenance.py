"""record grading provenance and correction state on attempts"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_grading_provenance"
down_revision: Union[str, None] = "0004_access_and_practice_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attempts", sa.Column("grading_model", sa.String(length=128)))
    op.add_column(
        "attempts",
        sa.Column("grading_policy_version", sa.String(length=64), nullable=False, server_default="gemini-json-v1"),
    )
    op.add_column(
        "attempts",
        sa.Column("grading_status", sa.String(length=32), nullable=False, server_default="graded"),
    )
    op.add_column("attempts", sa.Column("correction_note", sa.Text()))
    op.add_column("attempts", sa.Column("corrected_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("attempts", "corrected_at")
    op.drop_column("attempts", "correction_note")
    op.drop_column("attempts", "grading_status")
    op.drop_column("attempts", "grading_policy_version")
    op.drop_column("attempts", "grading_model")
