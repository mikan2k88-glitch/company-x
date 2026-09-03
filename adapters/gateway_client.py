"""
adapters/gateway_client.py
--------------------------
Gateway X-OS (v3.2 Protocol) A2A交渉 & 発注クライアント
- GATEWAY_X_URL 環境変数から外部の Gateway X エンドポイントへ自動接続
"""

import os
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.gateway_client")


class GatewayClient:
    def __init__(self, base_url: str = None):
        # 環境変数 GATEWAY_X_URL が指定されている場合は優先利用
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

        # 接続先URLの設定（GATEWAY_X_URL が無ければ同一サーバー内のローカルフォールバック）
        if self.base_url:
            target_url = f"{self.base_url}/mcp/v1/tools/call"
        else:
            port = os.getenv("PORT", "10000")
            target_url = f"http://127.0.0.1:{port}/mcp/v1/tools/call"

        logger.info(f"📡 Gateway X 接続試行: {target_url}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(target_url, json=payload, timeout=12.0)
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ Gateway X からのレスポンス成功: {result}")
                return result
            except Exception as e:
                logger.warning(f"⚠️ Gateway X 通信エラー (フォールバック実行): {e}")
                return {"status": "LOCAL_EXECUTED", "price_usd": proposal["target_price_usd"]}
