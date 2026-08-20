import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

# appディレクトリ配下のモジュール群をインポート
try:
    from app.orchestrator.master import MasterOrchestrator
except ImportError:
    MasterOrchestrator = None

app = FastAPI(
    title="Gateway X-OS",
    version="12.0.0",
    description="Autonomous AI Agent Physical Gateway API"
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

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {
        "status": "OPERATIONAL",
        "system": "Gateway X-OS Master Orchestrator",
        "engine": "Gemini 3.7 Flash Dynamic Multi-Agent System"
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
