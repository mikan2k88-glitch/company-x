"""
db/company_repository.py
------------------------
自社取引履歴・案件パイプラインのSQLite永続化モジュール (WALモード)
"""

import sqlite3
from typing import Dict, Any


class CompanyRepository:
    def __init__(self, db_path: str = "company_x.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS growth_backlog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent TEXT,
                    cost_jpy REAL,
                    price_usd REAL,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def log_decision(self, proposal: Dict[str, Any], status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO growth_backlog (intent, cost_jpy, price_usd, status) VALUES (?, ?, ?, ?)",
                (
                    proposal.get("intent", ""),
                    proposal.get("estimated_cost_jpy", 0.0),
                    proposal.get("target_price_usd", 0.0),
                    status
                )
            )
