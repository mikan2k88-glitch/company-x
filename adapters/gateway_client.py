"""
adapters/gateway_client.py
--------------------------
Gateway X-OS (v3.2 Protocol) A2A交渉 & 発注クライアント
- レスポンスの分類ロジック（QUOTED / DECLINED / NOT_FEASIBLE / COMM_ERROR）を明確化
- 指数バックオフ自動リトライを搭載
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
        async with httpx.AsyncClient() as client:
            for attempt in range(1, max_retries + 1):
                try:
                    response = await client.post(target_url, json=payload, timeout=45.0)

                    # 429 または 一時的なサーバーエラー(5xx) はリトライ
                    if response.status_code in (429, 502, 503, 504):
                        logger.warning(
                            f"⚠️ Gateway X 応答エラー (HTTP {response.status_code}) [試行 {attempt}/{max_retries}]. "
                            f"{attempt * 2}秒後にリトライします..."
                        )
                        await asyncio.sleep(attempt * 2)
                        continue

                    # HTTP Error 判定
                    if response.status_code == 403:
                        res_json = response.json()
                        return {
                            "status": "DECLINED",
                            "error_message": res_json.get("detail", "Gateway X の安全・ガバナンスポリシーにより拒否されました。"),
                            "price_usd": 0.0
                        }
                    elif response.status_code == 422:
                        res_json = response.json()
                        return {
                            "status": "NOT_FEASIBLE",
                            "error_message": res_json.get("detail", "技術的・物理的に実現不可と判定されました。"),
                            "price_usd": 0.0
                        }

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
                            "status": "COMM_ERROR",
                            "error_message": f"通信エラー (全{max_retries}回失敗): {str(e)}",
                            "price_usd": 0.0
                        }

        return {
            "status": "COMM_ERROR",
            "error_message": "リトライ上限を超過しました。",
            "price_usd": 0.0
        }
