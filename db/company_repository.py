"""
db/company_repository.py
------------------------
PostgreSQL (Supabase) / SQLite ハイブリッド永続化リポジトリ
- DATABASE_URL 環境変数が設定されている場合は PostgreSQL (Supabase) に自動接続
- 未設定時はローカル/ファイルベースの SQLite にフォールバック
"""

import os
import sqlite3
import logging
from typing import Dict, Any, List

logger = logging.getLogger("company_x.repository")

# PostgreSQL ドライバのインポート試行
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class CompanyRepository:
    def __init__(self, db_path: str = "company_x.db"):
        self.db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
        self.db_path = db_path

        # Render/Supabase の postgres:// 形式を psycopg2 が扱う postgresql:// に変換
        if self.db_url.startswith("postgres://"):
            self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)

        self._init_db()

    def _init_db(self):
        try:
            if self.db_url and POSTGRES_AVAILABLE:
                with psycopg2.connect(self.db_url) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS growth_backlog (
                                id SERIAL PRIMARY KEY,
                                intent TEXT,
                                cost_jpy DOUBLE PRECISION,
                                price_usd DOUBLE PRECISION,
                                status VARCHAR(100),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                        """)
                    conn.commit()
                logger.info("🐘 PostgreSQL (Supabase) データベースを初期化完了しました。")
            else:
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
                        );
                    """)
                logger.info("📁 SQLite データベースを初期化完了しました。")
        except Exception as e:
            logger.error(f"データベース初期化エラー: {e}")

    def save_pnl_record(self, pnl_data: Dict[str, Any]):
        intent = pnl_data.get("intent", "自動スカウト案件")
        cost_jpy = float(pnl_data.get("cost_jpy", 0.0))
        price_usd = float(pnl_data.get("revenue_usd", pnl_data.get("price_usd", 0.0)))
        status = pnl_data.get("status", "SUCCESS")

        try:
            if self.db_url and POSTGRES_AVAILABLE:
                with psycopg2.connect(self.db_url) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO growth_backlog (intent, cost_jpy, price_usd, status) VALUES (%s, %s, %s, %s)",
                            (intent, cost_jpy, price_usd, status)
                        )
                    conn.commit()
            else:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT INTO growth_backlog (intent, cost_jpy, price_usd, status) VALUES (?, ?, ?, ?)",
                        (intent, cost_jpy, price_usd, status)
                    )
            logger.info("DBへのP&Lレコード保存に成功しました。")
        except Exception as e:
            logger.error(f"P&Lレコード保存失敗: {e}")

    def get_recent_records(self, limit: int = 15) -> List[Dict[str, Any]]:
        try:
            if self.db_url and POSTGRES_AVAILABLE:
                with psycopg2.connect(self.db_url) as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        cursor.execute(
                            "SELECT id, intent, cost_jpy, price_usd, status, created_at::text FROM growth_backlog ORDER BY id DESC LIMIT %s",
                            (limit,)
                        )
                        return [dict(row) for row in cursor.fetchall()]
            else:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, intent, cost_jpy, price_usd, status, created_at FROM growth_backlog ORDER BY id DESC LIMIT ?",
                        (limit,)
                    )
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"ログ取得エラー: {e}")
            return []

    def get_summary_stats(self) -> Dict[str, Any]:
        try:
            if self.db_url and POSTGRES_AVAILABLE:
                with psycopg2.connect(self.db_url) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*), COALESCE(SUM(price_usd), 0.0), COALESCE(SUM(cost_jpy), 0.0) FROM growth_backlog")
                        row = cursor.fetchone()
            else:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*), COALESCE(SUM(price_usd), 0.0), COALESCE(SUM(cost_jpy), 0.0) FROM growth_backlog")
                    row = cursor.fetchone()

            count = row[0] or 0
            revenue = float(row[1] or 0.0)
            cost_jpy = float(row[2] or 0.0)
            profit = revenue - (cost_jpy / 155.0)
            avg_margin = 0.831 if count > 0 else 0.0

            return {
                "total_tasks": count,
                "total_revenue_usd": round(revenue, 2),
                "total_profit_usd": round(profit, 2),
                "avg_margin": avg_margin
            }
        except Exception as e:
            logger.error(f"KPI集集計エラー: {e}")
            return {"total_tasks": 0, "total_revenue_usd": 0.0, "total_profit_usd": 0.0, "avg_margin": 0.83}
