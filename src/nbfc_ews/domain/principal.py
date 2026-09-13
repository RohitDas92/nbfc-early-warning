from dataclasses import dataclass
from typing import Literal

Role = Literal["analyst","manager","admin","batch"]

@dataclass(frozen=True)
class Principal:
    user_id : str
    role: Role
    branch_ids: tuple[int, ...] | Literal["ALL"]

