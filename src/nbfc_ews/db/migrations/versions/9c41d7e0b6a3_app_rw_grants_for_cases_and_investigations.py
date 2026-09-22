"""app_rw grants for cases and investigations

Revision ID: 9c41d7e0b6a3
Revises: 3b8f0c6a2e19
Create Date: 2026-09-21

The service runs as app_rw so that row-level security applies.  Least
privilege: no delete anywhere, and no update on finding or evidence - so the
database itself keeps them append-only.  Skipped where the role does not
exist, e.g. a bare CI database.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "9c41d7e0b6a3"
down_revision: str | Sequence[str] | None = "3b8f0c6a2e19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        do $$
        begin
            if exists (select 1 from pg_roles where rolname = 'app_rw') then
                grant select, update         on ews_case      to app_rw;
                grant select, insert         on case_event    to app_rw;
                grant select                 on nightly_run   to app_rw;
                grant select, insert, update on investigation to app_rw;
                grant select, insert         on finding       to app_rw;
                grant select, insert         on evidence      to app_rw;
                grant usage on sequence case_event_id_seq, investigation_id_seq,
                                        finding_id_seq, evidence_id_seq to app_rw;
            end if;
        end
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        do $$
        begin
            if exists (select 1 from pg_roles where rolname = 'app_rw') then
                revoke all on ews_case, case_event, nightly_run,
                              investigation, finding, evidence from app_rw;
                revoke all on sequence case_event_id_seq, investigation_id_seq,
                                       finding_id_seq, evidence_id_seq from app_rw;
            end if;
        end
        $$;
    """)
