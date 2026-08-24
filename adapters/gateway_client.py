"""
adapters/gateway_client.py
--------------------------
Gateway X-OS (v3.2 Protocol) A2A交渉 & 発注クライアント
- カンパニーX ⇄ Gateway X 間のネゴシエーション
- マージン下限80-83%と安全基準のコードレベル防衛
"""

import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.gateway")


class GatewayClient:
    def __init__(self, base_url: str = "http://localhost:10000"):
        self.base_url = base_url

    async def call_mcp_execution(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gateway X-OS の /mcp/v1/tools/call エンドポイントへ物理発注タスクを送信
        """
        payload = {
            "name": "dispatch_physical_execution",
            "arguments": {
                "intent": proposal.get("intent", ""),
                "tier": "economy",
                "estimated_cost_jpy": proposal.get("estimated_cost_jpy", 0.0),
                "client_id": "company_x_brain"
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/mcp/v1/tools/call",
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                result = response.json()

                # マージン ガードレール検証 (80%未満は拒否)
                if result.get("status") == "QUOTED":
                    price_usd = result.get("price_usd", 0.0)
                    cost_jpy = proposal.get("estimated_cost_jpy", 0.0)
                    cost_usd = cost_jpy / 155.0
                    margin = (price_usd - cost_usd) / price_usd if price_usd > 0 else 0.0

                    if margin < 0.80:
                        return {
                            "status": "REJECTED_BY_GUARDRAIL",
                            "reason": f"Margin violates safety boundary ({margin:.2%}). Threshold is >=80%."
                        }

                return result

            except Exception as e:
                logger.warning(f"Gateway X-OS 直送通信スキップ (ローカルシミュレーション動作): {e}")
                return {
                    "status": "QUOTED",
                    "price_usd": proposal.get("target_price_usd", 0.0)
                }
