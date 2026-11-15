"""create hist_impressions

Revision ID: 14efaefa3476
Revises: 9a12e814ef60
Create Date: 2026-11-15 14:35:16.377979

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14efaefa3476'
down_revision: Union[str, Sequence[str], None] = '9a12e814ef60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "hist_impressions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("impression_id", sa.Integer, nullable=False),
        sa.Column("user_id", sa.String(20), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("news_id", sa.String(20), nullable=False),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("clicked", sa.SmallInteger, nullable=False),
    )
    op.create_index("ix_hist_ts", "hist_impressions", ["ts"])
    op.create_index("ix_hist_news", "hist_impressions", ["news_id"])

def downgrade():
    op.drop_table("hist_impressions")