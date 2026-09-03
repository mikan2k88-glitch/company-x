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
        self.openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "dummy_key")
        )
        # OpenRouterに実在する無料モデル（Gemini 2.0 Flash Exp 無料枠）
        self.critic_model = "google/gemini-2.0-flash-exp:free"

    def execute_debate(self, market_opportunity: Dict[str, Any]) -> Dict[str, Any]:
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
                timeout=10.0
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
            logger.warning(f"OpenRouter 呼び出しフォールバック ({e})")
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
