"""
main.py

Gateway X-OS (v3.2 Protocol) FastAPI 統合エントリーポイント

カンパニーX 自律成長ループのスケジューラ起動

LINE 1タップ承認 Postback イベントハンドリング
"""

import os
import sys
import asyncio
import logging
from urllib.parse import parse_qs
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway_x_main")

カレントディレクトリを Python パスに追加

sys.path.insert(0, os.path.dirname(os.path.abspath(file)))

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

    # 市場機会の検知 & ディベート
    opportunity = scout.scout_market()
    proposal = debate.execute_debate(opportunity)

    cost_jpy = proposal.get("estimated_cost_jpy", 0.0)

    # 5万円以上の場合は CEO の LINE 1タップ承認リクエストへ分岐
    if cost_jpy >= 50000.0:
        logger.info(f"高額案件 (¥{cost_jpy:,.0f}) のため CEO LINE 承認リクエストを送信します。")
        line_bot.send_approval_request(proposal)
        return

    # 通常案件は即時自動発注
    execution_result = await gateway.call_mcp_execution(proposal)

    pnl_data = {
        "revenue_usd": proposal.get("target_price_usd", 0.0),
        "cost_jpy": cost_jpy,
        "profit_usd": proposal.get("target_price_usd", 0.0) - (cost_jpy / 155.0),
        "margin": proposal.get("expected_margin", 0.83),
        "status": execution_result.get("status", "SUCCESS")
    }

    repo.save_pnl_record(pnl_data)
    line_bot.send_pnl_report(pnl_data)

    # 動作確認・体験用に 承認カードのデモ送信も平行実施
    line_bot.send_approval_request(proposal)

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
"""
LINE Webhook 受信: Postback (1タップ承認) イベントの非同期処理
"""
try:
body = await request.json()
events = body.get("events", [])
line_bot = LineCeoBot()
gateway = GatewayClient()
repo = CompanyRepository()

    for event in events:
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")

        if user_id:
            logger.info(f"🔑 【検出された LINE_ADMIN_USER_ID】: {user_id}")

        # 1タップ承認 (Postback) イベントハンドリング
        if event_type == "postback":
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
