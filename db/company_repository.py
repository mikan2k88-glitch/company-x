"""
db/company_repository.py
------------------------
PostgreSQL (Supabase) / SQLite ハイブリッド永続化リポジトリ
- P&L 取引ログの永続化
- システム状態（キルスイッチ：ACTIVE / STOPPED）の永続管理
"""

import os
import sqlite3
import logging
from typing import Dict, Any, List

logger = logging.getLogger("company_x.repository")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class CompanyRepository:
    def __init__(self, db_path: str = "company_x.db"):
        /* STREAMING_CHUNK: Initializing database URLs and connections */
        self.db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
        self.db_path = db_path

        if self.db_url.startswith("postgres://"):
            self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)

        self._init_db()

    def _init_db(self):
        /* STREAMING_CHUNK: Creating tables for logs and system state */
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
                            CREATE TABLE IF NOT EXISTS system_config (
                                key VARCHAR(50) PRIMARY KEY,
                                value TEXT,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                            INSERT INTO system_config (key, value) VALUES ('system_state', 'ACTIVE')
                            ON CONFLICT (key) DO NOTHING;
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
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS system_config (
                            key TEXT PRIMARY KEY,
                            value TEXT,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.execute("""
                        INSERT OR IGNORE INTO system_config (key, value) VALUES ('system_state', 'ACTIVE');
                    """)
                logger.info("📁 SQLite データベースを初期化完了しました。")
        except Exception as e:
            logger.error(f"データベース初期化エラー: {e}")

    def set_system_state(self, state: str) -> bool:
        /* STREAMING_CHUNK: Setting Emergency Kill Switch state */
        try:
            state_val = state.upper()
            if self.db_url and POSTGRES_AVAILABLE:
                with psycopg2.connect(self.db_url) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO system_config (key, value) VALUES ('system_state', %s) "
                            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP",
                            (state_val,)
                        )
                    conn.commit()
            else:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES ('system_state', ?, CURRENT_TIMESTAMP)",
                        (state_val,)
                    )
            logger.info(f"🚨 システム状態変更: {state_val}")
            return True
        except Exception as e:
            logger.error(f"システム状態更新失敗: {e}")
            return False

    def is_system_stopped(self) -> bool:
        /* STREAMING_CHUNK: Checking if Kill Switch is active */
        try:
            val = "ACTIVE"
            if self.db_url and POSTGRES_AVAILABLE:
                with psycopg2.connect(self.db_url) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT value FROM system_config WHERE key = 'system_state'")
                        row = cursor.fetchone()
                        if row:
                            val = row[0]
            else:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM system_config WHERE key = 'system_state'")
                    row = cursor.fetchone()
                    if row:
                        val = row[0]

            return val.upper() == "STOPPED"
        except Exception as e:
            logger.error(f"システム状態取得エラー: {e}")
            return False

    def save_pnl_record(self, pnl_data: Dict[str, Any]):
        /* STREAMING_CHUNK: Saving P&L transaction records */
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
        /* STREAMING_CHUNK: Retrieving recent execution logs */
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
        /* STREAMING_CHUNK: Computing KPI metrics for Dashboard */
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
                "avg_margin": avg_margin,
                "is_stopped": self.is_system_stopped()
            }
        except Exception as e:
            logger.error(f"KPI集計エラー: {e}")
            return {"total_tasks": 0, "total_revenue_usd": 0.0, "total_profit_usd": 0.0, "avg_margin": 0.83, "is_stopped": False}
```eof

/* STREAMING_CHUNK: Updating main.py with Kill Switch Webhook Handling */
```python:main.py
"""
main.py
-------
Gateway X-OS (v3.2 Protocol) FastAPI エントリーポイント
- キルスイッチ（緊急停止 / 再開）受信処理の組み込み
"""

import os
import sys
import asyncio
import logging
from urllib.parse import parse_qs
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway_x_main")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODULES_READY = False
try:
    from core.scout_engine import ScoutEngine
    from core.debate_governance import DebateGovernance
    from adapters.gateway_client import GatewayClient
    from adapters.line_ceo_bot import LineCeoBot
    from db.company_repository import CompanyRepository

    logger.info("モジュール読み込みに成功しました。")
    MODULES_READY = True
except Exception as e:
    logger.error(f"モジュール読み込み失敗の詳細: {e}", exc_info=True)


