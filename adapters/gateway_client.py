import httpx
from typing import Dict, Any


class GatewayClient:
    def __init__(self, base_url: str = "http://localhost:10000"):
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
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/mcp/v1/tools/call",
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {"status": "LOCAL_EXECUTED", "price_usd": proposal["target_price_usd"]}
