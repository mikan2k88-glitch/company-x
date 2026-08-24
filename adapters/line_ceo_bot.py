"""
adapters/line_ceo_bot.py

LINE Messaging API 連携アダプター
- 日次 P&L レポートの Push 通知送信
- CEO (人間) 用 1 タップ承認 Flex Message カード送信
"""

import os
import logging
from typing import Dict, Any
import httpx

logger = logging.getLogger("company_x.line_bot")


class LineCeoBot:
    APPROVAL_THRESHOLD_JPY = 50000.0  # 5万円以上は要手動承認

    def __init__(self):
        self.access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip().strip('"').strip("'")
        self.admin_user_id = os.getenv("LINE_ADMIN_USER_ID", "").strip().strip('"').strip("'")

    def send_pnl_report(self, pnl_data: Dict[str, Any]) -> bool:
        """日次 P&L レポートを Push 送信"""
        report_text = (
            f"📊 【カンパニーX 日次P&L】\n"
            f"売上: ${pnl_data.get('revenue_usd', 0.0):.2f} | "
            f"利益: ${pnl_data.get('profit_usd', 0.0):.2f} | "
            f"粗利: {pnl_data.get('margin', 0.0)*100:.1f}%\n\n"
            f"ステータス: {pnl_data.get('status', 'RUNNING')}"
        )
        return self._send_push_text(report_text)

    def send_approval_request(self, proposal: Dict[str, Any]) -> bool:
        """
        高額・重要案件に対する LINE Flex Message 1タップ承認カードを送信
        """
        intent = proposal.get("intent", "案件提案")
        cost_jpy = proposal.get("estimated_cost_jpy", 0.0)
        target_price_usd = proposal.get("target_price_usd", 0.0)
        margin = proposal.get("expected_margin", 0.83) * 100

        flex_message = {
            "type": "flex",
            "altText": f"🚨 CEO承認リクエスト: {intent} (¥{cost_jpy:,.0f})",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#1DB446",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🚨 CEO 意思決定リクエスト",
                            "color": "#FFFFFF",
                            "weight": "bold",
                            "size": "sm"
                        }
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": intent,
                            "weight": "bold",
                            "size": "md",
                            "wrap": True
                        },
                        {"type": "separator", "margin": "md"},
                        {
                            "type": "box",
                            "layout": "vertical",
                            "margin": "md",
                            "spacing": "sm",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "baseline",
                                    "contents": [
                                        {"type": "text", "text": "推定コスト:", "color": "#aaaaaa", "size": "sm", "flex": 2},
                                        {"type": "text", "text": f"¥{cost_jpy:,.0f}", "weight": "bold", "size": "sm", "flex": 3}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "baseline",
                                    "contents": [
                                        {"type": "text", "text": "目標売上:", "color": "#aaaaaa", "size": "sm", "flex": 2},
                                        {"type": "text", "text": f"${target_price_usd:,.2f}", "weight": "bold", "size": "sm", "flex": 3}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "baseline",
                                    "contents": [
                                        {"type": "text", "text": "想定粗利率:", "color": "#aaaaaa", "size": "sm", "flex": 2},
                                        {"type": "text", "text": f"{margin:.1f}%", "weight": "bold", "color": "#1DB446", "size": "sm", "flex": 3}
                                    ]
                                }
                            ]
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#1DB446",
                            "action": {
                                "type": "postback",
                                "label": "✅ 1タップ承認・即時発注",
                                "data": f"action=approve&intent={intent}&cost={cost_jpy}&price={target_price_usd}",
                                "displayText": "✅ 案件を承認し、発注を実行します。"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "🔄 軍師へ再検討指示",
                                "data": f"action=redebate&intent={intent}",
                                "displayText": "🔄 軍師へ再審査を命じます。"
                            }
                        },
                        {
                            "type": "button",
                            "style": "link",
                            "color": "#FF3B30",
                            "action": {
                                "type": "postback",
                                "label": "❌ 却下",
                                "data": f"action=reject&intent={intent}",
                                "displayText": "❌ 案件を却下します。"
                            }
                        }
                    ]
                }
            }
        }
        return self._send_push_message(flex_message)

    def send_simple_message(self, text: str) -> bool:
        """テキストメッセージ送信"""
        return self._send_push_text(text)

    def _send_push_text(self, text: str) -> bool:
        message = {"type": "text", "text": text}
        return self._send_push_message(message)

    def _send_push_message(self, message_obj: Dict[str, Any]) -> bool:
        if not self.access_token or not self.admin_user_id:
            logger.warning("[LINE 送信スキップ] 環境変数が不足しています。")
            return False

        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        payload = {
            "to": self.admin_user_id,
            "messages": [message_obj]
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info("✅ LINE Push メッセージの送信に成功しました！")
                return True
            else:
                logger.error(f"❌ LINE Push 送信失敗 (HTTP {response.status_code}): {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ LINE 通信例外エラー: {e}")
            return False