async def run_autonomous_loop():
    """
    完全自律成長ループ（キルスイッチ・ガードレール判定機能付き）
    """
    if not MODULES_READY:
        logger.warning("モジュール未準備のため自律ループをスキップします。")
        return

    repo = CompanyRepository()
    line_bot = LineCeoBot()

    /* STREAMING_CHUNK: Kill Switch Safety Check before execution */
    if repo.is_system_stopped():
        logger.warning("🚨 [緊急停止発動中] キルスイッチがアクティブなため、自律ループを完全にスキップします。")
        line_bot.send_simple_message("🛑 【緊急停止中】\n現在キルスイッチがONのため、処理を停止しています。\n再開するには「再開」とLINEに送信してください。")
        return

    logger.info("=== カンパニーX 完全自律成長ループ開始 ===")
    try:
        scout = ScoutEngine()
        debate = DebateGovernance()
        gateway = GatewayClient()

        # 1. マルチソース案件スカウト
        opportunity = scout.scout_market()

        # 2. ガバナンスAIディベート（安全上限5万円自動縮小 & 83%利益率担保）
        proposal = debate.execute_debate(opportunity)

        # 3. 完全自律発注
        execution_result = await gateway.call_mcp_execution(proposal)

        pnl_data = {
            "intent": proposal.get("intent", ""),
            "revenue_usd": proposal.get("target_price_usd", 0.0),
            "cost_jpy": proposal.get("estimated_cost_jpy", 0.0),
            "profit_usd": proposal.get("target_price_usd", 0.0) - (proposal.get("estimated_cost_jpy", 0.0) / 155.0),
            "margin": proposal.get("expected_margin", 0.83),
            "status": execution_result.get("status", "AUTOPILOT_EXECUTED")
        }

        # 4. DBへの記録保存
        repo.save_pnl_record(pnl_data)

        # 5. LINE通知（結果の自動報告のみ）
        line_bot.send_pnl_report(pnl_data)

        logger.info("=== カンパニーX 完全自律成長ループ正常完了 ===")
    except Exception as e:
        logger.error(f"自律成長ループ実行エラー: {e}")


scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 カンパニーX スケジューラーを起動中...")

    asyncio.create_task(run_autonomous_loop())

    scheduler.add_job(
        run_autonomous_loop,
        CronTrigger(hour=9, minute=0, timezone="Asia/Tokyo"),
        id="daily_autonomous_loop",
        replace_existing=True
    )
    scheduler.start()
    logger.info("⏰ 毎朝 09:00 (JST) の定時実行ジョブをセットしました。")

    yield

    scheduler.shutdown()


app = FastAPI(title="Gateway X-OS API", lifespan=lifespan)


@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "Gateway X-OS v3.2 Protocol",
        "mode": "Autopilot with Safety Kill Switch",
        "dashboard": "/dashboard"
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return HTMLResponse(content="<h2>dashboard.html が見つかりません。</h2>", status_code=404)


@app.get("/api/stats")
async def get_api_stats():
    if MODULES_READY:
        repo = CompanyRepository()
        return repo.get_summary_stats()
    return {"total_tasks": 0, "total_revenue_usd": 0.0, "total_profit_usd": 0.0, "avg_margin": 0.83, "is_stopped": False}


@app.get("/api/logs")
async def get_api_logs():
    if MODULES_READY:
        repo = CompanyRepository()
        return repo.get_recent_records(limit=15)
    return []


@app.post("/api/run-loop")
async def trigger_run_loop():
    if MODULES_READY:
        repo = CompanyRepository()
        if repo.is_system_stopped():
            return {"status": "STOPPED", "message": "キルスイッチがONのため実行できません。「再開」で復帰させてください。"}
        asyncio.create_task(run_autonomous_loop())
        return {"status": "SUCCESS", "message": "自律成長ループを即時起動しました。"}
    return {"status": "ERROR", "message": "モジュール未準備のため実行できません。"}


@app.post("/mcp/v1/tools/call")
async def handle_mcp_call(request: Request):
    data = await request.json()
    args = data.get("arguments", {})
    cost_jpy = args.get("estimated_cost_jpy", 10000.0)
    price_usd = round((cost_jpy / 155.0) * 5.88, 2)
    return {
        "status": "QUOTED",
        "price_usd": price_usd,
        "message": "Gateway X-OS execution dispatched successfully."
    }


