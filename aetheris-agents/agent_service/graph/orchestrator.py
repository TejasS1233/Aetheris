from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from agent_service.agents.role_agent import RoleAgent
from agent_service.models.schema import AgentVote, CommandEvent, ExceptionEvent
from agent_service.tools.registry import ToolRegistry


class InvestigationState(TypedDict):
    event: ExceptionEvent
    votes: list[AgentVote]
    action: str
    reason: str


class Orchestrator:
    def __init__(self) -> None:
        self.registry = ToolRegistry()
        self.analyst = RoleAgent(
            name="Analyst",
            role="Pattern recognition and fraud signal analysis.",
            registry=self.registry,
        )
        self.auditor = RoleAgent(
            name="Auditor",
            role="Compliance and regulatory risk checks.",
            registry=self.registry,
        )
        self.strategist = RoleAgent(
            name="Strategist",
            role="Loss prevention and action planning.",
            registry=self.registry,
        )
        self.graph = self._build_graph()

    def _broadcast(self, state: InvestigationState) -> InvestigationState:
        event = state["event"]
        votes = [
            self.analyst.vote(event),
            self.auditor.vote(event),
            self.strategist.vote(event),
        ]
        return {**state, "votes": votes}

    def _consensus(self, state: InvestigationState) -> InvestigationState:
        votes = state["votes"]
        block_count = len([v for v in votes if v.decision == "BLOCK"])
        approve_count = len([v for v in votes if v.decision == "APPROVE"])

        if block_count >= 2:
            action = "BLOCK"
            reason = "2/3 consensus reached for BLOCK"
            self.registry.execute("kill_switch", {"accountId": state["event"].account_origin})
        elif approve_count >= 2:
            action = "APPROVE"
            reason = "2/3 consensus reached for APPROVE"
        else:
            action = "REVIEW"
            reason = "No majority; escalated for review"
        return {**state, "action": action, "reason": reason}

    def _build_graph(self):
        graph = StateGraph(InvestigationState)
        graph.add_node("broadcast", self._broadcast)
        graph.add_node("consensus", self._consensus)
        graph.set_entry_point("broadcast")
        graph.add_edge("broadcast", "consensus")
        graph.add_edge("consensus", END)
        return graph.compile()

    def investigate(self, event: ExceptionEvent) -> CommandEvent:
        final = self.graph.invoke({"event": event, "votes": [], "action": "REVIEW", "reason": ""})
        return CommandEvent(
            account_origin=event.account_origin,
            transaction_id=event.transaction_id,
            action=final["action"],
            votes=final["votes"],
            reason=final["reason"],
            timestamp=event.timestamp,
        )
