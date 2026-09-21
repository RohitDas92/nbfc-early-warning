"""Probe the Responses API with one full tool round trip. Prints inputs first."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nbfc_ews.config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT

DEPLOYMENT = os.environ.get("AZURE_CHAT_DEPLOYMENT", "")
URL = f"{AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/responses"

TOOL = {
    "type": "function",
    "name": "get_dpd",
    "description": "Days past due for one loan account, as of the business date.",
    "parameters": {
        "type": "object",
        "properties": {"loan_id": {"type": "string"}},
        "required": ["loan_id"],
        "additionalProperties": False,
    },
}


def post(body: dict) -> dict:
    request = Request(
        URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()}")
        raise SystemExit(1) from exc


def main() -> None:
    print(f"url        : {URL}")
    print(f"deployment : {DEPLOYMENT!r}")
    print(f"key        : {AZURE_OPENAI_API_KEY[:6]}... ({len(AZURE_OPENAI_API_KEY)} chars)")
    print()

    history = [
        {"role": "system", "content": "You are a collections investigator. Use your tools; never guess."},
        {"role": "user", "content": "What is the DPD on loan L-1001?"},
    ]

    # store=False: nothing about this conversation is kept on Azure's side.
    first = post({"model": DEPLOYMENT, "input": history, "tools": [TOOL], "store": False})
    print("=== TURN 1 ===")
    print(json.dumps(first, indent=2))

    calls = [item for item in first["output"] if item["type"] == "function_call"]
    if not calls:
        print("\nno function_call - the model answered without the tool")
        return

    call = calls[0]
    # Rebuilt without its server id: with store=False there is nothing on the
    # server for an id to point at.
    history += [
        {
            "type": "function_call",
            "call_id": call["call_id"],
            "name": call["name"],
            "arguments": call["arguments"],
        },
        {
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": json.dumps({"ok": True, "dpd": 47}),
        },
    ]

    second = post({"model": DEPLOYMENT, "input": history, "tools": [TOOL], "store": False})
    print("\n=== TURN 2 ===")
    print(json.dumps(second, indent=2))


if __name__ == "__main__":
    main()