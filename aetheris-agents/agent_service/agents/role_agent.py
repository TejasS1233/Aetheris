from __future__ import annotations

import json

from langchain_groq import ChatGroq
from pydantic import BaseModel

from agent_service.config.settings import settings
from agent_service.models.schema import AgentVote, ExceptionEvent
from agent_service.tools.registry import ToolRegistry


class ToolCall(BaseModel):
    tool: str
    args: dict


class RoleAgent:
    def __init__(self, name: str, role: str, registry: ToolRegistry) -> None:
        self.name = name
        self.role = role
        self.registry = registry
        self.llm = ChatGroq(api_key=settings.groq_api_key, model=settings.groq_model, temperature=0)

    def _tool_call_prompt(self, event: ExceptionEvent) -> str:
        return (
            "You are an agent deciding a single tool call.\n"
            f"Agent: {self.name}\nRole: {self.role}\n"
            "Available tools:\n"
            f"{self.registry.tool_descriptions()}\n\n"
            "Exception event:\n"
            f"account={event.account_origin}, amount={event.amount}, zscore={event.z_score}, "
            f"branch={event.branch}, type={event.type}\n\n"
            "Return ONLY JSON in this shape: {\"tool\":\"...\",\"args\":{...}}"
        )

    def _vote_prompt(self, event: ExceptionEvent, observation: dict) -> str:
        return (
            f"You are {self.name}. Role: {self.role}.\n"
            "Use the event and tool observation to decide APPROVE, REVIEW, or BLOCK.\n"
            "Return ONLY JSON: {\"decision\":\"APPROVE|REVIEW|BLOCK\",\"reason\":\"...\"}\n\n"
            f"Event: account={event.account_origin}, amount={event.amount}, zscore={event.z_score}\n"
            f"Observation: {json.dumps(observation)}"
        )

    def _safe_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def vote(self, event: ExceptionEvent) -> AgentVote:
        tool_response = self.llm.invoke(self._tool_call_prompt(event))
        tool_call_obj = self._safe_json(tool_response.content)

        tool_name = str(tool_call_obj.get("tool", "query_history"))
        tool_args = tool_call_obj.get("args", {"accountId": event.account_origin, "amount": event.amount})
        if not isinstance(tool_args, dict):
            tool_args = {"accountId": event.account_origin, "amount": event.amount}

        observation = self.registry.execute(tool_name, tool_args)

        vote_response = self.llm.invoke(self._vote_prompt(event, observation))
        vote_obj = self._safe_json(vote_response.content)

        decision = str(vote_obj.get("decision", "REVIEW")).upper()
        if decision not in {"APPROVE", "REVIEW", "BLOCK"}:
            decision = "REVIEW"
        reason = str(vote_obj.get("reason", "Insufficient signal, defaulting to review."))

        return AgentVote(agent=self.name, decision=decision, reason=reason)
