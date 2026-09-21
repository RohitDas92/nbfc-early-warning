"""nightly run ledger and event uniqueness

Revision ID: 7e2a91c4d5b8
Revises: cdcebbf07eec
Create Date: 2026-09-21

A business date is processed once.  The ledger row is written in the same
transaction as the cases, so a failed run leaves no row and can be retried,
and a successful run leaves one and cannot be repeated.

The unique index is defence in depth: the same event for the same case on the
same day cannot be stored twice, whoever writes it.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "7e2a91c4d5b8"
down_revision: str | Sequence[str] | None = "cdcebbf07eec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        create table nightly_run (
            as_of      date primary key,
            started_at timestamptz not null default now(),
            constraint ck_nightly_run_first_of_month check (extract(day from as_of) = 1)
        )
    """)

    # The index cannot be built while duplicates exist.  Keep the earliest of
    # each (lowest id), delete the rest.
    op.execute("""
        delete from case_event e
        using case_event keep
        where e.case_id    = keep.case_id
          and e.event_type = keep.event_type
          and e.at         = keep.at
          and e.signal_type is not distinct from keep.signal_type
          and e.id > keep.id
    """)

    # nulls not distinct: two events with no signal_type are still the same event.
    op.execute("""
        create unique index ux_case_event_once
            on case_event (case_id, event_type, at, signal_type)
            nulls not distinct
    """)


def downgrade() -> None:
    op.execute("drop index if exists ux_case_event_once")
    op.execute("drop table if exists nightly_run")
    # The deleted duplicates are not restored.  They were never correct.
