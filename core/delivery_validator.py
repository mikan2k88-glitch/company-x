import logging
import json
from typing import Dict, Any, Tuple

logger = logging.getLogger("company_x.delivery_validator")

class DeliveryValidator:
    """
    納品物の構造・品質・安全性を自動検証する品質保証 (QA) モジュール
    """

    def validate(self, task_type: str, result_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        タスクタイプに応じた品質判定ロジック
        返り値: (合格判定: bool, 検品コメント: str)
        """
        if not result_data:
            return False, "納品データが空 (None) です。"

        # 1. データ構造化タスクの検証
        if task_type == "data_structuring":
            structured_output = result_data.get("structured_output")
            if not structured_output:
                return False, "抽出データ 'structured_output' が存在しません。"
            
            # 文字列（JSON文字列含む）または辞書型の内容チェック
            output_str = str(structured_output)
            if len(output_str) < 15:
                return False, "抽出されたデータが著しく短く、内容が不十分です。"
            
            # エラーキーワードの検知
            if "エラー" in output_str or "TypeError" in output_str or "UnboundLocalError" in output_str:
                return False, "納品データ内にプログラム例外文字列が混入しています。"

        # 2. Webリサーチ / レポート生成タスクの検証
        elif task_type == "research_report":
            report = result_data.get("report_markdown") or result_data.get("report")
            if not report or len(str(report)) < 50:
                return False, "生成されたレポートが50文字未満で不十分です。"

        # 3. コンテンツ・コード生成タスクの検証
        elif task_type == "content_generation":
            content = result_data.get("generated_content") or result_data.get("content")
            if not content or len(str(content)) < 10:
                return False, "生成されたコンテンツが極端に短いか空です。"

        logger.info(f"[DeliveryValidator] タスク '{task_type}' の自動検品に合格しました。")
        return True, "QA検品合格: 品質およびデータ構造に問題ありません。"
