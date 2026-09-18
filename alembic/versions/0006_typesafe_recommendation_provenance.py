"""record optional adaptive recommendation provenance"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_typesafe_recommendation_provenance"
down_revision: Union[str, None] = "0005_grading_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column(
        "recommendations",
        sa.Column("decision_source", sa.String(length=32), nullable=False, server_default="deterministic"),
    )
    op.add_column(
        "recommendations",
        sa.Column("decision_version", sa.String(length=64), nullable=False, server_default="deterministic-v1"),
    )
    op.add_column("recommendations", sa.Column("decision_confidence", sa.Float()))
    op.add_column("recommendations", sa.Column("provider_model", sa.String(length=128)))
    op.add_column("recommendations", sa.Column("selection_distribution", json_type))


def downgrade() -> None:
    op.drop_column("recommendations", "selection_distribution")
    op.drop_column("recommendations", "provider_model")
    op.drop_column("recommendations", "decision_confidence")
    op.drop_column("recommendations", "decision_version")
    op.drop_column("recommendations", "decision_source")
