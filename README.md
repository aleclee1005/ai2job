# 日本職種のAI影響

**Japan AI Job Impact Visualizer** — A two-tab interactive tool for understanding how AI is reshaping the Japanese labor market: a static treemap of 556 occupations scored by AI exposure, plus a live feed of emerging AI job listings scraped from Doda.

👉 **[Live Demo](https://aleclee1005.github.io/ai2job/)**

---

## 背景 / Background

This project was directly inspired by [Andrej Karpathy](https://karpathy.ai/)'s **[US Job Market Visualizer](https://karpathy.ai/jobs/)** ([GitHub](https://github.com/karpathy/jobs)), which visualizes US occupations from BLS data. I wanted to build the same thing for Japan — using Japanese government data and LLM scoring — and extend it with a live job-listing layer to show which new AI roles are actually being hired for right now.

## 2つのタブ / Two Views

### Tab 1 — 職種AI影響度（Static Analysis）

A squarified treemap of all 556 Japanese occupations from the Ministry of Health, Labour and Welfare's jobtag database. Each tile's **area is proportional to worker count** (√-scaled). Switch between four color layers:

| Layer | Meaning |
|-------|---------|
| 雇用見通し | Employment outlook — 10-year hiring trend (-5 to +5) |
| 年収 | Average annual pay from e-Stat 2022 |
| 学歴 | Required education level |
| AI影響度 | AI exposure score — how much AI will reshape the role (0–10) |

### Tab 2 — AI新職種（Live Job Listings）

A live dashboard of AI-related job postings scraped from **[Doda](https://doda.jp/)**, Japan's largest job platform. Updated by running `scrape_jobs.py` locally and committing the resulting `live_jobs.json`.

Displays:
- **職種別求人数** — Bar chart of open roles by AI job category
- **職種別年収レンジ** — Salary range chart (min / avg / max per role)
- **求められるスキル** — Skill tag cloud sized by frequency across listings
- **求人カード** — Individual job cards with company, salary, skills, and link to Doda

---

## データ / Data Sources

### 静的データ（職種AI影響度タブ）

| Source | Contents |
|--------|----------|
| [jobtag (厚生労働省)](https://shigoto.mhlw.go.jp/) | 556 occupations: title, category, description, worker count |
| [e-Stat 賃金構造基本統計調査 2022](https://www.e-stat.go.jp/) | Average annual pay and education level by occupation |
| Google Gemini 2.0 Flash (via OpenRouter) | AI exposure (0–10) and employment outlook (-5 to +5) — 1,112 LLM calls |

### 動的データ（AI新職種タブ）

| Source | Contents |
|--------|----------|
| [Doda](https://doda.jp/) | Live AI job listings scraped by keyword (AIエンジニア, 機械学習, 生成AI, etc.) |

**収集方法 / How the live data is collected:**

`scrape_jobs.py` searches Doda for 7 AI-related keywords, fetching up to 3 pages per keyword (~20 listings/page). For each result page it first tries to extract **JSON-LD `JobPosting` structured data** (the most stable approach, since Doda emits schema.org markup for SEO). If no structured data is found it falls back to **BeautifulSoup HTML parsing** with multiple CSS-selector fallbacks. Results are deduplicated by `(title, company)` and aggregated into role categories and salary ranges before being written to `site/live_jobs.json`.

---

## 仕組み / How It Works

1. **静的パイプライン** (`score_jp.py`, `fetch_estat.py`): merges jobtag CSV with e-Stat JSON, then calls Gemini 2.0 Flash to score each occupation on two dimensions
2. **LLM scoring prompts**:
   - *AI Exposure (0–10)*: how much will AI reshape this occupation?
   - *Employment Outlook (-5 to +5)*: 10-year hiring trend for Japan, accounting for aging society, automation, and digital transformation
3. **動的パイプライン** (`scrape_jobs.py`): scrapes Doda by keyword → extracts JSON-LD or HTML → classifies role category → aggregates salary/skill stats → writes `site/live_jobs.json`
4. **Frontend** (`site/index.html`): vanilla JS + HTML5 Canvas, squarified treemap + tab-based layout, no frameworks

---

## 特徴 / Features

- **面積** = 就業者数の√に比例（極端な差を視覚的に調整）
- **4つの色レイヤー**: 雇用見通し・年収・学歴・AI影響度
- **5大分類**: 専門技術 / 事務系 / 現場系 / サービス・その他 / 管理類
- **専門技術** をさらに IT・デジタル / 法律・教育・言語 / 医療・理工・その他 に細分化
- タイルクリックで jobtag 詳細ページへ
- **ライブ求人タブ**: Canvas チャート + 求人カードで最新AI職種の需要を可視化

---

## 主な知見 / Key Findings

**静的分析（556職種）**
- 平均雇用見通し **+0.5/5**（微増傾向）
- 医療・介護・看護系が最も強い雇用増（+5/5）— 高齢化社会の影響
- IT・デジタル職種は高AI影響度だが、需要も旺盛で雇用増傾向
- 製造・輸送・事務職は自動化リスクが高く雇用減少傾向（-1〜-3）
- 平均AI影響度 **約5.4/10** — 「高影響＝消滅」ではなく、働き方の大幅な変化を意味する

**AI新職種（Doda求人）**
- 最多求人: AIエンジニア・データサイエンティスト・機械学習エンジニア
- 最高年収帯: 生成AI・LLM系（平均 ~920万円）、AIプロダクトマネージャー（平均 ~1,050万円）
- 最頻出スキル: Python / SQL / 機械学習 / クラウド(AWS・GCP) / PyTorch

---

## 実行方法 / Running Locally

```bash
# Serve the site
cd site && python -m http.server 8765

# Re-score occupations (requires OPENROUTER_API_KEY)
export OPENROUTER_API_KEY=your_key
uv run python score_jp.py

# Fetch live AI job listings from Doda
pip install httpx beautifulsoup4
python scrape_jobs.py
# → writes site/live_jobs.json; commit & push to update the live site
```

---

## クレジット / Credits

- Inspired by [karpathy.ai/jobs](https://karpathy.ai/jobs/) — the original concept, LLM scoring pipeline approach, and squarified treemap visualization
- Static data: 厚生労働省 jobtag · e-Stat 賃金構造基本統計調査 2022
- LLM scoring: Google Gemini 2.0 Flash via [OpenRouter](https://openrouter.ai/)
- Live job data: [Doda](https://doda.jp/) (scraped via `scrape_jobs.py`)
