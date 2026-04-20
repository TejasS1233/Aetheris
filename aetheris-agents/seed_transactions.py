from __future__ import annotations

import csv
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

from agent_service.config.settings import settings


def main() -> None:
    load_dotenv()

    csv_path = Path(__file__).resolve().parent.parent / "data" / "transactions.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Could not find dataset at: {csv_path}")

    mongo = MongoClient(settings.mongodb_uri)
    db = mongo[settings.mongodb_database]
    coll = db["transactions"]

    coll.create_index("transactionId", unique=True)

    docs = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            docs.append(
                {
                    "transactionId": int(row["TransactionID"]),
                    "accountOrigin": row["AccountOriginID"],
                    "accountDestination": row["AccountDestinationID"],
                    "amount": float(row["Amount"]),
                    "transactionTypeId": int(row["TransactionTypeID"]),
                    "branchId": int(row["BranchID"]),
                    "transactionDate": row["TransactionDate"],
                    "description": row["Description"],
                }
            )

    inserted = 0
    skipped = 0
    for doc in docs:
        result = coll.update_one(
            {"transactionId": doc["transactionId"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
        else:
            skipped += 1

    total = coll.count_documents({})
    print(f"Seed complete. inserted={inserted}, skipped_existing={skipped}, total_in_collection={total}")


if __name__ == "__main__":
    main()
