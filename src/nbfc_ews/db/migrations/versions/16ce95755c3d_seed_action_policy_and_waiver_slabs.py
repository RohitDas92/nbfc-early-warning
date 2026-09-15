"""seed action policy and waiver slabs

Revision ID: 16ce95755c3d
Revises: d3148f2b1f7a
Create Date: 2026-09-15 14:42:20.012756

"""
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '16ce95755c3d'
down_revision: str | Sequence[str] | None = 'd3148f2b1f7a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROM = date(2019, 1, 1)

action_policy = sa.table(
    "action_policy",
    sa.column("action_type", sa.Text),
    sa.column("min_dpd", sa.Integer),
    sa.column("max_dpd", sa.Integer),
    sa.column("requires_prior", postgresql.ARRAY(sa.Text)),
    sa.column("forbidden_when", postgresql.ARRAY(sa.Text)),
    sa.column("authority", sa.Text),
    sa.column("effective_from", sa.Date),
    sa.column("source_clause", sa.Text),
)

waiver_slab = sa.table(
    "waiver_slab",
    sa.column("waiver_type", sa.Text),
    sa.column("min_amount", sa.Numeric),
    sa.column("max_amount", sa.Numeric),
    sa.column("authority", sa.Text),
    sa.column("effective_from", sa.Date),
    sa.column("source_clause", sa.Text),
)


def upgrade() -> None:
    op.bulk_insert(action_policy, [
        {"action_type": "SOFT_CONTACT_BORROWER", "min_dpd": 0, "max_dpd": None,
         "requires_prior": [], "forbidden_when": [],
         "authority": "analyst", "effective_from": FROM,
         "source_clause": "Collections SOP 3.1"},

        {"action_type": "MANDATE_REPAIR", "min_dpd": 0, "max_dpd": None,
         "requires_prior": [], "forbidden_when": [],
         "authority": "analyst", "effective_from": FROM,
         "source_clause": "Collections SOP 3.2"},

        {"action_type": "PAYMENT_DATE_CHANGE", "min_dpd": 0, "max_dpd": 60,
         "requires_prior": [], "forbidden_when": [],
         "authority": "analyst", "effective_from": FROM,
         "source_clause": "Collections SOP 3.3"},

        {"action_type": "CONTACT_CO_APPLICANT", "min_dpd": 1, "max_dpd": None,
         "requires_prior": ["SOFT_CONTACT_BORROWER"], "forbidden_when": [],
         "authority": "analyst", "effective_from": FROM,
         "source_clause": "Collections SOP 3.4"},

        {"action_type": "MORATORIUM_EXTENSION", "min_dpd": 0, "max_dpd": 30,
         "requires_prior": [], "forbidden_when": [],
         "authority": "manager", "effective_from": FROM,
         "source_clause": "Restructuring policy 2.1"},

        {"action_type": "TENURE_EXTENSION", "min_dpd": 30, "max_dpd": 90,
         "requires_prior": [], "forbidden_when": ["in_moratorium"],
         "authority": "manager", "effective_from": FROM,
         "source_clause": "Restructuring policy 2.2"},

        {"action_type": "HANDOVER_TO_COLLECTIONS", "min_dpd": 30, "max_dpd": None,
         "requires_prior": ["SOFT_CONTACT_BORROWER", "CONTACT_CO_APPLICANT"],
         "forbidden_when": ["in_moratorium"],
         "authority": "manager", "effective_from": FROM,
         "source_clause": "Collections SOP 5.1"},

        {"action_type": "FIELD_VISIT", "min_dpd": 45, "max_dpd": None,
         "requires_prior": ["CONTACT_CO_APPLICANT"],
         "forbidden_when": ["in_moratorium"],
         "authority": "manager", "effective_from": FROM,
         "source_clause": "Collections SOP 5.2"},

        # authority is null: it comes from waiver_slab, by amount.
        {"action_type": "SETTLEMENT", "min_dpd": 91, "max_dpd": None,
         "requires_prior": ["HANDOVER_TO_COLLECTIONS"],
         "forbidden_when": ["in_moratorium"],
         "authority": None, "effective_from": FROM,
         "source_clause": "Settlement policy 1.1"},
    ])

    # Interest only. There is deliberately no row for principal:
    # no slab means no authority, and no authority means denied.
    op.bulk_insert(waiver_slab, [
        {"waiver_type": "interest", "min_amount": 0, "max_amount": 25000,
         "authority": "manager", "effective_from": FROM,
         "source_clause": "Settlement policy 2.1"},

        {"waiver_type": "interest", "min_amount": 25000, "max_amount": 100000,
         "authority": "head", "effective_from": FROM,
         "source_clause": "Settlement policy 2.2"},

        {"waiver_type": "interest", "min_amount": 100000, "max_amount": None,
         "authority": "committee", "effective_from": FROM,
         "source_clause": "Settlement policy 2.3"},
    ])


def downgrade() -> None:
    op.execute("delete from waiver_slab where effective_from = date '2019-01-01'")
    op.execute("delete from action_policy where effective_from = date '2019-01-01'")