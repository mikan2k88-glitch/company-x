"""
core/scout_engine.py
--------------------
マルチソース市場スカウトエンジン (日本語対応版)
- Qiita API (国内技術トレンド)
- GitHub Search API (グローバル AI / LLM リポジトリ)
- Hacker News API (グローバルビジネス / テックニュース)
上記のリアルタイムデータソースから多角的にニーズを自動収集し、案件を日本語で自動創出します。
"""

import logging
import random
import httpx
from typing import Dict, Any, List

logger = logging.getLogger("company_x.scout")


class ScoutEngine:
    def __init__(self):
        # 日本語化された案件テンプレートプール
        self.opportunity_pool = [
            {
                "topic": "LLMマルチエージェント応答速度の最適化",
                "base_intent": "分散型LLMマルチエージェントの処理遅延を計測し、東京リージョン向けに応答速度を高速化",
                "base_cost_jpy": 8500.0,
                "category": "グローバルAI技術"
            },
            {
                "topic": "エッジVision AIによる人流密度リアルタイム解析",
                "base_intent": "省電力ビジョンモデルを配置し、渋谷・新宿エリアのリアルタイム歩行者ヒートマップを生成",
                "base_cost_jpy": 12000.0,
                "category": "都市データアナリティクス"
            },
            {
                "topic": "自律型B2Bスクレイピング＆LLMデータ構造化",
                "base_intent": "企業プロフィール情報を自動収集し、LLMを用いて高品質な顧客メタデータを補完・生成",
                "base_cost_jpy": 6400.0,
                "category": "リード獲得＆スクレイピング"
            },
            {
                "topic": "自動セキュリティ脆弱性修正パッチ生成",
                "base_intent": "静的コード解析を実行し、重大なCVE脆弱性に対する修正プルリクエストをAIが自動作成",
                "base_cost_jpy": 9800.0,
                "category": "DevSecOps"
            },
            {
                "topic": "マルチモーダル技術文書の自動ローカライズ＆評価",
                "base_intent": "LLM-as-a-Judgeを活用し、技術ドキュメントの日本語化および翻訳クオリティの自動評価を実施",
                "base_cost_jpy": 7500.0,
                "category": "ローカライズ"
            },
            {
                "topic": "リアルタイム金融センチメント分析＆RAG検索エンジン",
                "base_intent": "決算短信や市場ニュースをリアルタイム解析する軽量RAGパイプラインの構築と金融分析",
                "base_cost_jpy": 11000.0,
                "category": "FinTech & RAG"
            }
        ]

    def _fetch_qiita_trends(self, client: httpx.Client) -> List[str]:
        """Qiita API から国内トレンドタグを取得"""
        try:
            url = "https://qiita.com/api/v2/tags?page=1&per_page=5&sort=count"
            res = client.get(url, timeout=3.5)
            if res.status_code == 200:
                tags = [item.get("id") for item in res.json()]
                if tags:
                    logger.info(f"🇯🇵 [Qiita] トレンドタグを取得: {', '.join(tags)}")
                    return tags
        except Exception as e:
            logger.warning(f"Qiita トレンド取得スキップ: {e}")
        return ["FastAPI", "Python", "GenerativeAI"]

    def _fetch_github_trending_ai(self, client: httpx.Client) -> List[str]:
        """GitHub API からスター急上昇中の AI リポジトリを取得"""
        try:
            url = "https://api.github.com/search/repositories?q=topic:llm+topic:ai&sort=stars&order=desc&per_page=3"
            headers = {"User-Agent": "Company-X-ScoutEngine/3.2"}
            res = client.get(url, headers=headers, timeout=3.5)
            if res.status_code == 200:
                items = res.json().get("items", [])
                repo_names = [item.get("name") for item in items if item.get("name")]
                if repo_names:
                    logger.info(f"🌐 [GitHub] 急上昇AIリポジトリを取得: {', '.join(repo_names)}")
                    return repo_names
        except Exception as e:
            logger.warning(f"GitHub トレンド取得スキップ: {e}")
        return ["langchain", "auto-gpt", "vllm"]

    def _fetch_hacker_news_top(self, client: httpx.Client) -> List[str]:
        """Hacker News API から海外最新テックニュースの見出しを取得"""
        try:
            url = "https://hacker-news.firebaseio.com/v0/topstories.json"
            res = client.get(url, timeout=3.5)
            if res.status_code == 200:
                top_ids = res.json()[:3]
                titles = []
                for story_id in top_ids:
                    item_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                    item_res = client.get(item_url, timeout=2.0)
                    if item_res.status_code == 200:
                        title = item_res.json().get("title")
                        if title:
                            titles.append(title[:30] + "...")
                if titles:
                    logger.info(f"📰 [HackerNews] 最新ニュースを取得: {titles[0]}")
                    return titles
        except Exception as e:
            logger.warning(f"HackerNews 取得スキップ: {e}")
        return ["AI Agent Revolution in Enterprise"]

    def scout_market(self) -> Dict[str, Any]:
        """
        複数ソース（Qiita / GitHub / HackerNews）からリアルタイム情報を統合し、案件を自動生成
        """
        logger.info("🔍 [ScoutEngine] マルチソース(Qiita / GitHub / HackerNews)スカウトを実行中...")

        qiita_tags = []
        github_repos = []
        hn_stories = []

        # 単一 Client セッションで高速並行リクエスト
        with httpx.Client() as client:
            qiita_tags = self._fetch_qiita_trends(client)
            github_repos = self._fetch_github_trending_ai(client)
            hn_stories = self._fetch_hacker_news_top(client)

        # 基礎案件の決定
        base_opportunity = random.choice(self.opportunity_pool)
        
        # 収集データの統合コンテキスト作成（日本語表記）
        selected_source = random.choice(["Qiita", "GitHub", "HackerNews"])
        if selected_source == "Qiita" and qiita_tags:
            context_str = f"文脈: Qiitaトレンド [{', '.join(qiita_tags[:3])}]"
        elif selected_source == "GitHub" and github_repos:
            context_str = f"文脈: GitHub注目AI [{', '.join(github_repos[:2])}]"
        elif hn_stories:
            context_str = f"文脈: 海外最新ニュース [{hn_stories[0]}]"
        else:
            context_str = "文脈: グローバルAIトレンド"

        # コストゆらぎ（需給バランスの表現）
        cost_variance = random.randint(-1000, 2000)
        final_cost = max(5000.0, base_opportunity["base_cost_jpy"] + cost_variance)

        scouted_item = {
            "task_name": base_opportunity["topic"],
            "intent": f"【{base_opportunity['topic']}】{base_opportunity['base_intent']} ({context_str})",
            "estimated_cost_jpy": float(final_cost)
        }

        logger.info(
            f"💡 [マルチソース案件発掘完了] ソース: {selected_source} | "
            f"タスク: {scouted_item['task_name']} | 見積予算: ¥{scouted_item['estimated_cost_jpy']:,}"
        )

        return scouted_item
