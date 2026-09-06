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
        # STREAMING_CHUNK: Preparing execution payload for Gateway X
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
        # STREAMING_CHUNK: Executing Gateway X request with exponential backoff retry
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
