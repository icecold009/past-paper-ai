"""record whether a paper question is real or AI generated"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_paper_question_source_type"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paper_questions",
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="real"),
    )


def downgrade() -> None:
    op.drop_column("paper_questions", "source_type")
