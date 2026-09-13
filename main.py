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

scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

# グローバルキルスイッチ状態 (メモリ保持 + DB共有)
IS_KILLED: bool = False


# ==========================================
# 1. ライフサイクル ＆ 定時バックグラウンドタスク (APScheduler)
# ==========================================

async def run_daily_autonomous_workflow():
    """
    毎朝 09:00 JST に自動実行される日次スカウト＆意思決定＆発注パイプライン
    """
    global IS_KILLED
    if IS_KILLED or repository.get_kill_switch_status():
        logger.warning("[Cron] キルスイッチ作動中のため、日次ワークフローをスキップします。")
        return

    logger.info("[Cron] 日次スカウト・ディベートワークフローを開始します。")

    try:
        # Step 1: トレンドスカウト & capability_rules DB による事前フィルタ処理
        candidates = scout_engine.scout_opportunities()
        logger.info(f"[Cron] 検出された適合候補タスク件数: {len(candidates)}")

        for candidate in candidates:
            if IS_KILLED or repository.get_kill_switch_status():
                logger.warning("[Cron] ループ中にキルスイッチが検出されたため中断します。")
                break

            task_id = candidate.get("task_id")
            task_type = candidate.get("task_type")
            execution_type = candidate.get("execution_type", "GATEWAY_X")
            estimated_price_jpy = candidate.get("estimated_price_jpy", 0)

            # Step 2: Gemini 3 Flash ✕ OpenRouter 2ラウンドディベート (粗利83%防衛 & ¥50,000キャップ判定)
            governance_result = debate_governance.evaluate_opportunity(candidate)
            
            if not governance_result.get("approved"):
                logger.info(f"[Cron] タスク {task_id} はガバナンス審査により却下されました。理由: {governance_result.get('reason')}")
                continue

            # Step 3: 金額分岐 & 実行ルーティング
            if estimated_price_jpy >= 50000:
                # 5万円以上 ➔ LINE Flex Message 1タップ承認カードの送信 (手動承認待ち)
                line_bot.send_approval_card(
                    task_id=task_id,
                    title=candidate.get("title", "高額タスク"),
                    amount_jpy=estimated_price_jpy,
                    reason=governance_result.get("reason", "")
                )
                logger.info(f"[Cron] タスク {task_id} は ¥50,000 超のため LINE CEO 承認待ちへルーティングしました。")
            else:
                # 5万円未満 ➔ 即時自動発注／自動実行
                execute_task_pipeline(candidate)

    except Exception as e:
        logger.error(f"[Cron] ワークフロー実行中に例外が発生しました: {str(e)}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 起動・停止時のライフサイクルイベント管理
    """
    logger.info("===========================================")
    logger.info("   カンパニーX Gateway X-OS v3.2 起動完了   ")
    logger.info("===========================================")
    
    # 毎朝 09:00 JST 定時タスクの登録
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


app = FastAPI(
    title="Company X - Autonomous Operations Platform",
    version="3.2.0",
    lifespan=lifespan
)


# ==========================================
# 2. タスク実行制御コアロジック
# ==========================================

def execute_task_pipeline(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """
    タスク種別（現場・物理 vs デジタル・内部）に応じた二輪駆動タスク実行パイプライン
    """
    task_id = candidate.get("task_id")
    task_type = candidate.get("task_type")
    execution_type = candidate.get("execution_type", "AUTO")
    payload = candidate.get("payload", {})
    amount_jpy = candidate.get("estimated_price_jpy", 0)

    # A. 内部デジタル処理 (Render完結型) の判定・実行
    if execution_type == "INTERNAL" or task_type in ["data_structuring", "research_report", "content_generation"]:
        logger.info(f"[Pipeline] 内部実行エンジン (InternalExecutor) にルーティング: {task_id}")
        
        result = internal_executor.execute_task(task_type, payload)
        
        if result.get("status") == "SUCCESS":
            # 成功時: 証跡永続化 & 高粗利ログ
            repository.save_execution_log(
                task_id=task_id,
                execution_type="INTERNAL_RENDER",
                status="EXECUTED",
                revenue_jpy=amount_jpy,
                cost_jpy=int(amount_jpy * 0.01), # 原価約1%
                gross_margin="99.0%"
            )
            line_bot.send_push_message(
                f"【完全自動完了】内部エンジンでデジタルタスク完了\n"
                f"タスクID: {task_id}\n"
                f"売上: ¥{amount_jpy:,} (粗利 99%)\n"
                f"処理時間: {result.get('execution_time_sec')}秒"
            )
            return {"status": "SUCCESS", "execution_type": "INTERNAL", "result": result}
        else:
            # 失敗時: 売上偽装を廃止し EXECUTION_FAILED を記録
            repository.save_execution_log(
                task_id=task_id,
                execution_type="INTERNAL_RENDER",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0,
                gross_margin="0.0%"
            )
            line_bot.send_push_message(f"【内部実行失敗】タスク {task_id} の処理に失敗しました。")
            return {"status": "EXECUTION_FAILED", "execution_type": "INTERNAL", "reason": result.get("error_message")}

    # B. 現場・物理タスク (Gateway X 2ステップ発注) の実行
    else:
        logger.info(f"[Pipeline] Gateway X A2A クライアントへルーティング: {task_id}")
        
        # Step 1: /mcp/v1/tools/call 見積取得
        quote_result = gateway_client.get_quote(task_id, payload)
        if not quote_result or quote_result.get("status") != "QUOTED":
            repository.save_execution_log(
                task_id=task_id,
                execution_type="GATEWAY_X",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0
            )
            return {"status": "EXECUTION_FAILED", "execution_type": "GATEWAY_X", "reason": "見積取得失敗"}

        # Step 2: /mcp/v1/tools/execute 実発注
        exec_result = gateway_client.execute_order(
            task_id=task_id,
            quote=quote_result.get("quote"),
            payment_method_id=os.getenv("GATEWAY_X_PAYMENT_METHOD_ID")
        )

        if exec_result and exec_result.get("status") == "EXECUTED":
            repository.save_execution_log(
                task_id=task_id,
                execution_type="GATEWAY_X",
                status="EXECUTED",
                revenue_jpy=amount_jpy,
                cost_jpy=int(amount_jpy * 0.17), # 83% 粗利防衛
                gross_margin="83.0%"
            )
            line_bot.send_push_message(
                f"【Gateway X 発注完了】現場実発注が完了しました。\n"
                f"タスクID: {task_id}\n"
                f"発注額: ¥{amount_jpy:,}"
            )
            return {"status": "SUCCESS", "execution_type": "GATEWAY_X", "result": exec_result}
        else:
            # バックオフ失敗等の確定エラーログ
            repository.save_execution_log(
                task_id=task_id,
                execution_type="GATEWAY_X",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0
            )
            line_bot.send_push_message(f"【Gateway X 発注失敗】タスク {task_id} の発注が失敗しました (EXECUTION_FAILED)。")
            return {"status": "EXECUTION_FAILED", "execution_type": "GATEWAY_X", "reason": "実発注実行エラー"}


# ==========================================
# 3. リクエスト/レスポンス Pydantic モデル
# ==========================================

class TaskExecuteRequest(BaseModel):
    task_id: str
    task_type: str
    execution_target: Optional[str] = "AUTO" # AUTO, GATEWAY_X, INTERNAL
    amount_jpy: int
    payload: Dict[str, Any]


# ==========================================
# 4. API エンドポイント
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def read_dashboard():
    """
    Web管理ダッシュボード表示 (dashboard.html を返却)
    """
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        return HTMLResponse(content=f"<h1>Company X Dashboard Error</h1><p>{str(e)}</p>", status_code=500)


@app.get("/api/v1/health")
async def health_check():
    """ヘルスチェック & キルスイッチ状態確認"""
    kill_status = repository.get_kill_switch_status() or IS_KILLED
    return {
        "status": "HEALTHY" if not kill_status else "STOPPED",
        "kill_switch_active": kill_status,
        "platform": "FastAPI / Render Cloud",
        "version": "v3.2.0"
    }


@app.post("/api/v1/task/execute")
async def handle_client_task(request: TaskExecuteRequest, background_tasks: BackgroundTasks):
    """
    外部クライアントからの発注を無人で受付・実行するエンドポイント
    """
    global IS_KILLED
    if IS_KILLED or repository.get_kill_switch_status():
        raise HTTPException(status_code=530, detail="システムは緊急停止中 (Kill Switch Active) です。")

    candidate = {
        "task_id": request.task_id,
        "task_type": request.task_type,
        "execution_type": request.execution_target,
        "estimated_price_jpy": request.amount_jpy,
        "payload": request.payload
    }

    # 5万円未満なら即時実行、5万円以上はバックグラウンド承認待ち
    if request.amount_jpy < 50000:
        res = execute_task_pipeline(candidate)
        return res
    else:
        line_bot.send_approval_card(
            task_id=request.task_id,
            title=f"外部リクエスト: {request.task_type}",
            amount_jpy=request.amount_jpy,
            reason="クライアントからの直接高額発注"
        )
        return {"status": "PENDING_APPROVAL", "message": "¥50,000 以上のため CEO 承認待ちに投入されました。"}


@app.post("/webhook/line")
async def line_webhook(request: Request, x_line_signature: Optional[str] = Header(None)):
    """
    LINE Messaging API Webhook (1タップ承認 / キルスイッチ「ストップ」「再開」受領)
    """
    global IS_KILLED
    body = await request.body()
    body_str = body.decode("utf-8")

    # LINE 署名検証・イベント処理
    event_data = line_bot.parse_webhook_event(body_str, x_line_signature)
    if not event_data:
        return JSONResponse(content={"status": "ok"})

    action = event_data.get("action")
    user_message = event_data.get("message", "").strip()

    # ミリ秒単位の緊急停止 (キルスイッチ) 分岐
    if user_message in ["ストップ", "STOP", "stop"]:
        IS_KILLED = True
        repository.set_kill_switch_status(True)
        line_bot.send_push_message("【緊急停止】キルスイッチが作動しました。全自動発注パイプラインを即時停止します。")
        logger.warning("[KillSwitch] LINE からの指示によりシステムが緊急停止されました。")
        return JSONResponse(content={"status": "killed"})

    elif user_message in ["再開", "RESTART", "restart"]:
        IS_KILLED = False
        repository.set_kill_switch_status(False)
        line_bot.send_push_message("【再開】キルスイッチを解除しました。自動運用を再開します。")
        logger.info("[KillSwitch] LINE からの指示によりシステムが再開されました。")
        return JSONResponse(content={"status": "resumed"})

    # 1タップ Flex Message 承認の受信処理
    if action == "APPROVE_TASK":
        task_id = event_data.get("task_id")
        logger.info(f"[LINE CEO] タスク {task_id} が CEO により承認されました。")
        
        # 承認済みタスク情報の取得と実行
        task_info = repository.get_pending_task(task_id)
        if task_info:
            execute_task_pipeline(task_info)
            line_bot.send_push_message(f"【承認完了】タスク {task_id} の発注・処理を開始しました。")

    return JSONResponse(content={"status": "ok"})


# 静的ファイル (dashboard.html 等) のマウント
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
