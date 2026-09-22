"""Case queue and case page - a thin screen over the API.

    streamlit run ui/app.py

This file imports nothing from nbfc_ews.  It talks to the API over HTTP and
nothing else, so every permission check happens where it belongs: in the API.
Swapping this screen for React later changes nothing underneath.
"""

import os
from typing import Any

import httpx
import streamlit as st

API_URL = os.environ.get("EWS_API_URL", "http://127.0.0.1:8000")

# DEMO ONLY: stands in for a real sign-in.  The API trusts these headers today;
# with Entra ID the screen would send a signed token instead, and this list goes.
USERS: dict[str, dict[str, str]] = {
    "Manager - all branches": {"X-User-Id": "manager-1", "X-Role": "manager", "X-Branches": "ALL"},
    "Analyst - branch 1": {"X-User-Id": "analyst-1", "X-Role": "analyst", "X-Branches": "1"},
    "Analyst - branch 2": {"X-User-Id": "analyst-2", "X-Role": "analyst", "X-Branches": "2"},
}

STATES = ["open", "investigating", "awaiting_review", "escalated", "snoozed", "closed"]

ERRORS = {
    401: "Not signed in",
    404: "Not found - or not in your branches",
    409: "Not possible right now",
}


# --- talking to the API -------------------------------------------------------


def call(method: str, path: str, **kwargs: Any) -> httpx.Response | None:
    """One API call as the signed-in user.  None, with an error shown, if unreachable."""
    try:
        return httpx.request(
            method, f"{API_URL}{path}", headers=st.session_state.headers, timeout=15, **kwargs
        )
    except httpx.HTTPError as exc:
        st.error(f"Cannot reach the API at {API_URL}. Is uvicorn running? ({exc})")
        return None


def show_error(response: httpx.Response) -> None:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    label = ERRORS.get(response.status_code, "Error")
    st.error(f"{label} ({response.status_code}): {detail}")


def safe_markdown(text: str) -> str:
    """Model text shown as markdown.  A '$' would otherwise be read as maths."""
    return text.replace("$", "\\$")


# --- the queue ----------------------------------------------------------------


def queue() -> None:
    st.title("Case queue")

    left, right = st.columns(2)
    state = left.selectbox("State", ["all", *STATES], index=1)
    limit = right.slider("Show up to", min_value=10, max_value=500, value=100, step=10)

    params: dict[str, Any] = {"limit": limit}
    if state != "all":
        params["state"] = state

    response = call("GET", "/cases", params=params)
    if response is None:
        return
    if response.status_code != 200:
        show_error(response)
        return

    cases = response.json()
    if not cases:
        st.info("No cases match.")
        return

    st.caption(f"{len(cases)} cases, newest first. Select a row to open it.")
    rows = [
        {
            "Case": c["case_id"],
            "Account": c["account_id"],
            "Type": c["case_type"],
            "State": c["state"],
            "Opened": c["opened_at"],
            "Signals": ", ".join(c["signals"]),
        }
        for c in cases
    ]
    picked = st.dataframe(
        rows, hide_index=True, on_select="rerun", selection_mode="single-row", key="queue"
    )
    if picked.selection.rows:
        st.query_params["case"] = cases[picked.selection.rows[0]]["case_id"]
        st.rerun()


# --- one case -----------------------------------------------------------------


def case_page(case_id: str) -> None:
    if st.button("Back to queue"):
        st.query_params.clear()
        st.session_state.pop("queue", None)  # forget the row, or it reopens at once
        st.rerun()

    response = call("GET", f"/cases/{case_id}")
    if response is None:
        return
    if response.status_code != 200:
        show_error(response)
        return

    case = response.json()
    summary = case["summary"]

    st.title(case_id)
    a, b, c, d = st.columns(4)
    a.metric("State", summary["state"])
    b.metric("Account", summary["account_id"])
    c.metric("Type", summary["case_type"])
    d.metric("Opened", summary["opened_at"])
    st.markdown("**Signals:** " + "  ".join(f"`{s}`" for s in summary["signals"]))

    with st.expander(f"Case history ({len(case['events'])} events)"):
        st.dataframe(
            [
                {
                    "Date": e["at"],
                    "Event": e["event_type"],
                    "Signal": e["signal_type"] or "",
                    "Detail": e["detail"] or "",
                    "By": e["actor"] or "",
                }
                for e in case["events"]
            ],
            hide_index=True,
        )

    st.divider()
    investigation_panel(case_id, summary["state"], case["investigation"])


def investigation_panel(case_id: str, state: str, run: dict[str, Any] | None) -> None:
    st.subheader("Investigation")

    if run is not None and run["status"] == "running":
        watch_running(case_id)
        return

    if state == "open":
        if st.button("Investigate", type="primary"):
            started = call("POST", f"/cases/{case_id}/investigations")
            if started is not None:
                if started.status_code == 202:
                    st.rerun()
                else:
                    show_error(started)
    elif run is None:
        st.info(f"This case is {state}. An investigation can only start from open.")

    if run is not None:
        show_run(run)


@st.fragment(run_every="3s")
def watch_running(case_id: str) -> None:
    """Re-checks every few seconds while the agents run; reloads the page when done."""
    response = call("GET", f"/cases/{case_id}")
    if response is None or response.status_code != 200:
        return
    run = response.json()["investigation"]
    if run is None or run["status"] != "running":
        st.rerun()
    st.info(
        f"Agents running since {run['started_at'][11:19]} UTC. "
        "This page updates by itself."
    )


def show_run(run: dict[str, Any]) -> None:
    status = run["status"]
    who = f"{run['model']}, requested by {run['requested_by']}, business date {run['as_of']}"
    if status == "failed":
        st.error(f"Failed: {run['error']}  \n{who}")
    elif status == "incomplete":
        st.warning(f"Incomplete: an agent ran out of turns before answering.  \n{who}")
    else:
        st.success(f"Complete.  \n{who}")

    if run["input_tokens"] is not None:
        st.caption(f"Tokens: {run['input_tokens']} in / {run['output_tokens']} out")

    for finding in run["findings"]:
        with st.container(border=True):
            st.markdown(
                f"**{finding['agent'].title()} agent** - "
                f"{finding['turns']} turns, {finding['tool_calls']} tool calls"
            )
            if finding["text"]:
                st.markdown(safe_markdown(finding["text"]))
            else:
                st.markdown("_No answer - the turn budget ran out._")

    if run["evidence"]:
        st.subheader("Evidence the agents used")
        for item in run["evidence"]:
            outcome = f"{item['row_count']} rows" if item["ok"] else "FAILED"
            with st.expander(f"{item['agent']} - {item['tool']} - {outcome}"):
                st.caption("Called with")
                st.json(item["arguments"])
                if item["ok"]:
                    st.dataframe(item["rows"], hide_index=True)
                else:
                    st.error(item["reason"])


# --- page ---------------------------------------------------------------------

st.set_page_config(page_title="NBFC Early Warning", layout="wide")

with st.sidebar:
    st.header("NBFC Early Warning")
    signed_in_as = st.selectbox("Signed in as", list(USERS))
    st.session_state.headers = USERS[signed_in_as]
    st.caption("Demo sign-in. Switch users to watch branch access change.")
    st.caption(f"API: {API_URL}")

opened = st.query_params.get("case")
if opened:
    case_page(opened)
else:
    queue()
