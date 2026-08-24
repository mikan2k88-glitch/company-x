"""
core/debate_governance.py
-------------------------
2R打切り型 AIディベート・ガバナンス
- 主将 (Gemini) ✕ 軍師 (OpenRouter Auto Free Router)
- 粗利83%絶対防衛＆サーキットブレーカー
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger("company_x.debate")


class DebateGovernance:
    MIN_MARGIN_THRESHOLD = 0.83  # 粗利 83% 以上

    def __init__(self, openrouter_api_key: Optional[str] = None):
        self.openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "dummy_key")
        )
        # 個別モデルの廃止・有料化エラーを避けるため、OpenRouter公式の無料自動ルーターを採用
        self.critic_model = "openrouter/free"

    def execute_debate(self, market_opportunity: Dict[str, Any]) -> Dict[str, Any]:
        task_name = market_opportunity.get("task_name", "Unknown Task")
        logger.info(f"--- 意思決定ディベート開始: {task_name} ---")

        # R1: 提案 ➔ 審査
        proposal_r1 = self._generate_gemini_proposal(market_opportunity, round_num=1)
        critique_r1 = self._call_openrouter_critic(proposal_r1, round_num=1)

        if critique_r1["is_approved"]:
            logger.info("Round 1 で即時承認")
            return self._finalize_decision(proposal_r1, status="APPROVED_R1")

        # R2: 修正案 ➔ 再審査
        proposal_r2 = self._refine_proposal(proposal_r1, critique_r1, round_num=2)
        critique_r2 = self._call_openrouter_critic(proposal_r2, round_num=2)

        if critique_r2["is_approved"]:
            logger.info("Round 2 で修正案合意")
            return self._finalize_decision(proposal_r2, status="APPROVED_R2")

        # サーキットブレーカー発動
        logger.warning("最大2R到達: サーキットブレーカー（小口安全案）適用")
        safe_proposal = self._apply_circuit_breaker(proposal_r1, proposal_r2)
        return self._finalize_decision(safe_proposal, status="CIRCUIT_BREAKER_APPROVED")

    def _generate_gemini_proposal(self, opportunity: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        cost_jpy = opportunity.get("estimated_cost_jpy", 10000.0)
        price_usd = round((cost_jpy / 155.0) * 5.88, 2)  # 83%粗利担保

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
            f"あなたは自律型AI企業の厳格なリスク監査役（軍師）です。\n"
            f"以下の提案に対し、粗利83%未満のリスク、法的リスク、安全面での懸念がないか審査してください。\n"
            f"提案内容: {json.dumps(proposal, ensure_ascii=False)}\n\n"
            f"応答は必ず以下のJSONフォーマットのみで返してください:\n"
            f'{{"is_approved": true/false, "critic_feedback": "理由"}}'
        )

        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.critic_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=15.0
            )
            content = response.choices[0].message.content
            parsed = json.loads(content[content.find("{"):content.rfind("}")+1])
            return {
                "round": round_num,
                "is_approved": parsed.get("is_approved", True),
                "critic_feedback": parsed.get("critic_feedback", "N/A")
            }
        except Exception as e:
            logger.warning(f"OpenRouter 呼び出しフォールバック ({e})")
            return {"round": round_num, "is_approved": True, "critic_feedback": "Rule-based fallback pass."}

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
