# 日本の職業市場とAI

**Japan Job Market & AI Visualizer** — An interactive treemap of 556 Japanese occupations, colored by job outlook, pay, education, and AI exposure.

👉 **[Live Demo](https://aleclee1005.github.io/ai2job/)**

---

## 背景 / Background

This project was directly inspired by [Andrej Karpathy](https://karpathy.ai/)'s **[US Job Market Visualizer](https://karpathy.ai/jobs/)** ([GitHub](https://github.com/karpathy/jobs)), which visualizes US occupations from BLS data. I wanted to build the same thing for Japan, using Japanese government data and LLM scoring.

Karpathy's original idea — squarified treemap + LLM-powered scoring of every occupation — is elegant and I tried to apply it faithfully to the Japanese labor market context.

## データ / Data Sources

| Source | Contents |
|--------|----------|
| [jobtag (厚生労働省)](https://shigoto.mhlw.go.jp/) | 556 occupations: title, category, description, worker count, job-to-applicant ratio |
| [e-Stat 賃金構造基本統計調査 2022](https://www.e-stat.go.jp/) | Average annual pay, education level by occupation |
| Google Gemini 2.0 Flash (via OpenRouter) | AI exposure score (0–10) and employment outlook (-5 to +5) — 1,112 LLM calls total |

## 仕組み / How It Works

1. **Data pipeline** (`score_jp.py`, `fetch_estat.py`): merges jobtag CSV with e-Stat JSON, then calls Gemini 2.0 Flash to score each occupation on two dimensions
2. **LLM scoring prompts**:
   - *AI Exposure (0–10)*: how much will AI reshape this occupation?
   - *Employment Outlook (-5 to +5)*: 10-year hiring trend for Japan
3. **Frontend** (`site/index.html`): vanilla JS + HTML5 Canvas, squarified treemap algorithm, no frameworks

## 特徴 / Features

- **面積** = 就業者数の√に比例（極端な差を視覚的に調整）
- **4つの色レイヤー**: 雇用見通し・年収・学歴・AI影響度
- **5大分類**: 専門技術 / 事務系 / 現場系 / サービス・その他 / 管理類
- **専門技術** をさらに IT・デジタル / 法律・教育・言語 / 医療・理工・その他 に細分化
- タイルクリックで jobtag 詳細ページへ

## 主な知見 / Key Findings

- 平均雇用見通し **+0.5/5**（微増傾向）
- 医療・介護・看護系が最も強い雇用増（+5/5）— 高齢化社会の影響
- IT・デジタル職種は高AI影響度だが、需要も旺盛で雇用増傾向
- 製造・輸送・事務職は自動化リスクが高く雇用減少傾向（-1〜-3）
- 平均AI影響度 **約5.4/10** — 「高影響＝消滅」ではなく、働き方の大幅な変化を意味する

## 実行方法 / Running Locally

```bash
# Serve the site
cd site && python -m http.server 8765

# Re-score occupations (requires OPENROUTER_API_KEY)
export OPENROUTER_API_KEY=your_key
uv run python score_jp.py
```

## クレジット / Credits

- Inspired by [karpathy.ai/jobs](https://karpathy.ai/jobs/) — the original concept, LLM scoring pipeline approach, and squarified treemap visualization
- Data: 厚生労働省 jobtag · e-Stat 賃金構造基本統計調査 2022
- LLM scoring: Google Gemini 2.0 Flash via [OpenRouter](https://openrouter.ai/)
