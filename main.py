"""
main.py
-------
Gateway X-OS (v3.2 Protocol) FastAPI 統合エントリーポイント
- カンパニーX Web管理ダッシュボード (/dashboard) の配信機能追加
- 毎朝 09:00 (JST) の Cron 自動実行スケジューラ組み込み
- LINE Webhook 受信・1タップ承認 (Postback) 処理
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

# カレントディレクトリを Python パスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODULES_READY = False
try:
    from core.scout_engine import ScoutEngine
    from core.debate_governance import DebateGovernance
    from adapters.gateway_client import GatewayClient
    from adapters.line_ceo_bot import LineCeoBot
    from db.company_repository import CompanyRepository

    logger.info("ルート直下のモジュール (core, adapters, db) の読み込みに成功しました。")
    MODULES_READY = True
except Exception as e:
    logger.error(f"モジュール読み込み失敗の詳細: {e}", exc_info=True)


async def run_autonomous_loop():
    """
    自律成長ループの実行ロジック
    """
    if not MODULES_READY:
        logger.warning("モジュール未準備のため自律ループをスキップします。")
        return

    logger.info("=== カンパニーX 自律成長ループ開始 ===")
    try:
        scout = ScoutEngine()
        debate = DebateGovernance()
        gateway = GatewayClient()
        line_bot = LineCeoBot()
        repo = CompanyRepository()

        # 1. 案件スカウト
        opportunity = scout.scout_market()

        # 2. 軍師AIディベート
        proposal = debate.execute_debate(opportunity)

        # 3. Gateway X-OS 見積もり/発注
        execution_result = await gateway.call_mcp_execution(proposal)

        pnl_data = {
            "revenue_usd": proposal.get("target_price_usd", 0.0),
            "cost_jpy": proposal.get("estimated_cost_jpy", 0.0),
            "profit_usd": proposal.get("target_price_usd", 0.0) - (proposal.get("estimated_cost_jpy", 0.0) / 155.0),
            "margin": proposal.get("expected_margin", 0.83),
            "status": execution_result.get("status", "SUCCESS")
        }

        # 4. DBへの記録保存
        repo.save_pnl_record(pnl_data)

        # 5. LINE通知（P&L レポート & 1タップ承認カード送信）
        line_bot.send_pnl_report(pnl_data)
        line_bot.send_approval_request(proposal)

        logger.info("=== カンパニーX 自律成長ループ正常完了 ===")
    except Exception as e:
        logger.error(f"自律成長ループ実行エラー: {e}")


# スケジューラの初期化
scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 カンパニーX スケジューラーを起動中...")

    # 1. サーバー起動時にまず1回即時実行（デバッグ & 稼働確認用）
    asyncio.create_task(run_autonomous_loop())

    # 2. 毎朝 09:00 (JST) に自動実行する Cron ジョブを追加
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
        "cron": "Active at 09:00 JST",
        "dashboard": "/dashboard"
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """
    Web管理ダッシュボードUI (dashboard.html) を返却するエンドポイント
    """
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return HTMLResponse(
        content="<h2>⚠️ dashboard.html がリポジトリ直下に配置されていません。GitHubへアップロードしてください。</h2>",
        status_code=404
    )


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
    try:
        body = await request.json()
        events = body.get("events", [])
        line_bot = LineCeoBot() if MODULES_READY else None
        gateway = GatewayClient() if MODULES_READY else None
        repo = CompanyRepository() if MODULES_READY else None

        for event in events:
            source = event.get("source", {})
            user_id = source.get("userId")
            if user_id:
                logger.info(f"🔑 【検出された LINE_ADMIN_USER_ID】: {user_id}")

            if event.get("type") == "postback" and line_bot:
                postback_data = event.get("postback", {}).get("data", "")
                params = {k: v[0] for k, v in parse_qs(postback_data).items()}
                action = params.get("action")
                intent = params.get("intent", "案件")

                if action == "approve":
                    cost_jpy = float(params.get("cost", 0.0))
                    price_usd = float(params.get("price", 0.0))

                    proposal = {
                        "intent": intent,
                        "estimated_cost_jpy": cost_jpy,
                        "target_price_usd": price_usd,
                        "expected_margin": 0.83
                    }
                    exec_result = await gateway.call_mcp_execution(proposal)

                    pnl_data = {
                        "revenue_usd": price_usd,
                        "cost_jpy": cost_jpy,
                        "profit_usd": price_usd - (cost_jpy / 155.0),
                        "margin": 0.83,
                        "status": exec_result.get("status", "CEO_APPROVED")
                    }
                    repo.save_pnl_record(pnl_data)

                    line_bot.send_simple_message(
                        f"🎉 CEO承認を受理しました！\n"
                        f"案件『{intent}』を Gateway X-OS へ発注しました。\n"
                        f"売上確定: ${price_usd:,.2f}"
                    )

                elif action == "redebate":
                    line_bot.send_simple_message(f"🔄 CEOより軍師AIへ再検討指示を伝達しました: 『{intent}』")

                elif action == "reject":
                    line_bot.send_simple_message(f"❌ 案件『{intent}』はCEO判断により却下されました。")

        return Response(content="OK", status_code=200)
    except Exception as e:
        logger.error(f"Webhook 処理エラー: {e}")
        return Response(content="Error", status_code=500)
