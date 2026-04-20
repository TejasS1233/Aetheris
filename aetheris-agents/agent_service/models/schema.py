from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Decision = Literal["APPROVE", "REVIEW", "BLOCK"]


class ExceptionEvent(BaseModel):
    transaction_id: int = Field(alias="transactionId")
    account_origin: str = Field(alias="accountOrigin")
    account_destination: str = Field(alias="accountDestination")
    amount: float
    type: int
    branch: int
    date: str
    description: str
    z_score: float = Field(alias="zScore")
    timestamp: int
    detected_by: str = Field(alias="detectedBy")


class ToolResult(BaseModel):
    tool_name: str
    output: str


class AgentVote(BaseModel):
    agent: str
    decision: Decision
    reason: str


class CommandEvent(BaseModel):
    account_origin: str
    transaction_id: int
    action: Decision
    votes: list[AgentVote]
    reason: str
    timestamp: int
