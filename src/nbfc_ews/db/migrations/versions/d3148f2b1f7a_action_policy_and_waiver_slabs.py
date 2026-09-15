"""action policy and waiver slabs

Revision ID: d3148f2b1f7a
Revises: 566b5d71cb46
Create Date: 2026-09-15 14:39:17.088229

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd3148f2b1f7a'
down_revision: str | Sequence[str] | None = '566b5d71cb46'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_policy",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("min_dpd", sa.Integer),
        sa.Column("max_dpd", sa.Integer),
        sa.Column("requires_prior", postgresql.ARRAY(sa.Text)),
        sa.Column("forbidden_when", postgresql.ARRAY(sa.Text)),
        sa.Column("authority", sa.Text),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("source_clause", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "effective_to is null or effective_to > effective_from",
            name="ck_action_policy_period",
        ),
        sa.CheckConstraint(
            "max_dpd is null or min_dpd is null or max_dpd >= min_dpd",
            name="ck_action_policy_dpd_range",
        ),
        sa.UniqueConstraint("action_type", "effective_from",
                            name="ux_action_policy_version"),
    )

    op.create_table(
        "waiver_slab",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("waiver_type", sa.Text, nullable=False),
        sa.Column("min_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("max_amount", sa.Numeric(15, 2)),
        sa.Column("authority", sa.Text, nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("source_clause", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("min_amount >= 0", name="ck_waiver_slab_min"),
        sa.CheckConstraint(
            "max_amount is null or max_amount > min_amount",
            name="ck_waiver_slab_range",
        ),
        sa.CheckConstraint(
            "effective_to is null or effective_to > effective_from",
            name="ck_waiver_slab_period",
        ),
    )


def downgrade() -> None:
    op.drop_table("waiver_slab")
    op.drop_table("action_policy")