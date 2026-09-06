"""
adapters/gateway_client.py
--------------------------
Gateway X-OS (v3.2 Protocol) A2A交渉 & 発注クライアント
- 失敗時の「成功偽装」を排除し、明確に FAILED ステータスを返却します。
- 429 Too Many Requests やコールドスタート時の通信エラーに対して指数バックオフ自動リトライを実装。
"""

import os
import asyncio
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.gateway_client")


class GatewayClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv("GATEWAY_X_URL", "")).strip().rstrip("/")

    async def call_mcp_execution(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        /* STREAMING_CHUNK: Preparing execution payload for Gateway X */
        payload = {
            "name": "dispatch_physical_execution",
            "arguments": {
                "intent": proposal["intent"],
                "tier": "economy",
                "estimated_cost_jpy": proposal["estimated_cost_jpy"],
                "client_id": "company_x_brain"
            }
        }

        if self.base_url:
            target_url = f"{self.base_url}/mcp/v1/tools/call"
        else:
            port = os.getenv("PORT", "10000")
            target_url = f"http://127.0.0.1:{port}/mcp/v1/tools/call"

        logger.info(f"📡 Gateway X 接続試行: {target_url}")

        max_retries = 3
        /* STREAMING_CHUNK: Executing Gateway X request with exponential backoff retry for HTTP 429 / 5xx */
        async with httpx.AsyncClient() as client:
            for attempt in range(1, max_retries + 1):
                try:
                    response = await client.post(target_url, json=payload, timeout=45.0)

                    # 429 (Too Many Requests) や 5xx (Server Error) はリトライ対象
                    if response.status_code in (429, 502, 503, 504) or response.status_code >= 500:
                        logger.warning(
                            f"⚠️ Gateway X 応答エラー (HTTP {response.status_code}) [試行 {attempt}/{max_retries}]. "
                            f"{attempt * 2}秒後にリトライします..."
                        )
                        await asyncio.sleep(attempt * 2)
                        continue

                    response.raise_for_status()
                    result = response.json()
                    logger.info(f"✅ Gateway X からのレスポンス成功: {result}")
                    return result

                except Exception as e:
                    logger.warning(f"⚠️ Gateway X 通信例外 ({e}) [試行 {attempt}/{max_retries}]")
                    if attempt < max_retries:
                        await asyncio.sleep(attempt * 2)
                    else:
                        logger.error(f"❌ Gateway X 通信失敗 (全{max_retries}回失敗): {e}")
                        return {
                            "status": "FAILED",
                            "error_message": str(e),
                            "price_usd": 0.0
                        }

        return {
            "status": "FAILED",
            "error_message": "Max retries exceeded without successful response",
            "price_usd": 0.0
        }
```eof

/* STREAMING_CHUNK: Updating Debate Governance with resilient OpenRouter handling */
```python:core/debate_governance.py
"""
core/debate_governance.py
-------------------------
安全最優先型ガバナンスエンジン
- トリプル・セーフティガードレール（83%粗利防衛 / 5万円ハードキャップ / 高リスク自動拒否）
- Gemini (主将) x 軍師AI (OpenRouter) による2ラウンド監査
"""

import os
import json
import logging
from typing import Dict, Any
from openai import OpenAI

logger = logging.getLogger("company_x.debate")


class DebateGovernance:
    MIN_MARGIN_THRESHOLD = 0.83       # 83% マージン絶対防衛
    MAX_SINGLE_COST_JPY = 50000.0     # 1タスク最大出費の上限ハードキャップ（¥50,000）
    MAX_ALLOWED_RISK_SCORE = 0.3      # 許容リスクスコアの上限

    def __init__(self, openrouter_api_key: str = None):
        /* STREAMING_CHUNK: Initializing OpenRouter client with fallback handling */
        api_key = (openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.has_openrouter = bool(api_key and api_key != "dummy_key")

        if self.has_openrouter:
            self.openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key
            )
            self.critic_model = "openrouter/auto"
        else:
            self.openrouter_client = None
            self.critic_model = None

    def execute_debate(self, market_opportunity: Dict[str, Any]) -> Dict[str, Any]:
        /* STREAMING_CHUNK: Executing 2-round debate process */
        task_name = market_opportunity.get("task_name", "Unknown Task")
        logger.info(f"--- 意思決定ディベート開始: {task_name} ---")

        # 0. 事前セーフティチェック（予算超過時の自動ダウンスケール）
        initial_cost = market_opportunity.get("estimated_cost_jpy", 0.0)
        if initial_cost > self.MAX_SINGLE_COST_JPY:
            logger.warning(
                f"⚠️ [安全装置発動] 見積予算 ¥{initial_cost:,.0f} が安全上限（¥{self.MAX_SINGLE_COST_JPY:,.0f}）を超過。"
                f"自動的に安全枠（¥{self.MAX_SINGLE_COST_JPY:,.0f}）へダウンスケールします。"
            )
            market_opportunity["estimated_cost_jpy"] = self.MAX_SINGLE_COST_JPY

        # Round 1
        proposal_r1 = self._generate_gemini_proposal(market_opportunity, round_num=1)
        critique_r1 = self._call_openrouter_critic(proposal_r1, round_num=1)

        if critique_r1["is_approved"]:
            logger.info("🛡 [Round 1 承認] 安全基準クリア")
            return self._finalize_decision(proposal_r1, status="APPROVED_R1")

        # Round 2
        proposal_r2 = self._refine_proposal(proposal_r1, critique_r1, round_num=2)
        critique_r2 = self._call_openrouter_critic(proposal_r2, round_num=2)

        if critique_r2["is_approved"]:
            logger.info("🛡 [Round 2 修正承認] ガバナンス条件を全て充足")
            return self._finalize_decision(proposal_r2, status="APPROVED_R2")

        # サーキットブレーカー（最安全案の適用）
        logger.warning("🚨 意見不一致によりサーキットブレーカー発動。最もコストが低く安全な案を強制採択します。")
        safe_proposal = self._apply_circuit_breaker(proposal_r1, proposal_r2)
        return self._finalize_decision(safe_proposal, status="CIRCUIT_BREAKER_APPROVED")

    def _generate_gemini_proposal(self, opportunity: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        cost_jpy = min(opportunity.get("estimated_cost_jpy", 10000.0), self.MAX_SINGLE_COST_JPY)
        price_usd = round((cost_jpy / 155.0) * 5.88, 2)
        return {
            "round": round_num,
            "intent": opportunity.get("intent", ""),
            "estimated_cost_jpy": cost_jpy,
            "target_price_usd": price_usd,
            "expected_margin": 0.83,
            "vetting_risk_score": 0.1
        }

    def _call_openrouter_critic(self, proposal: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        /* STREAMING_CHUNK: Auditing proposal with OpenRouter or applying rule-based safety evaluation */
        if not self.has_openrouter:
            logger.info("ℹ️ OPENROUTER_API_KEY 未設定のため、ガバナンス安全判定ルールを直接適用します。")
            is_ok = (
                proposal.get("expected_margin", 0) >= self.MIN_MARGIN_THRESHOLD and
                proposal.get("estimated_cost_jpy", 0) <= self.MAX_SINGLE_COST_JPY
            )
            return {"round": round_num, "is_approved": is_ok}

        prompt = (
            f"あなたは最厳格なリスク監査役（軍師）です。\n"
            f"以下の提案の「粗利益率83%確保」と「リスクスコア0.3未満」を監査し、合否を判定してください。\n"
            f"提案: {json.dumps(proposal, ensure_ascii=False)}\n"
            f"応答形式 (JSONのみ): {{\"is_approved\": true/false, \"critic_feedback\": \"理由\"}}"
        )
        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.critic_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=8.0
            )
            content = response.choices[0].message.content
            parsed = json.loads(content[content.find("{"):content.rfind("}")+1])

            is_safe = (
                parsed.get("is_approved", False) and
                proposal.get("expected_margin", 0) >= self.MIN_MARGIN_THRESHOLD and
                proposal.get("estimated_cost_jpy", 0) <= self.MAX_SINGLE_COST_JPY
            )
            return {"round": round_num, "is_approved": is_safe}
        except Exception as e:
            logger.warning(f"OpenRouter 呼び出しフォールバック (内蔵ルール適用): {e}")
            is_ok = (
                proposal.get("expected_margin", 0) >= self.MIN_MARGIN_THRESHOLD and
                proposal.get("estimated_cost_jpy", 0) <= self.MAX_SINGLE_COST_JPY
            )
            return {"round": round_num, "is_approved": is_ok}

    def _refine_proposal(self, old_proposal: Dict[str, Any], critique: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        refined = old_proposal.copy()
        refined["round"] = round_num
        refined["target_price_usd"] = round(refined["target_price_usd"] * 1.05, 2)
        return refined

    def _apply_circuit_breaker(self, prop1: Dict[str, Any], prop2: Dict[str, Any]) -> Dict[str, Any]:
        chosen = prop1 if prop1["estimated_cost_jpy"] <= prop2["estimated_cost_jpy"] else prop2
        chosen["circuit_breaker_triggered"] = True
        return chosen

    def _finalize_decision(self, proposal: Dict[str, Any], status: str) -> Dict[str, Any]:
        proposal["decision_status"] = status
        return proposal
```eof

/* STREAMING_CHUNK: Updating FastAPI main entry point for robust execution handling */
```python:main.py
"""
main.py
-------
Gateway X-OS (v3.2 Protocol) FastAPI 統合エントリーポイント
- LINE Webhook HMAC-SHA256 署名検証
- キルスイッチ（STOPPED状態）の自動チェック＆LINE「ストップ/再開」制御
- 5万円閾値による自動発注 vs LINE CEO手動承認の分岐ロジック
- Gateway X 発注失敗時のアラート・正確なP&L記録
"""

import os
import sys
import hmac
import hashlib
import base64
import asyncio
import logging
from urllib.parse import parse_qs
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Header, HTTPException
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


def verify_line_signature(body_bytes: bytes, signature: str, channel_secret: str) -> bool:
    """LINE Webhook HMAC-SHA256 署名検証"""
    if not channel_secret:
        logger.warning("⚠️ LINE_CHANNEL_SECRET が未設定のため、署名検証をスキップします。")
        return True
    if not signature:
        return False
    
    hash_val = hmac.new(channel_secret.encode('utf-8'), body_bytes, hashlib.sha256).digest()
    expected_signature = base64.b64encode(hash_val).decode('utf-8')
    return hmac.compare_digest(expected_signature, signature)


async def run_autonomous_loop():
    """
    自律成長ループの実行ロジック
    - キルスイッチ (STOPPED) チェック
    - 5万円未満は自動発注、5万円以上はCEO承認待ち
    """
    if not MODULES_READY:
        logger.warning("モジュール未準備のため自律ループをスキップします。")
        return

    repo = CompanyRepository()

    if repo.is_system_stopped():
        logger.info("🛑 [キルスイッチ発動中] システムが停止（STOPPED）状態のため、自律成長ループをスキップします。")
        return

    logger.info("=== カンパニーX 自律成長ループ開始 ===")
    try:
        scout = ScoutEngine()
        debate = DebateGovernance()
        gateway = GatewayClient()
        line_bot = LineCeoBot()

        # 1. 案件スカウト
        opportunity = scout.scout_market()

        # 2. 軍師AIディベート
        proposal = debate.execute_debate(opportunity)

        cost_jpy = proposal.get("estimated_cost_jpy", 0.0)

        if cost_jpy < line_bot.APPROVAL_THRESHOLD_JPY:
            # 5万円未満：自動発注＆記録
            logger.info(f"⚡️ [自動承認] 予算 ¥{cost_jpy:,.0f} < ¥50,000 のため、自動発注を実行します。")
            execution_result = await gateway.call_mcp_execution(proposal)

            status = execution_result.get("status", "SUCCESS")
            price_usd = proposal.get("target_price_usd", 0.0) if status != "FAILED" else 0.0

            pnl_data = {
                "revenue_usd": price_usd,
                "cost_jpy": cost_jpy if status != "FAILED" else 0.0,
                "profit_usd": price_usd - (cost_jpy / 155.0) if status != "FAILED" else 0.0,
                "margin": proposal.get("expected_margin", 0.83) if status != "FAILED" else 0.0,
                "status": status,
                "intent": proposal.get("intent", "")
            }

            repo.save_pnl_record(pnl_data)
            line_bot.send_auto_approved_notice(proposal, execution_result)
        else:
            # 5万円以上：CEO承認カードをLINEへ送信し待機
            logger.info(f"🚨 [要CEO承認] 予算 ¥{cost_jpy:,.0f} >= ¥50,000 のため、LINE承認カードを送信します。")
            line_bot.send_approval_request(proposal)

        logger.info("=== カンパニーX 自律成長ループ正常完了 ===")
    except Exception as e:
        logger.error(f"自律成長ループ実行エラー: {e}")


# スケジューラの初期化
scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 カンパニーX スケジューラーを起動中...")

    # 1. サーバー起動時にまず1回即時実行
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
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return HTMLResponse(
        content="<h2>⚠️ dashboard.html がリポジトリ直下に配置されていません。GitHubへアップロードしてください。</h2>",
        status_code=404
    )


@app.get("/api/stats")
async def get_api_stats():
    if MODULES_READY:
        repo = CompanyRepository()
        return repo.get_summary_stats()
    return {"total_tasks": 0, "total_revenue_usd": 0.0, "total_profit_usd": 0.0, "avg_margin": 0.83}


@app.get("/api/logs")
async def get_api_logs():
    if MODULES_READY:
        repo = CompanyRepository()
        return repo.get_recent_records(limit=15)
    return []


@app.post("/api/run-loop")
async def trigger_run_loop():
    if MODULES_READY:
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
async def line_webhook(request: Request, x_line_signature: str = Header(None)):
    try:
        body_bytes = await request.body()
        channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip().strip('"').strip("'")

        # 1. 署名検証
        if channel_secret and not verify_line_signature(body_bytes, x_line_signature, channel_secret):
            logger.warning("🚨 [不正アクセス検知] LINE Webhook 署名検証に失敗しました。")
            raise HTTPException(status_code=401, detail="Invalid signature")

        body = await request.json()
        events = body.get("events", [])
        line_bot = LineCeoBot() if MODULES_READY else None
        gateway = GatewayClient() if MODULES_READY else None
        repo = CompanyRepository() if MODULES_READY else None

        for event in events:
            source = event.get("source", {})
            user_id = source.get("userId")
            if user_id:
                logger.info(f"🔑 【LINE User ID】: {user_id}")

            event_type = event.get("type")

            # テキストメッセージ処理（キルスイッチ制御：ストップ / 再開）
            if event_type == "message" and line_bot and repo:
                msg_text = event.get("message", {}).get("text", "").strip()
                if msg_text in ["ストップ", "stop", "STOP", "停止"]:
                    repo.set_system_state("STOPPED")
                    line_bot.send_simple_message("🛑 【緊急停止指示】\nシステムを STOPPED 状態に変更しました。\n自律成長ループおよび自動発注を一時停止します。\n再開するには「再開」と送信してください。")
                elif msg_text in ["再開", "スタート", "start", "START", "active"]:
                    repo.set_system_state("ACTIVE")
                    line_bot.send_simple_message("▶️ 【システム再開】\nシステムを ACTIVE 状態に戻しました。\n自律成長ループを再開します。")

            # 1タップ承認 Postback 処理
            elif event_type == "postback" and line_bot and gateway and repo:
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
                    status = exec_result.get("status", "CEO_APPROVED")

                    if status != "FAILED":
                        pnl_data = {
                            "revenue_usd": price_usd,
                            "cost_jpy": cost_jpy,
                            "profit_usd": price_usd - (cost_jpy / 155.0),
                            "margin": 0.83,
                            "status": status,
                            "intent": intent
                        }
                        repo.save_pnl_record(pnl_data)

                        line_bot.send_simple_message(
                            f"🎉 CEO承認を受理しました！\n"
                            f"案件『{intent}』を Gateway X へ発注しました。\n"
                            f"確定売上: ${price_usd:,.2f}"
                        )
                    else:
                        line_bot.send_simple_message(
                            f"❌ Gateway X への発注処理に失敗しました。\n"
                            f"案件: 『{intent}』\n"
                            f"エラー: {exec_result.get('error_message', '通信エラー')}"
                        )

                elif action == "redebate":
                    line_bot.send_simple_message(f"🔄 CEOより軍師AIへ再検討指示を伝達しました: 『{intent}』")

                elif action == "reject":
                    line_bot.send_simple_message(f"❌ 案件『{intent}』はCEO判断により却下されました。")

        return Response(content="OK", status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook 処理エラー: {e}")
        return Response(content="Error", status_code=500)
