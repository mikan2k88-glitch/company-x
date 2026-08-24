import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.line_bot")


class LineCeoBot:
    APPROVAL_THRESHOLD_JPY = 50000.0  # 5万円超は手動承認

    def send_daily_pnl_report(self, revenue_usd: float, profit_usd: float, margin: float) -> bool:
        message = (
            f"📊 【カンパニーX 日次P&L】\n"
            f"売上: ${revenue_usd:,.2f} | 利益: ${profit_usd:,.2f} | 粗利: {margin:.1%}"
        )
        logger.info(f"[LINE レポート送信]: {message}")
        return True

    def request_approval_if_needed(self, proposal: Dict[str, Any]) -> bool:
        cost_jpy = proposal.get("estimated_cost_jpy", 0.0)
        if cost_jpy < self.APPROVAL_THRESHOLD_JPY:
            return True  # 5万円未満は自動承認

        logger.info(f"[LINE 承認要請]: 高額案件につき要承認 (¥{cost_jpy:,.0f})")
        return False


3) SQLite データベースリポジトリ: company_x/db/company_repository.py

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
