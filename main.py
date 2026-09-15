# main.py の先頭インポートに追加
from adapters.payment_client import PaymentClient

payment_client = PaymentClient()

def execute_task_pipeline(candidate: Dict[str, Any]) -> Dict[str, Any]:
    task_id = candidate.get("task_id")
    task_type = candidate.get("task_type")
    execution_type = candidate.get("execution_type", "AUTO")
    payload = candidate.get("payload", {})
    amount_jpy = candidate.get("estimated_price_jpy", 0)
    payment_method_id = candidate.get("payment_method_id")

    # 1. 事前与信（Hold）の確保
    auth_res = payment_client.authorize_payment(task_id, amount_jpy, payment_method_id)
    if auth_res.get("status") != "AUTHORIZED":
        return {"status": "PAYMENT_FAILED", "reason": "カード与信の確保に失敗しました。"}

    payment_intent_id = auth_res.get("payment_intent_id")

    # 2. タスク実行 (InternalExecutor / GatewayClient)
    if execution_type == "INTERNAL" or task_type in ["data_structuring", "research_report", "content_generation"]:
        result = internal_executor.execute_task(task_type, payload)

        if result.get("status") == "SUCCESS":
            # 3. 検品合格 ➔ 即時売上確定 (Capture)
            cap_res = payment_client.capture_payment(payment_intent_id)
            
            repository.save_execution_log(
                task_id=task_id,
                execution_type="INTERNAL_RENDER",
                status="EXECUTED",
                revenue_jpy=amount_jpy,
                cost_jpy=int(amount_jpy * 0.01),
                gross_margin="99.0%"
            )
            safe_send_line_push(
                f"【完全自動決済・納品完了】デジタルタスク完了\n"
                f"タスクID: {task_id}\n"
                f"売上確定: ¥{amount_jpy:,} (粗利 99%)\n"
                f"決済ID: {payment_intent_id}"
            )
            result["payment_status"] = cap_res.get("status")
            return {"status": "SUCCESS", "execution_type": "INTERNAL", "result": result}
        else:
            # 処理失敗/検品NG ➔ 与信自動キャンセル
            payment_client.cancel_payment(payment_intent_id)
            repository.save_execution_log(
                task_id=task_id,
                execution_type="INTERNAL_RENDER",
                status="EXECUTION_FAILED",
                revenue_jpy=0,
                cost_jpy=0
            )
            return {"status": "EXECUTION_FAILED", "execution_type": "INTERNAL", "reason": result.get("error_message")}
