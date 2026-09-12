"""add case and case_event tables

Revision ID: 566b5d71cb46
Revises: 
Create Date: 2026-09-12 21:54:36.076008

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '566b5d71cb46'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        create table ews_case (
            id                  bigserial primary key,
            case_id             text not null unique,
            account_id          text,
            institution_id      text,
            case_type           text not null,
            state               text not null default 'open',
            outcome             text,
            snoozed_until       date,
            closed_at           date,
            opened_at           date not null,
            predecessor_case_id text,
            created_at          timestamptz not null default now(),

            constraint ck_case_scope check (
                (account_id is not null and institution_id is null)
                or (account_id is null and institution_id is not null)
            ),
            constraint ck_case_state check (
                state in ('open','investigating','awaiting_review',
                          'snoozed','escalated','closed')
            ),
            constraint ck_case_closed_outcome check (
                state <> 'closed' or outcome is not null
            ),
            constraint ck_case_outcome check (
                outcome is null or outcome in ('resolved_benign','intervened',
                                               'escalated','no_action_authorised')
            )
        );

        create unique index ux_case_one_open_per_account
            on ews_case (account_id)
            where state <> 'closed' and account_id is not null;

        create index ix_case_state on ews_case (state);

        create table case_event (
            id            bigserial primary key,
            case_id       text not null references ews_case(case_id),
            event_type    text not null,
            at            date not null,
            signal_type   text,
            detail        text,
            outcome       text,
            snoozed_until date,
            actor         text,
            created_at    timestamptz not null default now()
        );

        create index ix_case_event_case on case_event (case_id, id);
    """)

def downgrade() -> None:
    op.execute("drop table if exists case_event")
    op.execute("drop table if exists ews_case")