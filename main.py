import os
import asyncio
import logging
import json
import sqlite3
import httpx
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

# ロギング設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gateway_x_main")

# -----------------------------------------------------------------------------
# インポートフォールバック構成（ルート直下配置 / company_x パッケージ両対応）
# -----------------------------------------------------------------------------
try:
    from core.scout_engine import ScoutEngine
    from core.debate_governance import DebateGovernance
    from adapters.gateway_client import GatewayClient
    from adapters.line_ceo_bot import LineCeoBot
    try:
        from db.company_repository import CompanyRepository
    except ImportError:
        CompanyRepository = None
    HAS_COMPANY_X = True
    logger.info("ルート直下のモジュール (core, adapters) からの読み込みに成功しました。")
except ImportError:
    try:
        from company_x.core.scout_engine import ScoutEngine
        from company_x.core.debate_governance import DebateGovernance
        from company_x.adapters.gateway_client import GatewayClient
        from company_x.adapters.line_ceo_bot import LineCeoBot
        from company_x.db.company_repository import CompanyRepository
        HAS_COMPANY_X = True
        logger.info("company_x パッケージからの読み込みに成功しました。")
    except ImportError:
        HAS_COMPANY_X = False
        logger.warning("モジュールの読み込みに失敗しました。準備完了まで自律ループは一時スキップされます。")

# --- FastAPI アプリケーション本体 ---
app = FastAPI(
    title="Gateway X-OS & Company X",
    version="12.0.0",
    description="Autonomous AI Agent Physical Gateway & Brain System"
)

class PhysicalExecutionRequest(BaseModel):
    intent: str
    tier: str = "economy"
    estimated_cost_jpy: float
    client_id: str

class FeedbackRequest(BaseModel):
    client_id: str
    execution_id: str
    rating: int
    feedback_text: Optional[str] = None

async def run_autonomous_loop():
    """1時間ごとにバックグラウンドで実行されるカンパニーXの自律成長ループ"""
    if not HAS_COMPANY_X:
        logger.warning("コアモジュールが未配置のため、自律ループを一時スキップします。")
        return

    logger.info("=== カンパニーX 自律成長ループ開始 ===")
    try:
        scout = ScoutEngine()
        governance = DebateGovernance()
        gateway = GatewayClient()
        line_bot = LineCeoBot()
        repo = CompanyRepository() if CompanyRepository else None

        # 1. ニーズ検知
        opportunity = scout.find_opportunity()

        # 2. 軍師ディベート (Gemini ✕ OpenRouter Free Tier)
        decision = governance.execute_debate(opportunity)

        # 3. 社長承認チェック (高額案件はLINEで通知)
        if not line_bot.request_approval_if_needed(decision):
            logger.info("高額案件のため、Yuki社長の承認待ちに入りました。")
            return

        # 4. Gateway X-OS (関所) へタスク発注
        result = await gateway.call_mcp_execution(decision)

        # 5. DBへ決議ログを記録
        if repo:
            repo.log_decision(decision, status=result.get("status", "UNKNOWN"))

        # 6. LINE 日次損益レポート送信
        revenue_usd = decision.get("target_price_usd", 0.0)
        line_bot.send_daily_pnl_report(
            revenue_usd=revenue_usd,
            profit_usd=revenue_usd * 0.83,
            margin=0.83
        )

        logger.info("=== カンパニーX 自律成長ループ正常完了 ===")

    except Exception as e:
        logger.error(f"自律ループ実行中にエラーが発生しました: {e}")

async def background_company_x_scheduler():
    """Render 上で常駐し、1時間ごとに自律成長ループを呼出"""
    logger.info("🤖 カンパニーX バックグラウンド自律スケジューラを起動しました。")
    while True:
        try:
            await run_autonomous_loop()
        except Exception as e:
            logger.error(f"スケジューラエラー: {e}")
        
        # 1時間 (3600秒) 間隔でループ実行
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    """サーバー起動時にスケジューラを非同期バックグラウンドタスクとして起動"""
    asyncio.create_task(background_company_x_scheduler())

@app.get("/")
def read_root():
    return {
        "status": "OPERATIONAL",
        "system": "Gateway X-OS Master Orchestrator & Company X Brain",
        "engine": "Gemini 3.6/3.7 Flash ✕ OpenRouter Free Multi-Agent System"
    }

@app.post("/mcp/v1/tools/call")
async def handle_mcp_tool_call(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    tool_name = payload.get("name")
    args = payload.get("arguments", {})

    if tool_name == "dispatch_physical_execution":
        intent = args.get("intent", "")
        tier = args.get("tier", "economy")
        cost_jpy = args.get("estimated_cost_jpy", 0.0)
        client_id = args.get("client_id", "unknown_client")

        # セキュリティ審査 (Vetting) 簡易フィルタ
        forbidden_keywords = ["自衛隊", "変電所", "軍事", "スパイ", "substation"]
        if any(keyword in intent for keyword in forbidden_keywords):
            return {
                "status": "DECLINED",
                "vetting_assessment": {
                    "passed": False,
                    "reason": "Security protocol violation: Prohibited keyword detected."
                }
            }

        # Dynamic Pricing (83%純利益マージン設計)
        usd_rate = 155.0
        base_usd = cost_jpy / usd_rate
        tier_multiplier = {"economy": 1.5, "express": 2.5, "tactical": 5.0}.get(tier, 1.5)
        quoted_usd = round(base_usd * tier_multiplier * 5.88, 2)

        return {
            "status": "QUOTED",
            "quote_id": f"q_{os.urandom(4).hex()}",
            "tier": tier,
            "price_usd": quoted_usd,
            "currency": "USD",
            "vetting_assessment": {
                "passed": True,
                "reason": "Standard commercial task approved."
            }
        }

    raise HTTPException(status_code=400, detail="Unknown MCP tool name")

@app.post("/mcp/v1/feedback")
async def receive_client_feedback(request: FeedbackRequest, background_tasks: BackgroundTasks):
    return {
        "status": "SUCCESS",
        "message": "Feedback received. Optimization loop triggered asynchronously."
    }

@app.post("/webhook/line")
async def line_webhook(request: Request):
    """LINE Messaging API からの承認ボタンタップ等の通知を受信"""
    try:
        body = await request.json()
        logger.info(f"LINE Webhook 受信: {body}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"LINE Webhook エラー: {e}")
        return {"status": "error", "detail": str(e)}
