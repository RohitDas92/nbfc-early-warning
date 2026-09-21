"""Show one case's signals next to the raw payment rows the agent saw."""

import sys
from datetime import date

import nbfc_ews.tools  # noqa: F401  - registers the tools
from nbfc_ews.db.engine import connect, session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.registry import get

PRINCIPAL = Principal(user_id="show_case", role="analyst", branch_ids="ALL")

case_id = sys.argv[1]
conn = connect()
try:
    account_id, = conn.execute(
        "select account_id from ews_case where case_id = %s", [case_id]
    ).fetchone()

    print(f"=== detector events for {case_id} ({account_id}) ===")
    for at, signal, detail in conn.execute(
        "select at, signal_type, detail from case_event where case_id = %s order by id",
        [case_id],
    ):
        print(f"  {at}  {signal or '-':<22} {detail or ''}")

    print("\n=== get_payment_behaviour, exactly as the agent saw it ===")
    tool = get("get_payment_behaviour")
    with session(conn, PRINCIPAL) as c:
        result = tool(c, PRINCIPAL, as_of=date(2026, 6, 1), account_id=account_id, months=12)
    for row in result.data:
        print(f"  {row}")
finally:
    conn.rollback()
    conn.close()