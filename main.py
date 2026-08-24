"""
company_x/main.py
-----------------
カンパニーX 自律成長ループ エントリーポイント
"""

import asyncio
import logging
from company_x.core.scout_engine import ScoutEngine
from company_x.core.debate_governance import DebateGovernance
from company_x.adapters.gateway_client import GatewayClient
from company_x.adapters.line_ceo_bot import LineCeoBot
from company_x.db.company_repository import CompanyRepository

logger = logging.getLogger("company_x.main")


async def run_autonomous_loop():
    """1時間ごとにバックグラウンドで呼び出される自律意思決定・発注ループ"""
    scout = ScoutEngine()
    governance = DebateGovernance()
    gateway = GatewayClient()
    line_bot = LineCeoBot()
    repo = CompanyRepository()

    logger.info("=== カンパニーX 自律成長ループ開始 ===")

    try:
        # 1. 機会検知 (渋谷等でのデータ収集ニーズ)
        opportunity = scout.find_opportunity()

        # 2. 軍師ディベート (Gemini ✕ OpenRouter Free Tier)
        decision = governance.execute_debate(opportunity)

        # 3. 社長承認チェック (高額案件はLINEで通知して止める)
        if not line_bot.request_approval_if_needed(decision):
            logger.info("高額案件のため、Yuki社長の承認待ちに入りました。")
            return

        # 4. Gateway X-OS (関所 API) へ物理タスク発注
        result = await gateway.call_mcp_execution(decision)

        # 5. 取引ログの永続化
        repo.log_decision(decision, status=result.get("status", "UNKNOWN"))

        # 6. LINE 日次損益レポート報告
        revenue_usd = decision.get("target_price_usd", 0.0)
        line_bot.send_daily_pnl_report(
            revenue_usd=revenue_usd,
            profit_usd=revenue_usd * 0.83,
            margin=0.83
        )

        logger.info("=== カンパニーX 自律成長ループ正常完了 ===")

    except Exception as e:
        logger.error(f"自律ループ実行中にエラーが発生しました: {e}")


if __name__ == "__main__":
    asyncio.run(run_autonomous_loop())
