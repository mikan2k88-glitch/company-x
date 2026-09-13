import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("company_x.line_ceo_bot")

class LineCeoBot:
    """
    LINE Messaging API と連携し、CEO への Push 通知および Flex Message 1タップ承認カード、
    Webhook イベントのパースを担当するアダプター。
    """

    def __init__(self):
        self.channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
        self.ceo_user_id = os.getenv("LINE_CEO_USER_ID", "")

    def send_push_message(self, text: str) -> bool:
        """
        CEO の LINE アカウントへテキスト Push 通知を送信する
        """
        if not self.channel_access_token or not self.ceo_user_id:
            logger.warning("[LineCeoBot] LINE_CHANNEL_ACCESS_TOKEN または LINE_CEO_USER_ID が未設定のため、ログ出力のみ行います。")
            logger.info(f"[Push Message Notification]: {text}")
            return False

        try:
            import requests
            url = "https://api.line.me/v2/bot/message/push"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.channel_access_token}"
            }
            payload = {
                "to": self.ceo_user_id,
                "messages": [{"type": "text", "text": text}]
            }
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code == 200:
                logger.info("[LineCeoBot] LINE Push 通知の送信に成功しました。")
                return True
            else:
                logger.error(f"[LineCeoBot] LINE Push 通知送信エラー: {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"[LineCeoBot] LINE Push 通知送信例外: {str(e)}")
            return False

    def send_approval_card(self, task_id: str, title: str, amount_jpy: int, reason: str = "") -> bool:
        """
        5万円以上のタスクに対する Flex Message 承認カードの送信
        """
        msg = (
            f"【要CEO承認】¥{amount_jpy:,} の高額タスク承認要請が届きました。\n"
            f"タスクID: {task_id}\n"
            f"件名: {title}\n"
            f"審査理由: {reason}"
        )
        return self.send_push_message(msg)

    def parse_webhook_event(self, body_str: str, signature: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        LINE からの Webhook リクエスト（キルスイッチ指示 / 承認ボタン押下）の解析
        """
        try:
            import json
            data = json.loads(body_str)
            events = data.get("events", [])
            if not events:
                return None

            event = events[0]
            event_type = event.get("type")

            if event_type == "message":
                msg_text = event.get("message", {}).get("text", "")
                return {"action": "MESSAGE", "message": msg_text}

            elif event_type == "postback":
                postback_data = event.get("postback", {}).get("data", "")
                params = dict(item.split("=") for item in postback_data.split("&") if "=" in item)
                return {
                    "action": params.get("action"),
                    "task_id": params.get("task_id")
                }
        except Exception as e:
            logger.error(f"[LineCeoBot] Webhook イベントパースエラー: {str(e)}")

        return None