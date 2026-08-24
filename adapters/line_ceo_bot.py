"""
adapters/line_ceo_bot.py
------------------------
Yuki社長用 LINE Webhook (ダッシュボード & 緊急承認) モジュール
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("company_x.line_bot")


class LineCeoBot:
    APPROVAL_THRESHOLD_JPY = 50000.0  # 5万円超は手動承認

    def send_daily_pnl_report(self, revenue_usd: float, profit_usd: float, margin: float) -> bool:
        """日次P&L報告メッセージの送信"""
        message = (
            f"📊 【カンパニーX 日次P&L】\n"
            f"売上: ${revenue_usd:,.2f} | 利益: ${profit_usd:,.2f} | 粗利: {margin:.1%}"
        )
        logger.info(f"[LINE レポート送信]: {message}")
        return True

    def request_approval_if_needed(self, proposal: Dict[str, Any]) -> bool:
        """高額案件（5万円以上）の場合のLINE承認要請"""
        cost_jpy = proposal.get("estimated_cost_jpy", 0.0)
        if cost_jpy < self.APPROVAL_THRESHOLD_JPY:
            return True  # 5万円未満は自動承認

        logger.info(f"[LINE 承認要請]: 高額案件につき要承認 (¥{cost_jpy:,.0f})")
        return False
