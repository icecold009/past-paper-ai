"""scrub orphaned student-tailored generated questions"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_scrub_orphan_generated_questions"
down_revision: Union[str, None] = "0006_typesafe_recommendation_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    orphaned = """
        SELECT q.id
        FROM questions AS q
        WHERE q.paper = 'ai_generated'
          AND NOT EXISTS (
              SELECT 1 FROM paper_questions AS pq WHERE pq.question_id = q.id
          )
    """
    op.execute(
        sa.text(
            f"DELETE FROM mark_scheme_points WHERE question_id IN ({orphaned})"
        )
    )
    op.execute(
        sa.text(
            f"DELETE FROM question_chapter_mappings WHERE question_id IN ({orphaned})"
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE questions
            SET raw_text = '', topic = NULL, subtopic = NULL, command_word = NULL,
                difficulty = NULL, marks = NULL
            WHERE id IN ({orphaned})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DELETE FROM questions
            WHERE id IN ({orphaned})
              AND NOT EXISTS (SELECT 1 FROM attempts AS a WHERE a.question_id = questions.id)
              AND NOT EXISTS (
                  SELECT 1 FROM diagnostic_responses AS dr WHERE dr.question_id = questions.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM practice_answers AS pa WHERE pa.question_id = questions.id
              )
            """
        )
    )


def downgrade() -> None:
    """No-op: scrubbed private question text and marks cannot be restored."""
