"""
adapters/gateway_client.py
--------------------------
Gateway X-OS (v3.2 Protocol) A2A交渉 & 発注クライアント
"""

import os
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.gateway_client")


class GatewayClient:
    def __init__(self, base_url: str = "http://127.0.0.1:10000"):
        self.base_url = base_url

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
        port = os.getenv("PORT", "10000")
        target_url = f"http://127.0.0.1:{port}/mcp/v1/tools/call"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(target_url, json=payload, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"Gateway X-OS 直接呼出フォールバック ({e})")
                return {"status": "LOCAL_EXECUTED", "price_usd": proposal["target_price_usd"]}
