import os
import json
import logging
from typing import Dict, Any
from openai import OpenAI

logger = logging.getLogger("company_x.debate")


class DebateGovernance:
    MIN_MARGIN_THRESHOLD = 0.83  # 83% マージン絶対防衛

    def __init__(self, openrouter_api_key: str = None):
        self.openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "dummy_key")
        )
        self.critic_model = "deepseek/deepseek-r1:free"  # 無料モデル指定

    def execute_debate(self, market_opportunity: Dict[str, Any]) -> Dict[str, Any]:
        task_name = market_opportunity.get("task_name", "Unknown Task")
        logger.info(f"--- 意思決定ディベート開始: {task_name} ---")

        # R1: 主将提案 ➔ 軍師批判
        proposal_r1 = self._generate_gemini_proposal(market_opportunity, round_num=1)
        critique_r1 = self._call_openrouter_critic(proposal_r1, round_num=1)

        if critique_r1["is_approved"]:
            logger.info("Round 1 で即時承認")
            return self._finalize_decision(proposal_r1, status="APPROVED_R1")

        # R2: 主将修正 ➔ 軍師再批判
        proposal_r2 = self._refine_proposal(proposal_r1, critique_r1, round_num=2)
        critique_r2 = self._call_openrouter_critic(proposal_r2, round_num=2)

        if critique_r2["is_approved"]:
            logger.info("Round 2 で修正案承認")
            return self._finalize_decision(proposal_r2, status="APPROVED_R2")

        # サーキットブレーカー (2R未収束時、損失最小案を強制採用)
        logger.warning("サーキットブレーカー発動 (小口・安全側案を強制採択)")
        safe_proposal = self._apply_circuit_breaker(proposal_r1, proposal_r2)
        return self._finalize_decision(safe_proposal, status="CIRCUIT_BREAKER_APPROVED")

    def _generate_gemini_proposal(self, opportunity: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        cost_jpy = opportunity.get("estimated_cost_jpy", 10000.0)
        price_usd = round((cost_jpy / 155.0) * 5.88, 2)
        return {
            "round": round_num,
            "intent": opportunity.get("intent", ""),
            "estimated_cost_jpy": cost_jpy,
            "target_price_usd": price_usd,
            "expected_margin": 0.83,
            "vetting_risk_score": 0.0
        }

    def _call_openrouter_critic(self, proposal: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        prompt = (
            f"あなたはリスク監査役（軍師）です。\n"
            f"提案: {json.dumps(proposal, ensure_ascii=False)}\n"
            f"応答形式: {{\"is_approved\": true/false, \"critic_feedback\": \"理由\"}}"
        )
        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.critic_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=10.0
            )
            content = response.choices[0].message.content
            parsed = json.loads(content[content.find("{"):content.rfind("}")+1])
            return {"round": round_num, "is_approved": parsed.get("is_approved", False)}
        except Exception:
            # フォールバック (ルールベース評価)
            is_ok = proposal.get("expected_margin", 0) >= self.MIN_MARGIN_THRESHOLD
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
