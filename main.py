"""
main.py
-------
Gateway X-OS (v3.2 Protocol) FastAPI 統合エントリーポイント
- カンパニーX 自律成長ループのスケジューラ起動
- 柔軟なモジュールインポート & LINE Webhook / 実送信対応
"""

import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway_x_main")

# パス追加でインポートの確実性を担保
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# モジュールの柔軟な読み込み
MODULES_READY = False
try:
    try:
        from core.scout_engine import ScoutEngine
        from core.debate_governance import DebateGovernance
        from adapters.gateway_client import GatewayClient
        from adapters.line_ceo_bot import LineCeoBot
        from db.company_repository import CompanyRepository
        logger.info("ルート直下のモジュール (core, adapters) からの読み込みに成功しました。")
    except ImportError:
        from company_x.core.scout_engine import ScoutEngine
        from company_x.core.debate_governance import DebateGovernance
        from company_x.adapters.gateway_client import GatewayClient
        from company_x.adapters.line_ceo_bot import LineCeoBot
        from company_x.db.company_repository import CompanyRepository
        logger.info("company_x サブモジュールからの読み込みに成功しました。")
    
    MODULES_READY = True
except Exception as e:
    logger.error(f"モジュール読み込み重大エラー: {e}")

# 自律成長ループの定義
async def run_autonomous_loop():
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

        opportunity = scout.scan_opportunities()
        proposal = debate.execute_debate(opportunity)
        execution_result = await gateway.call_mcp_execution(proposal)

        pnl_data = {
            "revenue_usd": proposal.get("target_price_usd", 0.0),
            "cost_jpy": proposal.get("estimated_cost_jpy", 0.0),
            "profit_usd": proposal.get("target_price_usd", 0.0) - (proposal.get("estimated_cost_jpy", 0.0) / 155.0),
            "margin": proposal.get("expected_margin", 0.83),
            "status": execution_result.get("status", "SUCCESS")
        }
        repo.save_pnl(pnl_data)
        
        # LINE Push通知の呼び出し
        line_bot.send_pnl_report(pnl_data)
        logger.info("=== カンパニーX 自律成長ループ正常完了 ===")
    except Exception as e:
        logger.error(f"自律成長ループ実行エラー: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 カンパニーX バックグラウンド自律スケジューラを起動しました。")
    asyncio.create_task(run_autonomous_loop())
    yield

app = FastAPI(title="Gateway X-OS API", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "online", "system": "Gateway X-OS v3.2 Protocol"}

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
        for event in events:
            source = event.get("source", {})
            user_id = source.get("userId")
            if user_id:
                logger.info(f"🔑 【検出された LINE_ADMIN_USER_ID】: {user_id}")
        return Response(content="OK", status_code=200)
    except Exception as e:
        logger.error(f"Webhook 処理エラー: {e}")
        return Response(content="Error", status_code=500)
