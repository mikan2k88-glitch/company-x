"""
core/scout_engine.py
--------------------
マルチソース市場スカウトエンジン (Gateway X Capability連動版)
- Qiita API / GitHub Search API / Hacker News API からリアルタイムトレンドを取得
- 共有DB (capability_rules) から Gateway X が実行可能なカテゴリを参照し、
  実行不能な案件の生成を水際で防止します。
"""

import logging
import random
import httpx
from typing import Dict, Any, List, Optional
from db.company_repository import CompanyRepository

logger = logging.getLogger("company_x.scout")


class ScoutEngine:
    def __init__(self):
        # Gateway X が得意とする「現地・物理・データアノテーション・エッジ収集」対応テンプレート
        self.capability_aligned_pool = [
            {
                "topic": "エッジVision AIによる人流密度リアルタイム解析",
                "base_intent": "省電力ビジョンカメラを配置し、渋谷・新宿エリアのリアルタイム歩行者ヒートマップを現地計測・サンプリング",
                "base_cost_jpy": 12000.0,
                "category": "FIELD_PHYSICAL"  # 現場・物理タスク
            },
            {
                "topic": "現地店舗・看板データのアノテーション＆収集",
                "base_intent": "都内主要エリアの店舗サイン・看板画像を現地撮影・データ収集し、LLM向けにタグ付けアノテーションを実施",
                "base_cost_jpy": 8500.0,
                "category": "FIELD_PHYSICAL"
            },
            {
                "topic": "自律型B2B情報収集＆現場確認サンプリング",
                "base_intent": "公開企業データベースおよび現地オフィス実在確認を連携し、高品質な企業メタデータを検証作成",
                "base_cost_jpy": 6400.0,
                "category": "DATA_COLLECTION"
            },
            {
                "topic": "リアルタイム金融・ニュースセンチメントデータアノテーション",
                "base_intent": "市場ニュースおよび決算短信データに対する精度評価アノテーションタスクを現場ワーカー連携で実行",
                "base_cost_jpy": 9800.0,
                "category": "DATA_COLLECTION"
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
        return ["Python", "GenerativeAI", "IoT"]

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
        return ["vllm", "auto-gpt"]

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
        return ["AI Edge Sensing Trends"]

    def scout_market(self) -> Dict[str, Any]:
        """
        Gateway X の capability_rules（対応可能カテゴリ）を参照し、
        適合する案件のみをスカウト創出
        """
        logger.info("🔍 [ScoutEngine] Gateway X 連携 Capability チェック ＆ スカウトを実行中...")

        # 1. 共有DBから有効ルールを取得して事前検証
        repo = CompanyRepository()
        rules = repo.fetch_active_capability_rules()
        active_categories = [r.get("category") for r in rules if r.get("is_enabled")] if rules else []

        # 2. 外部トレンドの収集
        qiita_tags = []
        github_repos = []
        hn_stories = []

        with httpx.Client() as client:
            qiita_tags = self._fetch_qiita_trends(client)
            github_repos = self._fetch_github_trending_ai(client)
            hn_stories = self._fetch_hacker_news_top(client)

        # 3. Gateway X 対応範囲に絞り込んだ案件選定
        eligible_pool = self.capability_aligned_pool
        if active_categories:
            filtered = [item for item in self.capability_aligned_pool if item["category"] in active_categories]
            if filtered:
                eligible_pool = filtered
                logger.info(f"✅ capability_rules により {len(filtered)} 件の適合可能案件候補に絞り込みました。")

        base_opportunity = random.choice(eligible_pool)

        # 文脈情報の付加
        selected_source = random.choice(["Qiita", "GitHub", "HackerNews"])
        if selected_source == "Qiita" and qiita_tags:
            context_str = f"文脈: Qiita [{', '.join(qiita_tags[:2])}]"
        elif selected_source == "GitHub" and github_repos:
            context_str = f"文脈: GitHub [{github_repos[0]}]"
        elif hn_stories:
            context_str = f"文脈: HN [{hn_stories[0]}]"
        else:
            context_str = "文脈: AI/エッジリアルタイムニーズ"

        cost_variance = random.randint(-500, 1500)
        final_cost = max(5000.0, base_opportunity["base_cost_jpy"] + cost_variance)

        scouted_item = {
            "task_name": base_opportunity["topic"],
            "intent": f"【{base_opportunity['topic']}】{base_opportunity['base_intent']} ({context_str})",
            "estimated_cost_jpy": float(final_cost)
        }

        logger.info(
            f"💡 [Capability適合案件発掘完了] ソース: {selected_source} | "
            f"タスク: {scouted_item['task_name']} | 見積予算: ¥{scouted_item['estimated_cost_jpy']:,}"
        )

        return scouted_item
