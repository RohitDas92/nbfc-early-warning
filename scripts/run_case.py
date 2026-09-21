"""Run the real investigation pipeline on one open case, against Azure.

    python scripts/run_case.py              # the open case with the most signals
    python scripts/run_case.py EWS-2026-06-00017

Read-only: the transaction is rolled back at the end, so nothing is written.
Costs a few model calls.
"""

import logging
import sys
import time
from datetime import date

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.supervisor import supervise
from nbfc_ews.db.engine import connect, session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.azure_openai import AzureChatModel

PRINCIPAL = Principal(user_id="run_case", role="analyst", branch_ids="ALL")

# The case with the most distinct signals is the most interesting one to watch.
_PICK = """
    select c.case_id, c.account_id, max(e.at) as as_of,
           array_agg(distinct e.signal_type) as signals
    from ews_case c
    join case_event e on e.case_id = c.case_id
    where c.state <> 'closed'
      and c.account_id is not null
      and e.signal_type is not null
      and (%(case_id)s::text is null or c.case_id = %(case_id)s)
    group by c.case_id, c.account_id
    order by count(distinct e.signal_type) desc, c.case_id
    limit 1
"""


def main() -> None:
    # The adapter logs one line per model call: id, tokens, latency. Never text.
    logging.basicConfig(level=logging.INFO, format="  %(levelname)s %(name)s: %(message)s")

    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    conn = connect()
    try:
        row = conn.execute(_PICK, {"case_id": wanted}).fetchone()
        if row is None:
            raise SystemExit(
                "no open case found - run scripts/nightly.py first to detect some"
            )
        case_id, account_id, as_of, signals = row
        as_of = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))

        print(f"case     : {case_id}")
        print(f"account  : {account_id}")
        print(f"as of    : {as_of}")
        print(f"signals  : {', '.join(signals)}")
        print()

        model = AzureChatModel()
        ctx = CaseContext(case_id=case_id, as_of=as_of)
        started = time.monotonic()

        with session(conn, PRINCIPAL) as c:
            result = supervise(
                case_id=case_id,
                account_id=account_id,
                signal_types=list(signals),
                model=model,
                ctx=ctx,
                conn=c,
                principal=PRINCIPAL,
            )

        elapsed = time.monotonic() - started

        print()
        print(f"agents run : {', '.join(result.agents_run)}")
        print(f"complete   : {result.complete}")
        print(f"tokens     : {result.input_tokens} in / {result.output_tokens} out")
        print(f"wall time  : {elapsed:.1f}s")

        for finding in result.findings:
            print()
            print(f"--- {finding.agent} ---")
            print(f"complete={finding.complete} turns={finding.turns} "
                f"tool_calls={finding.tool_calls} "
                f"tokens={finding.input_tokens}/{finding.output_tokens}")
            print(finding.text or "(no answer - turn budget ran out)")

        print()
        print("--- evidence log ---")
        for entry in ctx.entries():
            status = "ok" if entry.result.ok else f"FAILED: {entry.result.reason}"
            rows = len(entry.result.data) if entry.result.ok else 0
            print(f"  {entry.agent:<10} {entry.tool:<24} {dict(entry.arguments)} -> {status}, {rows} rows")
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()