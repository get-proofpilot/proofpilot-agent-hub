"""Pydantic I/O models for RedditPilot routes.

RedditPilot exposes ~40 helper endpoints; most return free-form dicts
built by the orchestrator. These models cover the shapes the frontend
relies on explicitly.
"""
from pydantic import BaseModel


class AccountAddRequest(BaseModel):
    username: str
    password: str
    client_slug: str | None = None
    enabled: bool = True


class AccountEnabledBody(BaseModel):
    enabled: bool


class ClientUpdate(BaseModel):
    updates: dict


class ControlAction(BaseModel):
    action: str  # scan | learn | pause | resume | emergency_stop | etc.
