import os
import sys
import time
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# カンパニーX 内部モジュールのインポート
from db.company_repository import CompanyRepository
from core.scout_engine import ScoutEngine
from core.debate_governance import DebateGovernance
from adapters.gateway_client import GatewayClient
from adapters.internal_executor import InternalExecutor
from adapters.line_ceo_bot import LineCeoBot
from adapters.payment_client import PaymentClient

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("company_x.main")

# システムコンポーネントの初期化
repository = CompanyRepository()
scout_engine = ScoutEngine()
debate_governance = DebateGovernance()
gateway_client = GatewayClient()
internal_executor = InternalExecutor()
line_bot = LineCeoBot()
payment_client = PaymentClient()

scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

# グローバルキルスイッチ状態 (メモリ保持)
IS_KILLED: bool = False


def check_kill_switch() -> bool:
    """安全なキルスイッチ状態チェック"""
    if IS_KILLED:
        return True
    get_status = getattr(repository, "get_kill_switch_status", None)
    if callable(get_status):
        try:
            return get_status()
        except Exception:
            return False
    return False


def safe_send_line_push(text: str):
    """LINE 通知失敗時にメインの処理・レスポンスを停止させないためのガード付き関数"""
    try:
        send_fn = getattr(line_bot, "send_push_message", None)
        if callable(send_fn):
            send_fn(text)
        else:
            logger.info(f"[LINE Notification Bypass]: {text}")
    except Exception as e:
        logger.warning(f"LINE通知スキップ (非致死的例外): {e}")


# ==========================================
# 1. ライフサイクル ＆ 定時バックグラウンドタスク
# ==========================================

