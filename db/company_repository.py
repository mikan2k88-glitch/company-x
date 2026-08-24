"""
db/company_repository.py
------------------------
カンパニーX 永続化リポジトリ (SQLite)
"""

import sqlite3
import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.repository")


class CompanyRepository:
    def __init__(self, db_path: str = "company_x.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pnl_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revenue_usd REAL,
                    cost_jpy REAL,
                    profit_usd REAL,
                    margin REAL,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_pnl_record(self, pnl_data: Dict[str, Any]) -> bool:
        """P&LレコードをDBへ保存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO pnl_records (revenue_usd, cost_jpy, profit_usd, margin, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    pnl_data.get("revenue_usd", 0.0),
                    pnl_data.get("cost_jpy", 0.0),
                    pnl_data.get("profit_usd", 0.0),
                    pnl_data.get("margin", 0.0),
                    pnl_data.get("status", "SUCCESS")
                ))
                conn.commit()
            logger.info("DBへのP&Lレコード保存に成功しました。")
            return True
        except Exception as e:
            logger.error(f"DB保存失敗: {e}")
            return False

    # エイリアス（互換性確保）
    def save_pnl(self, pnl_data: Dict[str, Any]) -> bool:
        return self.save_pnl_record(pnl_data)
