"""policy chunk and corpus meta

Revision ID: cdcebbf07eec
Revises: 16ce95755c3d
Create Date: 2026-09-18 20:45:56.353313

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cdcebbf07eec'
down_revision: str | Sequence[str] | None = '16ce95755c3d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create extension if not exists vector")

    op.execute("""
        create table corpus_meta (
            id      integer primary key default 1,
            version integer not null default 0,
            check (id = 1)
        )
    """)
    op.execute("insert into corpus_meta (id, version) values (1, 0)")

    op.execute("""
        create table policy_chunk (
            id             text primary key,
            doc_id         text    not null,
            section        text    not null,
            heading_path   text    not null,
            chunk_index    integer not null,
            chunk_count    integer not null,
            rule_key       text,
            source_ref     text,
            version        integer not null,
            effective_from date    not null,
            effective_to   date,
            department     text    not null,
            sensitivity    integer not null check (sensitivity between 1 and 3),
            acl_groups     text[]  not null default '{}',
            text           text    not null,
            embedding      vector(768) not null,
            embed_model    text    not null,
            tsv            tsvector generated always as (to_tsvector('english', text)) stored,
            ingested_at    timestamptz not null default now()
        )
    """)

    op.execute("create index policy_chunk_tsv_idx   on policy_chunk using gin (tsv)")
    op.execute("create index policy_chunk_eff_idx   on policy_chunk (effective_from, effective_to)")
    op.execute("create index policy_chunk_scope_idx on policy_chunk (department, sensitivity)")


def downgrade() -> None:
    op.execute("drop table if exists policy_chunk")
    op.execute("drop table if exists corpus_meta")