async def run_daily_autonomous_workflow():
    if check_kill_switch():
        logger.warning("[Cron] キルスイッチ作動中のため、日次ワークフローをスキップします。")
        return

    logger.info("[Cron] 日次スカウト・ディベートワークフローを開始します。")

    try:
        candidates = scout_engine.scout_opportunities()
        logger.info(f"[Cron] 検出された適合候補タスク件数: {len(candidates)}")

        for candidate in candidates:
            if check_kill_switch():
                logger.warning("[Cron] ループ中にキルスイッチが検出されたため中断します。")
                break

            task_id = candidate.get("task_id")
            estimated_price_jpy = candidate.get("estimated_price_jpy", 0)

            governance_result = debate_governance.evaluate_opportunity(candidate)
            
            if not governance_result.get("approved"):
                logger.info(f"[Cron] タスク {task_id} はガバナンス審査により却下されました。理由: {governance_result.get('reason')}")
                continue

            if estimated_price_jpy >= 50000:
                safe_send_line_push(
                    f"【要承認】タスク {task_id} (¥{estimated_price_jpy:,}) の承認が必要です。"
                )
                logger.info(f"[Cron] タスク {task_id} は LINE CEO 承認待ちへルーティングしました。")
            else:
                execute_task_pipeline(candidate)

    except Exception as e:
        logger.error(f"[Cron] ワークフロー実行中に例外が発生しました: {str(e)}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("===========================================")
    logger.info("   カンパニーX Gateway X-OS v3.2 起動完了   ")
    logger.info("===========================================")
    
    scheduler.add_job(
        run_daily_autonomous_workflow,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_workflow"
    )
    scheduler.start()
    yield
    scheduler.shutdown()
    logger.info("カンパニーX システムをシャットダウンしました。")


# Uvicorn 起動用の ASGI アプリケーションインスタンス (必須)
app = FastAPI(
    title="Company X - Autonomous Operations Platform",
    version="3.2.0",
    lifespan=lifespan
)


# ==========================================
# 2. タスク実行制御コアロジック (決済 & QA 統合)
# ==========================================

def execute_task_pipeline(candidate: Dict[str, Any]) -> Dict[str, Any]:
    task_id = candidate.get("task_id")
    task_type = candidate.get("task_type")
    execution_type = candidate.get("execution_type", "AUTO")
    payload = candidate.get("payload", {})
    amount_jpy = candidate.get("estimated_price_jpy", 0)
    payment_method_id = candidate.get("payment_method_id")

    # A. Stripe 事前与信（仮売上 / Hold）の確保
    auth_res = payment_client.authorize_payment(task_id, amount_jpy, payment_method_id)
    if auth_res.get("status") != "AUTHORIZED":
        logger.error(f"[Pipeline] タスク {task_id} のカード与信確保に失敗しました。")
        return {"status": "PAYMENT_FAILED", "reason": "クレジットカードの事前与信枠確保に失敗しました。"}

    payment_intent_id = auth_res.get("payment_intent_id")

    # B. 内部デジタル処理 (Render完結型 / 粗利99%)
    if execution_type == "INTERNAL" or task_type in ["data_structuring", "research_report", "content_generation"]:
        logger.info(f"[Pipeline] 内部実行エンジン (InternalExecutor) にルーティング: {task_id}")
        
        result = internal_executor.execute_task(task_type, payload)
        
        if result.get("status") == "SUCCESS":
            # 納品＆QA合格 ➔ Stripe 本売上確定 (Capture)
            cap_res = payment_client.capture_payment(payment_intent_id)

            repository.save_execution_log(
                task_id=task_id,
                execution_type="INTERNAL_RENDER",
                status="EXECUTED",
                revenue_jpy=amount_jpy,
                cost_jpy=int(amount_jpy * 0.01),
                gross_margin="99.0%"
            )
            safe_send_line_push(
                f"【完全自動完了】内部デジタルタスク完了＆売上確定\n"
                f"タスクID: {task_id}\n"
                f"売上確定: ¥{amount_jpy:,} (粗利 99%)\n"
                f"決済ID: {payment_intent_id}\n"
                f"処理時間: {result.get('execution_time_sec')}秒"
            )
            result["payment_status"] = cap_res.get("status")
            return {"status": "SUCCESS", "execution_type": "INTERNAL", "result": result}
        else:
            # 処理失敗 / QA検品NG ➔ 与信自動キャンセル
            payment_client.cancel_payment(payment_intent_id)

            repository.save_execution_log(
                task_id=task_id,
                execution_type="INTERNAL_RENDER",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0,
                gross_margin="0.0%"
            )
            safe_send_line_push(f"【内部実行失敗】タスク {task_id} の処理または検品に失敗したため決済をキャンセルしました。")
            return {"status": "EXECUTION_FAILED", "execution_type": "INTERNAL", "reason": result.get("error_message")}

    # C. 現場・物理タスク (Gateway X 発注 / 粗利83%)
    else:
        logger.info(f"[Pipeline] Gateway X A2A クライアントへルーティング: {task_id}")
        
        quote_result = gateway_client.get_quote(task_id, payload)
        if not quote_result or quote_result.get("status") != "QUOTED":
            payment_client.cancel_payment(payment_intent_id)
            repository.save_execution_log(
                task_id=task_id,
                execution_type="GATEWAY_X",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0
            )
            return {"status": "EXECUTION_FAILED", "execution_type": "GATEWAY_X", "reason": "見積取得失敗"}

        exec_result = gateway_client.execute_order(
            task_id=task_id,
            quote=quote_result.get("quote"),
            payment_method_id=os.getenv("GATEWAY_X_PAYMENT_METHOD_ID")
        )

        if exec_result and exec_result.get("status") == "EXECUTED":
            cap_res = payment_client.capture_payment(payment_intent_id)

            repository.save_execution_log(
                task_id=task_id,
                execution_type="GATEWAY_X",
                status="EXECUTED",
                revenue_jpy=amount_jpy,
                cost_jpy=int(amount_jpy * 0.17),
                gross_margin="83.0%"
            )
            safe_send_line_push(
                f"【Gateway X 発注完了】現場実発注完了＆売上確定\n"
                f"タスクID: {task_id}\n"
                f"発注額: ¥{amount_jpy:,}\n"
                f"決済ID: {payment_intent_id}"
            )
            exec_result["payment_status"] = cap_res.get("status")
            return {"status": "SUCCESS", "execution_type": "GATEWAY_X", "result": exec_result}
        else:
            payment_client.cancel_payment(payment_intent_id)

            repository.save_execution_log(
                task_id=task_id,
                execution_type="GATEWAY_X",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0
            )
            safe_send_line_push(f"【Gateway X 発注失敗】タスク {task_id} の発注が失敗したため決済をキャンセルしました。")
            return {"status": "EXECUTION_FAILED", "execution_type": "GATEWAY_X", "reason": "実発注実行エラー"}


# ==========================================
# 3. Pydantic リクエストモデル
# ==========================================

class TaskExecuteRequest(BaseModel):
    task_id: str
    task_type: str
    execution_target: Optional[str] = "AUTO"
    amount_jpy: int
    payload: Dict[str, Any]
    payment_method_id: Optional[str] = None


# ==========================================
# 4. API エンドポイント
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def read_dashboard():
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        return HTMLResponse(content=f"<h1>Company X Dashboard Error</h1><p>{str(e)}</p>", status_code=500)


@app.get("/api/v1/health")
async def health_check():
    killed = check_kill_switch()
    return {
        "status": "HEALTHY" if not killed else "STOPPED",
        "kill_switch_active": killed,
        "platform": "FastAPI / Render Cloud",
        "version": "v3.2.0"
    }


@app.post("/api/v1/task/execute")
async def handle_client_task(request: TaskExecuteRequest):
    if check_kill_switch():
        raise HTTPException(status_code=530, detail="システムは緊急停止中 (Kill Switch Active) です。")

    candidate = {
        "task_id": request.task_id,
        "task_type": request.task_type,
        "execution_type": request.execution_target,
        "estimated_price_jpy": request.amount_jpy,
        "payload": request.payload,
        "payment_method_id": request.payment_method_id
    }

    try:
        if request.amount_jpy < 50000:
            res = execute_task_pipeline(candidate)
            return res
        else:
            safe_send_line_push(
                f"【要承認】外部より ¥{request.amount_jpy:,} の高額発注を受領しました (ID: {request.task_id})。"
            )
            return {"status": "PENDING_APPROVAL", "message": "¥50,000 以上のため CEO 承認待ちに投入されました。"}
    except Exception as e:
        logger.error(f"[TaskExecuteError] エラー詳細: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "ERROR", "error_type": type(e).__name__, "detail": str(e)}
        )


@app.post("/webhook/line")
async def line_webhook(request: Request, x_line_signature: Optional[str] = Header(None)):
    global IS_KILLED
    body = await request.body()
    body_str = body.decode("utf-8")

    event_data = line_bot.parse_webhook_event(body_str, x_line_signature)
    if not event_data:
        return JSONResponse(content={"status": "ok"})

    action = event_data.get("action")
    user_message = event_data.get("message", "").strip()

    if user_message in ["ストップ", "STOP", "stop"]:
        IS_KILLED = True
        set_status = getattr(repository, "set_kill_switch_status", None)
        if callable(set_status):
            set_status(True)
        safe_send_line_push("【緊急停止】キルスイッチが作動しました。全自動発注パイプラインを即時停止します。")
        return JSONResponse(content={"status": "killed"})

    elif user_message in ["再開", "RESTART", "restart"]:
        IS_KILLED = False
        set_status = getattr(repository, "set_kill_switch_status", None)
        if callable(set_status):
            set_status(False)
        safe_send_line_push("【再開】キルスイッチを解除しました。自動運用を再開します。")
        return JSONResponse(content={"status": "resumed"})

    if action == "APPROVE_TASK":
        task_id = event_data.get("task_id")
        task_info = repository.get_pending_task(task_id)
        if task_info:
            execute_task_pipeline(task_info)
            safe_send_line_push(f"【承認完了】タスク {task_id} の発注・処理を開始しました。")

    return JSONResponse(content={"status": "ok"})


if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
