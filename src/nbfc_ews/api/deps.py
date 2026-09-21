"""Everything the endpoints needs that is not the request itself.

Each is a FastAPI dependency, so a test can swap any one of them for a fake 
without touching the endpoints.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, closing
from typing import Annotated, Literal, cast

import psycopg
from fastapi import Header, HTTPException

from nbfc_ews.db.engine import connect
from nbfc_ews.domain.principal import Principal, Role
from nbfc_ews.llm.azure_openai import AzureChatModel
from nbfc_ews.llm.base import ChatModel

#Only these may be claimed through a header. "admin" maps to the database
#role that can read PII, and "batch" is nightly job - neither may be 
#asserted by whoever happens to be sending the request.

_HEADER_ROLES = {"analyst", "manager"}

ConnectionScope = Callable[[], AbstractContextManager[psycopg.Connection]]

def _unauthorised(reason: str) -> HTTPException:
    return HTTPException(status_code=401, detail=reason)

def get_principal(
        x_user_id: Annotated[str | None, Header()] = None,
        x_role: Annotated[str | None, Header()] = None,
        x_branches: Annotated[str | None, Header()] = None,
) -> Principal:
    """Who is asking.
    
    DEMO_ONLY: this trusts three request headers. In production this one
    function reads a signed Entra ID token instead - and nothing else changes.
    """

    if not x_user_id or not x_role or not x_branches:
        raise _unauthorised("X-User-id, X-Role and X-Branches are all required")
    if x_role not in _HEADER_ROLES:
        raise _unauthorised(f"role {x_role!r} cannot be claimed by a request")

    branches: tuple[int, ...] | Literal["ALL"]
    if x_branches.strip().upper() == "ALL":
        branches = "ALL"
    else:
        try:
            branches = tuple(int(part) for part in x_branches.split(",") if part.strip())
        except ValueError:
            raise _unauthorised("X-Branches must be all or numbers like 1,2") from None
        if not branches:
            raise _unauthorised("X-branches names no branch")

    return Principal(user_id=x_user_id, role=cast(Role, x_role), branch_ids=branches)

def get_conn() -> Iterator[psycopg.Connection]:
    """One connection per request, closed when the response has been sent."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()

def get_connect() -> ConnectionScope:
    """A way to open a connection of one's own - for work that outlives the request.
    
    The request's own connection is closed as soon as the response is sent,
    before any background work begins.
    """

    return lambda: closing(connect())

def get_model() -> ChatModel:
    """Built per request, never at import: importing must not need Azure settings."""
    return AzureChatModel()

