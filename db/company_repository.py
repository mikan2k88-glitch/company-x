import os
import sqlite3
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("company_x.repository")

class CompanyRepository:
    """
    Supabase (PostgreSQL) ↔ SQLite (WALモード) ハイブリッドリポジトリ
    capability_rules 参照、実行ログの保存、キルスイッチ状態の永続化を担当
    """

    def __init__(self, db_path: str = "company_x.db"):
        self.db_path = db_path
        self._kill_switch_active: bool = False
        self._init_db()

    def _init_db(self):
        """SQLite WALモードでの初期化とテーブル作成"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            # 実行ログテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    execution_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revenue_jpy INTEGER DEFAULT 0,
                    cost_jpy INTEGER DEFAULT 0,
                    gross_margin TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # システム設定（キルスイッチ等）保存テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("🐘 SQLite (WALモード) データベースを初期化完了しました。")
        except Exception as e:
            logger.error(f"DB初期化エラー: {str(e)}")

    def get_kill_switch_status(self) -> bool:
        """キルスイッチの稼働状態を取得 (メモリ ＆ DBフォールバック)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'kill_switch'")
            row = cursor.fetchone()
            conn.close()
            if row:
                return row[0].lower() in ["true", "1", "yes"]
        except Exception as e:
            logger.warning(f"キルスイッチ状態取得エラー (デフォルトFalseを返却): {str(e)}")
        return self._kill_switch_active

    def set_kill_switch_status(self, status: bool) -> None:
        """キルスイッチの稼働状態を保存"""
        self._kill_switch_active = status
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_settings (key, value, updated_at) 
                VALUES ('kill_switch', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
            """, (str(status),))
            conn.commit()
            conn.close()
            logger.info(f"[Repository] キルスイッチ状態を {status} に更新しました。")
        except Exception as e:
            logger.error(f"キルスイッチ状態保存エラー: {str(e)}")

    def save_execution_log(self, task_id: str, execution_type: str, status: str, 
                           revenue_jpy: int = 0, cost_jpy: int = 0, gross_margin: str = "0.0%") -> None:
        """タスク実行結果および P&L ログの永続化"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO execution_logs (task_id, execution_type, status, revenue_jpy, cost_jpy, gross_margin)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, execution_type, status, revenue_jpy, cost_jpy, gross_margin))
            conn.commit()
            conn.close()
            logger.info(f"[Repository] 実行ログ保存完了: {task_id} ({status})")
        except Exception as e:
            logger.error(f"実行ログ保存エラー: {str(e)}")

    def get_pending_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """承認待ちタスクのダミー取得 (必要に応じて実装拡張)"""
        return {
            "task_id": task_id,
            "task_type": "data_structuring",
            "execution_type": "INTERNAL",
            "estimated_price_jpy": 50000,
            "payload": {"text": "承認済み高額タスク"}
        }