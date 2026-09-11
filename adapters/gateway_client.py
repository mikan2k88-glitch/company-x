"""
adapters/gateway_client.py
--------------------------
Gateway X-OS (v3.2 Protocol) A2A交渉 & 現場実発注クライアント
- 2ステップ発注プロセス:
    1. /mcp/v1/tools/call (見積・Vetting審査取得)
    2. /mcp/v1/tools/execute (現場・タスク物理実行 & 決済確定)
- 120秒タイムアウト & 指数バックオフ自動リトライ搭載
- ステータス分類: EXECUTED / QUOTED / DECLINED / NOT_FEASIBLE / COMM_ERROR
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
        """
        1. 見積取得 (/mcp/v1/tools/call)
        2. 見積承認後、現場・決済実行 (/mcp/v1/tools/execute)
        """
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
            quote_url = f"{self.base_url}/mcp/v1/tools/call"
            execute_url = f"{self.base_url}/mcp/v1/tools/execute"
        else:
            port = os.getenv("PORT", "10000")
            quote_url = f"http://127.0.0.1:{port}/mcp/v1/tools/call"
            execute_url = f"http://127.0.0.1:{port}/mcp/v1/tools/execute"

        logger.info(f"📡 Gateway X 見積請求試行: {quote_url}")

        max_retries = 3
        # タイムアウトを120秒に設定（Gateway X側のAIリトライ遅延を確実に許容）
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: 見積もり & Vetting 審査の取得
            quote_response = None
            for attempt in range(1, max_retries + 1):
                try:
                    res = await client.post(quote_url, json=payload)

                    if res.status_code in (429, 502, 503, 504):
                        logger.warning(
                            f"⚠️ Gateway X 応答一時エラー (HTTP {res.status_code}) [試行 {attempt}/{max_retries}]. "
                            f"{attempt * 3}秒後にリトライ..."
                        )
                        await asyncio.sleep(attempt * 3)
                        continue

                    if res.status_code == 403:
                        res_json = res.json()
                        return {
                            "status": "DECLINED",
                            "error_message": res_json.get("detail", "Gateway X セキュリティ/ポリシー違反により拒否されました。"),
                            "price_usd": 0.0
                        }
                    elif res.status_code == 422:
                        res_json = res.json()
                        return {
                            "status": "NOT_FEASIBLE",
                            "error_message": res_json.get("detail", "物理・技術的に実行不能と判明しました。"),
                            "price_usd": 0.0
                        }

                    res.raise_for_status()
                    quote_response = res.json()
                    logger.info(f"✅ Gateway X 見積取得成功: {quote_response}")
                    break

                except Exception as e:
                    logger.warning(f"⚠️ Gateway X 通信例外 ({e}) [試行 {attempt}/{max_retries}]")
                    if attempt < max_retries:
                        await asyncio.sleep(attempt * 3)
                    else:
                        logger.error(f"❌ Gateway X 通信失敗 (全{max_retries}回失敗): {e}")
                        return {
                            "status": "COMM_ERROR",
                            "error_message": f"通信エラー: {str(e)}",
                            "price_usd": 0.0
                        }

            if not quote_response:
                return {
                    "status": "COMM_ERROR",
                    "error_message": "見積もりの取得に失敗しました。",
                    "price_usd": 0.0
                }

            # Step 2: 現場実発注 & 実行確定 (/mcp/v1/tools/execute)
            quote_id = quote_response.get("quote_id") or quote_response.get("orchestration_event_id")

            # Gateway X側の ExecuteRequest スキーマ (client_id, quote, payment_method_id) に適合させる
            payment_method_id = os.getenv("GATEWAY_X_PAYMENT_METHOD_ID")
            exec_payload = {
                "client_id": "company_x_brain",
                "quote": quote_response,
                "payment_method_id": payment_method_id,
            }

            logger.info(f"⚡️ Gateway X 現場実発注実行 (Quote ID: {quote_id}): {execute_url}")

            try:
                exec_res = await client.post(execute_url, json=exec_payload)
                if exec_res.status_code == 200:
                    exec_data = exec_res.json()
                    logger.info(f"🎉 Gateway X 現場発注・実行完了: {exec_data}")
                    return {
                        "status": "EXECUTED",
                        "price_usd": exec_data.get("price_usd", quote_response.get("price_usd", proposal["target_price_usd"])),
                        "quote_id": quote_id,
                        "details": exec_data
                    }
                else:
                    # 422等、失敗時のログ出力と詳細ハンドリング
                    logger.error(
                        f"❌ Gateway X /execute 失敗 (HTTP {exec_res.status_code}): {exec_res.text[:500]}"
                    )
                    return {
                        "status": "QUOTED",
                        "price_usd": quote_response.get("price_usd", proposal["target_price_usd"]),
                        "quote_id": quote_id,
                        "details": quote_response,
                        "execute_error": exec_res.text[:500],
                    }
            except Exception as e:
                logger.warning(f"⚠️ /execute 呼出スキップ (QUOTED 確定として維持): {e}")
                return {
                    "status": "QUOTED",
                    "price_usd": quote_response.get("price_usd", proposal["target_price_usd"]),
                    "quote_id": quote_id,
                    "details": quote_response
                }