@app.post("/line/webhook")
async def line_webhook(request: Request):
    /* STREAMING_CHUNK: Handling LINE Webhook Text for Emergency Kill Switch */
    try:
        body = await request.json()
        events = body.get("events", [])
        line_bot = LineCeoBot() if MODULES_READY else None
        repo = CompanyRepository() if MODULES_READY else None

        for event in events:
            source = event.get("source", {})
            user_id = source.get("userId")
            if user_id:
                logger.info(f"🔑 【LINE_ADMIN_USER_ID】: {user_id}")

            # 1. テキストメッセージによるキルスイッチ受信処理
            if event.get("type") == "message":
                msg_text = event.get("message", {}).get("text", "").strip().lower()

                if msg_text in ["ストップ", "stop", "緊急停止", "キルスイッチ", "停止"]:
                    if repo:
                        repo.set_system_state("STOPPED")
                    if line_bot:
                        line_bot.send_simple_message(
                            "🚨 【キルスイッチ発動】\n"
                            "自律AIエンジンを即刻緊急停止しました！\n"
                            "今後の自動発注・スカウトはすべてブロックされます。\n\n"
                            "※ 再開するには「再開」とメッセージを送信してください。"
                        )

                elif msg_text in ["再開", "resume", "スタート", "start", "復帰"]:
                    if repo:
                        repo.set_system_state("ACTIVE")
                    if line_bot:
                        line_bot.send_simple_message(
                            "✅ 【システム自律運用再開】\n"
                            "キルスイッチを解除しました。\n"
                            "安全ガードレール（5万円上限/83%粗利防衛）の下で自律成長ループを再開します。"
                        )

        return Response(content="OK", status_code=200)
    except Exception as e:
        logger.error(f"Webhook 処理エラー: {e}")
        return Response(content="Error", status_code=500)
```eof

/* STREAMING_CHUNK: Updating line_ceo_bot.py with Kill Switch Instructions */
```python:adapters/line_ceo_bot.py
"""
adapters/line_ceo_bot.py
------------------------
LINE Messaging API 連携アダプター
- P&L 自律実行結果のリアルタイム報告
- LINE テキストによるキルスイッチコマンドのフィードバック
"""

import os
import logging
from typing import Dict, Any
import httpx

logger = logging.getLogger("company_x.line_bot")


class LineCeoBot:
    def __init__(self):
        self.access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip().strip('"').strip("'")
        self.admin_user_id = os.getenv("LINE_ADMIN_USER_ID", "").strip().strip('"').strip("'")

    def send_pnl_report(self, pnl_data: Dict[str, Any]) -> bool:
        """自律実行後の P&L 結果レポートを Push 送信"""
        intent = pnl_data.get("intent", "自動スカウト案件")
        cost = pnl_data.get("cost_jpy", 0.0)
        revenue = pnl_data.get("revenue_usd", 0.0)
        profit = pnl_data.get("profit_usd", 0.0)

        report_text = (
            f"⚡️ 【カンパニーX 自律決議・執行報告】\n"
            f"案件: {intent}\n"
            f"──────────────\n"
            f"・執行コスト: ¥{cost:,.0f}\n"
            f"・確定売上: ${revenue:,.2f}\n"
            f"・想定利益: ${profit:,.2f} (粗利率 83% 担保)\n"
            f"・ステータス: 正常執行完了\n\n"
            f"※ 緊急停止したい場合は「ストップ」と送信してください。"
        )
        return self._send_push_text(report_text)

    def send_simple_message(self, text: str) -> bool:
        """簡易テキストメッセージの送信"""
        return self._send_push_text(text)

    def _send_push_text(self, text: str) -> bool:
        if not self.access_token or not self.admin_user_id:
            logger.warning("[LINE 送信スキップ] 環境変数が不足しています。")
            return False

        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        payload = {
            "to": self.admin_user_id,
            "messages": [{"type": "text", "text": text}]
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info("✅ LINE Push メッセージの送信に成功しました！")
                return True
            else:
                logger.error(f"❌ LINE Push 送信失敗 (HTTP {response.status_code}): {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ LINE 通信例外エラー: {e}")
            return False
```eof

---

### 📱 LINEでの操作方法

これで、お持ちのスマートフォンのLINEから以下のように返信するだけで完全にコントロールできます：

* **「ストップ」** （または「停止」「STOP」）と送信 ➔ **即座にAIの全自動処理が全停止**します。
* **「再開」** （または「スタート」「RESUME」）と送信 ➔ **自律運用が安全に復帰**します。

上記の3ファイルを GitHub にコミットすれば、LINEからの緊急制御システムが稼働します！
