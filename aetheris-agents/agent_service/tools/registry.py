from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable

from pymongo import MongoClient
from redis import Redis

from agent_service.config.settings import settings


@dataclass
class Tool:
    name: str
    description: str
    execute: Callable[[dict], dict]


class ToolRegistry:
    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.mongo = MongoClient(settings.mongodb_uri)[settings.mongodb_database]
        self.transactions = self.mongo[settings.mongodb_transactions_collection]
        self.tool_audit = self.mongo[settings.mongodb_tool_audit_collection]
        self._init_indexes()
        self.tools: dict[str, Tool] = {
            "query_history": Tool(
                name="query_history",
                description="Fetches recent transactions for an account.",
                execute=self.query_history,
            ),
            "check_regulatory_flags": Tool(
                name="check_regulatory_flags",
                description="Runs rule checks for compliance.",
                execute=self.check_regulatory_flags,
            ),
            "simulate_loss_prevention": Tool(
                name="simulate_loss_prevention",
                description="Estimates potential prevented loss.",
                execute=self.simulate_loss_prevention,
            ),
            "kill_switch": Tool(
                name="kill_switch",
                description="Marks account for immediate review lock.",
                execute=self.kill_switch,
            ),
        }

    def _init_indexes(self) -> None:
        self.transactions.create_index("transactionId", unique=True)
        self.transactions.create_index("accountOrigin")
        self.tool_audit.create_index("transactionId")
        self.tool_audit.create_index(
            "createdAt",
            expireAfterSeconds=max(settings.mongodb_audit_ttl_days, 1) * 86400,
        )

    def query_history(self, args: dict) -> dict:
        account_id = str(args.get("accountId", ""))
        tx = list(
            self.transactions.find({"accountOrigin": account_id}, {"_id": 0}).limit(50)
        )
        return {"accountId": account_id, "count": len(tx), "transactions": tx[:5]}

    def check_regulatory_flags(self, args: dict) -> dict:
        amount = float(args.get("amount", 0.0))
        flags: list[str] = []
        if amount >= 10000:
            flags.append("LARGE_TRANSFER")
        if amount <= 1:
            flags.append("POTENTIAL_TEST_TRANSACTION")
        return {"flags": flags, "compliant": len(flags) == 0}

    def simulate_loss_prevention(self, args: dict) -> dict:
        amount = float(args.get("amount", 0.0))
        risk_multiplier = float(args.get("riskMultiplier", 0.35))
        prevented = round(amount * risk_multiplier, 2)
        return {"estimatedPreventedLoss": prevented}

    def kill_switch(self, args: dict) -> dict:
        account_id = str(args.get("accountId", ""))
        key = f"aetheris:account:lock:{account_id}"
        self.redis.set(key, "1", ex=3600)
        return {"accountId": account_id, "locked": True, "ttl_seconds": 3600}

    def execute(self, tool_name: str, args: dict) -> dict:
        tool = self.tools.get(tool_name)
        if tool is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            output = tool.execute(args)
            success = True
        except Exception as exc:
            output = {"error": str(exc)}
            success = False

        tx_id = args.get("transactionId")
        if tx_id is None:
            tx_id = args.get("txId")
        if tx_id is None:
            tx_id = args.get("transaction_id")

        try:
            audit_doc = {
                "tool": tool_name,
                "args": args,
                "output": output,
                "success": success,
                "transactionId": tx_id,
                "createdAt": datetime.now(timezone.utc),
            }
            self.tool_audit.insert_one(audit_doc)
        except Exception:
            # Do not fail tool execution path on audit write issues.
            pass

        return output

    def tool_descriptions(self) -> str:
        lines = []
        for tool in self.tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)
