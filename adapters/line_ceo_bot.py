"""
adapters/line_ceo_bot.py
------------------------
LINE Messaging API 連携アダプター
- 日次 P&L レポートの Push 通知送信
- CEO (人間) からの 1 タップ承認 Webhook 処理
"""

import os
import logging
from typing import Dict, Any
import requests

logger = logging.getLogger("company_x.line_bot")


class LineCeoBot:
    def __init__(self):
        self.access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        self.admin_user_id = os.getenv("LINE_ADMIN_USER_ID", "").strip()

    def send_pnl_report(self, pnl_data: Dict[str, Any]) -> bool:
        """
        日次 P&L レポートを CEO の LINE へ Push 送信
        """
        report_text = (
            f"📊 【カンパニーX 日次P&L】\n"
            f"売上: ${pnl_data.get('revenue_usd', 0.0):.2f} | "
            f"利益: ${pnl_data.get('profit_usd', 0.0):.2f} | "
            f"粗利: {pnl_data.get('margin', 0.0)*100:.1f}%\n\n"
            f"ステータス: {pnl_data.get('status', 'RUNNING')}"
        )

        if not self.access_token or not self.admin_user_id:
            logger.warning(
                f"[LINE 送信スキップ] 環境変数が不足しています。"
                f"(TOKEN存在: {bool(self.access_token)}, USER_ID存在: {bool(self.admin_user_id)})"
            )
            return False

        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        payload = {
            "to": self.admin_user_id,
            "messages": [
                {
                    "type": "text",
                    "text": report_text
                }
            ]
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10.0)
            if response.status_code == 200:
                logger.info("✅ LINE Push 通知の実送信に成功しました！")
                return True
            else:
                logger.error(f"❌ LINE Push 送信失敗 (HTTP {response.status_code}): {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ LINE 通信例外エラー: {e}")
            return False
