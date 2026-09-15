import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("company_x.payment_client")


class PaymentClient:
    """
    Stripe API 連携用決済アダプター
    事前与信（Hold）および納品完了後の売上自動確定（Capture）を担当
    """

    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if self.api_key:
            try:
                import stripe
                stripe.api_key = self.api_key
                self.stripe = stripe
                logger.info("[PaymentClient] Stripe API の初期化に成功しました。")
            except Exception as e:
                logger.warning(f"[PaymentClient] Stripe パッケージ初期化例外: {e}")
                self.stripe = None
        else:
            self.stripe = None
            logger.warning("[PaymentClient] STRIPE_SECRET_KEY 未設定のため、モック決済モードで稼働します。")

    def authorize_payment(self, task_id: str, amount_jpy: int, payment_method_id: Optional[str] = None) -> Dict[str, Any]:
        """
        クレジットカードの事前与信（仮売上/Hold）を行う
        """
        logger.info(f"[PaymentClient] タスク {task_id} の与信確保要求: ¥{amount_jpy:,}")

        if self.stripe and payment_method_id:
            try:
                intent = self.stripe.PaymentIntent.create(
                    amount=amount_jpy,
                    currency="jpy",
                    payment_method=payment_method_id,
                    capture_method="manual",  # 手動確定（あとでCapture）
                    confirm=True,
                    description=f"Company X Task Authorization: {task_id}"
                )
                return {
                    "status": "AUTHORIZED",
                    "payment_intent_id": intent.id,
                    "amount_jpy": amount_jpy
                }
            except Exception as e:
                logger.error(f"[PaymentClient] 与信確保例外: {str(e)}")
                return {"status": "AUTH_FAILED", "reason": str(e)}

        # モック決済（Stripe API キー未設定時）
        return {
            "status": "AUTHORIZED",
            "payment_intent_id": f"pi_mock_{task_id}",
            "amount_jpy": amount_jpy,
            "mode": "mock"
        }

    def capture_payment(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        検品合格後の売上即時確定（Capture）
        """
        logger.info(f"[PaymentClient] 決済確定 (Capture) 要求: {payment_intent_id}")

        if self.stripe and not payment_intent_id.startswith("pi_mock_"):
            try:
                intent = self.stripe.PaymentIntent.capture(payment_intent_id)
                return {
                    "status": "CAPTURED",
                    "payment_intent_id": intent.id,
                    "amount_received": intent.amount_received
                }
            except Exception as e:
                logger.error(f"[PaymentClient] 決済確定例外: {str(e)}")
                return {"status": "CAPTURE_FAILED", "reason": str(e)}

        # モック売上確定
        return {
            "status": "CAPTURED",
            "payment_intent_id": payment_intent_id,
            "mode": "mock"
        }

    def cancel_payment(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        処理失敗・検品NG時の与信自動キャンセル
        """
        logger.info(f"[PaymentClient] 与信キャンセル要求: {payment_intent_id}")

        if self.stripe and not payment_intent_id.startswith("pi_mock_"):
            try:
                intent = self.stripe.PaymentIntent.cancel(payment_intent_id)
                return {"status": "CANCELLED", "payment_intent_id": intent.id}
            except Exception as e:
                logger.error(f"[PaymentClient] 与信キャンセル例外: {str(e)}")
                return {"status": "CANCEL_FAILED", "reason": str(e)}

        return {"status": "CANCELLED", "payment_intent_id": payment_intent_id, "mode": "mock"}
