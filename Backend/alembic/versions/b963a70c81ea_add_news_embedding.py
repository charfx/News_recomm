"""add news embedding

Revision ID: b963a70c81ea
Revises: 7c9caa97c69b
Create Date: 2026-11-15 13:25:28.474642

"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b963a70c81ea'
down_revision: Union[str, Sequence[str], None] = '7c9caa97c69b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("news", sa.Column("embedding", Vector(384), nullable=True))
    


def downgrade() -> None:
    op.drop_column("news", "embedding")
