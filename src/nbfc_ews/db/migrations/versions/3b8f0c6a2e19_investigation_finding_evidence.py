"""investigation, finding and evidence

Revision ID: 3b8f0c6a2e19
Revises: 7e2a91c4d5b8
Create Date: 2026-09-21

Every run of the agents on a case is kept: what each agent concluded, and the
exact tool results it concluded from.  Append-only - a re-investigation is a
new row, never an edit.  The model's raw conversation is deliberately not
stored: it carries borrower facts and would multiply what must be secured.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "3b8f0c6a2e19"
down_revision: str | Sequence[str] | None = "7e2a91c4d5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        create table investigation (
            id             bigserial primary key,
            case_id        text        not null references ews_case(case_id),
            as_of          date        not null,
            model          text        not null,
            status         text        not null default 'running',
            requested_by   text        not null,
            started_at     timestamptz not null default now(),
            finished_at    timestamptz,
            input_tokens   integer,
            output_tokens  integer,
            error          text,

            constraint ck_investigation_status
                check (status in ('running', 'complete', 'incomplete', 'failed')),
            -- running means not finished; anything else means finished
            constraint ck_investigation_finished
                check ((status = 'running') = (finished_at is null))
        );

        -- One paid run per case at a time: a double-click cannot start two.
        create unique index ux_investigation_one_running
            on investigation (case_id)
            where status = 'running';

        create index ix_investigation_case on investigation (case_id, id desc);

        create table finding (
            id               bigserial primary key,
            investigation_id bigint  not null references investigation(id),
            agent            text    not null,
            text             text,
            complete         boolean not null,
            turns            integer not null,
            tool_calls       integer not null,
            input_tokens     integer not null,
            output_tokens    integer not null
        );

        create index ix_finding_investigation on finding (investigation_id);

        create table evidence (
            id               bigserial primary key,
            investigation_id bigint      not null references investigation(id),
            agent            text        not null,
            tool             text        not null,
            arguments        jsonb       not null,
            ok               boolean     not null,
            reason           text,
            row_count        integer     not null,
            rows             jsonb       not null,
            recorded_at      timestamptz not null
        );

        create index ix_evidence_investigation on evidence (investigation_id);
    """)


def downgrade() -> None:
    op.execute("drop table if exists evidence")
    op.execute("drop table if exists finding")
    op.execute("drop table if exists investigation")
