"""add hnsw index on news embedding

Revision ID: 9a12e814ef60
Revises: b963a70c81ea
Create Date: 2026-11-15 13:40:32.873918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a12e814ef60'
down_revision: Union[str, Sequence[str], None] = 'b963a70c81ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_news_embedding_hnsw
        ON news USING hnsw (embedding vector_cosine_ops)
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_news_embedding_hnsw")