"""
core/scout_engine.py
--------------------
マルチソース市場スカウトエンジン (Gateway X Capability連動版)
- Qiita API / GitHub Search API / Hacker News API からリアルタイムトレンドを取得
- 共有DB (capability_rules: keyword, allowed, reason) から Gateway X が実行不可と定義するキーワードを事前フィルタリングします。
"""

import logging
import random
import httpx
from typing import Dict, Any, List
from db.company_repository import CompanyRepository

logger = logging.getLogger("company_x.scout")


class ScoutEngine:
    def __init__(self):
        # Gateway X が実行得意とする現地・物理・アノテーションタスクプール
        self.capability_aligned_pool = [
            {
                "topic": "エッジVision AIによる人流密度リアルタイム解析",
                "base_intent": "省電力ビジョンカメラを配置し、渋谷・新宿エリアのリアルタイム歩行者ヒートマップを現地計測・サンプリング",
                "base_cost_jpy": 12000.0,
                "keywords": ["エッジVision", "人流密度", "現地計測"]
            },
            {
                "topic": "現地店舗・看板データのアノテーション＆収集",
                "base_intent": "都内主要エリアの店舗サイン・看板画像を現地撮影・データ収集し、データセット向けにアノテーションを実施",
                "base_cost_jpy": 8500.0,
                "keywords": ["現地撮影", "看板データ", "アノテーション"]
            },
            {
                "topic": "自律型B2B情報収集＆現場確認サンプリング",
                "base_intent": "公開企業データベースおよび現地オフィス実在確認を連携し、高品質な企業メタデータを検証作成",
                "base_cost_jpy": 6400.0,
                "keywords": ["現場確認", "オフィス実在確認", "企業データ検証"]
            },
            {
                "topic": "現地交通量・流動パターンデータ実測",
                "base_intent": "主要交差点における現地トラフィックパターンおよび交通量データをサンプリング・評価",
                "base_cost_jpy": 9800.0,
                "keywords": ["現地トラフィック", "交通量実測", "サンプリング"]
            }
        ]

    def _fetch_qiita_trends(self, client: httpx.Client) -> List[str]:
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
        capability_rules (keyword, allowed, reason) テーブルを参照し、
        非対応キーワード（スクレイピング、純粋LLM等）が含まれる案件を事前除外してスカウト
        """
        logger.info("🔍 [ScoutEngine] Gateway X 連携 Capability チェック ＆ スカウトを実行中...")

        repo = CompanyRepository()
        rules = repo.fetch_active_capability_rules()

        disallowed_keywords = set()
        if rules:
            for r in rules:
                kw = r.get("keyword")
                allowed = r.get("allowed")
                if kw and (allowed is False or allowed == 0 or str(allowed).lower() == "false"):
                    disallowed_keywords.add(kw.lower())

        eligible_pool = []
        for candidate in self.capability_aligned_pool:
            intent_text = (candidate["topic"] + " " + candidate["base_intent"]).lower()
            is_disallowed = any(dk in intent_text for dk in disallowed_keywords)
            if not is_disallowed:
                eligible_pool.append(candidate)

        if not eligible_pool:
            eligible_pool = self.capability_aligned_pool

        with httpx.Client() as client:
            qiita_tags = self._fetch_qiita_trends(client)
            github_repos = self._fetch_github_trending_ai(client)
            hn_stories = self._fetch_hacker_news_top(client)

        base_opportunity = random.choice(eligible_pool)

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
