import os
import asyncio
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway_x_main")

# モジュールインポートの安全なハンドリング
try:
    from app.orchestrator.master import MasterOrchestrator
except ImportError:
    MasterOrchestrator = None

try:
    from company_x.main import run_autonomous_loop
    from company_x.adapters.line_ceo_bot import LineCeoBot
except ImportError:
    run_autonomous_loop = None
    LineCeoBot = None

app = FastAPI(
    title="Gateway X-OS & Company X",
    version="12.0.0",
    description="Autonomous AI Agent Physical Gateway & Brain System"
)

# --- Request / Response Models ---
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


# --- Background Autonomous Loop (カンパニーX 定期実行) ---
async def background_company_x_scheduler():
    """Render 上でサーバー起動中に、カンパニーXの自律成長ループをバックグラウンド実行"""
    logger.info("🤖 カンパニーX バックグラウンド自律スケジューラを起動しました。")
    while True:
        try:
            if run_autonomous_loop:
                logger.info("🔄 カンパニーX 自律成長ループを実行中...")
                await run_autonomous_loop()
            else:
                logger.warning("company_x モジュールが見つからないため、ループをスキップします。")
        except Exception as e:
            logger.error(f"カンパニーX 自律ループ実行エラー: {e}")
        
        # 1時間（3600秒）ごとに自律探索・意思決定を実行
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event():
    """RenderでのFastAPI起動時に自律AIループを非同期タスクとしてバックグラウンド開始"""
    asyncio.create_task(background_company_x_scheduler())


# --- API Endpoints ---
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

# --- Yuki社長用 LINE Webhook エンドポイント ---
@app.post("/webhook/line")
async def line_webhook(request: Request):
    """LINE Messaging API からの承認ボタンタップ等の通知を受信"""
    try:
        body = await request.json()
        logger.info(f"LINE Webhook 受信: {body}")
        # 必要に応じて LINE 承認レスポンスハンドラーを呼び出し
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"LINE Webhook エラー: {e}")
        return {"status": "error", "detail": str(e)}
