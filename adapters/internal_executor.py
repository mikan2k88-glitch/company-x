import os
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("InternalExecutor")

class InternalExecutor:
    """
    内部デジタルタスクを実行する高機能エンジンクラス。
    Gemini 3.8 Flash をプライマリに据えた 3.x 系統の安全なフォールバック・チェーンを搭載。
    """

    def __init__(self):
        # 優先モデルは環境変数 GEMINI_MODEL_NAME、未設定時は最先端の gemini-3.8-flash
        self.default_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.8-flash")

    def _get_genai_client(self) -> Tuple[Optional[Tuple[str, Any]], Optional[str]]:
        """
        環境変数から適切なSDKクライアントを初期化する。
        """
        api_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_KEY")
            or os.getenv("GEMINI_API_TOKEN")
        )
        if api_key:
            api_key = str(api_key).strip()

        if not api_key:
            found_keys = [k for k in os.environ.keys() if "GEMINI" in k.upper() or "GOOGLE" in k.upper()]
            return None, f"GEMINI_API_KEY未設定 (検出キー候補: {found_keys})"

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            return ("new_sdk", client), None
        except Exception as e_new:
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=api_key)
                return ("legacy_sdk", legacy_genai), None
            except Exception as e_legacy:
                return None, f"SDK初期化失敗 (google-genai: {e_new} / legacy: {e_legacy})"

    def execute_task(self, task_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        受託タスクの実行エントリポイント。
        Gemini 3.x 系統のフォールバックチェーンを順次試行。
        """
        sdk_info, err_msg = self._get_genai_client()
        
        if not sdk_info:
            logger.warning(f"Gemini API 初期化不可のためフォールバック適用: {err_msg}")
            return {
                "status": "SUCCESS_FALLBACK",
                "result_data": {
                    "engine": f"internal_fallback_parser ({err_msg})",
                    "report_markdown": self._generate_static_fallback_report(payload)
                }
            }

        sdk_type, client_obj = sdk_info
        topic = payload.get("topic", "AI技術の最新動向とビジネス分析")
        context = payload.get("context", "詳細な分析レポートおよび具体的推奨ロードマップを作成すること")

        prompt = f"""
あなたはプロフェッショナルなIT・ビジネスコンサルタントです。
以下のテーマおよび文脈に基づき、最新の一次情報・ファクトに基づく高品質なリサーチレポートを日本語のMarkdown形式で作成してください。

【テーマ】: {topic}
【文脈・要望】: {context}

【必須要件】:
1. 必要に応じてリアルタイムWeb検索を実施し、最新のファクト・市場動向・数値を正確に反映させること。
2. 必要に応じてPythonコード実行ツールを用いて精度の高い数値計算（市場予測、コスト比較、ROI試算など）を行うこと。
3. 明確な表形式（Markdown Table）での比較分析を含めること。

【構成案】:
1. Executive Summary
2. 市場・技術の最新動向 (リアルタイムファクト含む)
3. 主要課題およびリスク要因
4. 競合・選択肢の比較分析（Markdown表形式）
5. 展望と推奨アクション (Actionable Insights & Roadmap)
"""

        # Gemini 3.x 系統のみで構成された堅牢なフォールバック・チェーン
        fallback_models = [
            self.default_model_name,
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite"
        ]

        # 重複を排除しつつ順序を維持
        seen = set()
        unique_models = [m for m in fallback_models if not (m in seen or seen.add(m))]

        last_error = ""

        for model_name in unique_models:
            if not model_name:
                continue
            try:
                if sdk_type == "new_sdk":
                    response = client_obj.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={
                            "tools": [
                                {"google_search": {}},
                                {"code_execution": {}}
                            ]
                        }
                    )
                    if response and hasattr(response, "text") and response.text:
                        return {
                            "status": "SUCCESS",
                            "result_data": {
                                "engine": f"{model_name} (new_sdk + google_search + code_execution)",
                                "report_markdown": response.text
                            }
                        }
                else:
                    model_instance = client_obj.GenerativeModel(
                        model_name,
                        tools=["google_search_retrieval"]
                    )
                    response = model_instance.generate_content(prompt)
                    if response and hasattr(response, "text") and response.text:
                        return {
                            "status": "SUCCESS",
                            "result_data": {
                                "engine": f"{model_name} (legacy_sdk + google_search)",
                                "report_markdown": response.text
                            }
                        }
            except Exception as e:
                last_error = str(e)
                logger.warning(f"モデル '{model_name}' での生成失敗: {e}. 次の 3.x 系統フォールバックへ移行します。")

        # 全モデル失敗時の安全自動降格
        logger.error(f"Gemini API 呼び出し最終エラー: {last_error}")
        return {
            "status": "SUCCESS_FALLBACK",
            "result_data": {
                "engine": f"internal_fallback_parser (全3.xモデル応答不可: {last_error[:100]}...)",
                "report_markdown": self._generate_static_fallback_report(payload)
            }
        }

    def _generate_static_fallback_report(self, payload: Dict[str, Any]) -> str:
        topic = payload.get("topic", "リサーチテーマ")
        return f"""# 【リサーチレポート】{topic}

## 1. Executive Summary
本レポートは「{topic}」に関してシステム緊急用フォールバックから自動生成された概要書です。

## 2. システム状態と推奨アクション
現在Gemini APIへの接続または認証情報を確認中です。Render Cloud上の環境変数 `GEMINI_API_KEY` の登録状態をご確認ください。
"""