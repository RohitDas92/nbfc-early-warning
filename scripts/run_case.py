"""Detect live for one business date, then investigate one flagged account.

    python scripts/run_case.py 2026-07-01              # the most-flagged account
    python scripts/run_case.py 2026-07-01 EDU0000417   # a specific account

Does not use the cases stored in the database - it runs the detector itself,
so the detector and the agents are guaranteed to see the same business date.
Read-only: the transaction is rolled back. Costs a few model calls.
"""

import logging
import sys
import time
from collections import defaultdict
from datetime import date

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.supervisor import supervise
from nbfc_ews.db.engine import connect, session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.engine.detect import detect
from nbfc_ews.llm.azure_openai import AzureChatModel

PRINCIPAL = Principal(user_id="run_case", role="analyst", branch_ids="ALL")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/run_case.py YYYY-MM-01 [ACCOUNT_ID]")
    as_of = date.fromisoformat(sys.argv[1])
    wanted = sys.argv[2] if len(sys.argv) > 2 else None

    # One line per model call: id, tokens, latency. Never message text.
    logging.basicConfig(level=logging.INFO, format="  %(levelname)s %(name)s: %(message)s")

    conn = connect()
    try:
        run = detect(conn, as_of)
        by_account: dict[str, list] = defaultdict(list)
        for signal in run.signals:
            by_account[signal.account_id].append(signal)

        if wanted is None:
            if not by_account:
                raise SystemExit(f"the detector flagged nothing on {as_of}")
            wanted = max(by_account, key=lambda a: (len(by_account[a]), a))
        if wanted not in by_account:
            raise SystemExit(f"{wanted} was not flagged on {as_of}")

        signals = by_account[wanted]
        print(f"business date : {as_of}")
        print(f"accounts seen : {run.accounts_scanned}, flagged: {len(by_account)}")
        print(f"account       : {wanted}")
        print("detector said :")
        for s in signals:
            print(f"    {s.signal_type:<22} {s.detail}")
        print()

        ctx = CaseContext(case_id=f"ADHOC-{as_of}-{wanted}", as_of=as_of)
        started = time.monotonic()
        with session(conn, PRINCIPAL) as c:
            result = supervise(
                case_id=ctx.case_id,
                account_id=wanted,
                signal_types=sorted({s.signal_type for s in signals}),
                model=AzureChatModel(),
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
        print("--- evidence the agents saw ---")
        for entry in ctx.entries():
            status = "ok" if entry.result.ok else f"FAILED: {entry.result.reason}"
            print(f"  {entry.agent:<10} {entry.tool:<24} {dict(entry.arguments)} -> {status}")
            for row in entry.result.data[:3]:
                print(f"      {row}")
            if len(entry.result.data) > 3:
                print(f"      ... {len(entry.result.data) - 3} more rows")
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
