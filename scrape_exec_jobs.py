#!/usr/bin/env python3
"""
Multi-source async scraper for executive AI roles in Japan.

Sources:
  - Doda          (httpx + BeautifulSoup)
  - 求人ボックス   (httpx + BeautifulSoup)
  - Indeed Japan  (Playwright, async)
  - LinkedIn      (Playwright, async, best-effort)

Usage:
    pip install httpx beautifulsoup4 playwright
    playwright install chromium
    python scrape_exec_jobs.py

Output: site/exec_jobs.json
"""

import asyncio
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# ── Constants ─────────────────────────────────────────────────────────────────

REQUEST_DELAY = 1.5   # seconds between httpx requests
MAX_JOBS = 150        # cap on jobs written to JSON
MAX_PAGES_HTTPX = 3   # pages per keyword for httpx sources

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OUT_PATH = Path(__file__).parent / "site" / "exec_jobs.json"

# ── Role metadata ─────────────────────────────────────────────────────────────

ROLE_METADATA = {
    "CAIO": {
        "name_en": "Chief AI Officer",
        "name_ja": "最高AI責任者",
        "icon": "⚡",
        "color": "#9a6a2a",
        "keywords": [
            "CAIO",
            "Chief AI Officer",
            "最高AI責任者",
            "Chief Artificial Intelligence Officer",
        ],
        "description_ja": (
            "企業全体のAI戦略を統括し、AI導入による事業変革を牽引する最高責任者。"
            "CEOや取締役会への直接報告ラインを持ち、AI投資の優先順位付け・組織設計・"
            "倫理ガバナンスを一手に担う。2023年以降、日本の大手企業・外資系企業でも急速に設置が進んでいる。"
        ),
        "responsibilities_ja": [
            "全社AI戦略の策定と実行ロードマップの管理",
            "AI研究開発・データ基盤チームの組織設計・採用・育成",
            "CEO・取締役会へのAIリスクと機会の説明責任",
            "外部パートナー（クラウドベンダー・研究機関）との戦略的連携",
            "AI倫理・ガバナンス・コンプライアンスフレームワークの構築",
        ],
        "background_ja": (
            "AI研究者・データサイエンティスト出身が多く、MBA取得者や事業開発・経営経験を"
            "併せ持つ人材が求められる。英語力必須の企業も多い。"
        ),
    },
    "AI Director / Head of AI": {
        "name_en": "AI Director / Head of AI",
        "name_ja": "AIディレクター / AIヘッド",
        "icon": "🎯",
        "color": "#4a6a9a",
        "keywords": [
            "AI Director",
            "Head of AI",
            "AIディレクター",
            "AI責任者",
            "Director of AI",
            "AIリード",
            "AI部門長",
        ],
        "description_ja": (
            "AI部門・AIラボの実務責任者として、AIプロジェクトの計画・実行・品質管理を担う。"
            "CAIOの下に位置することが多く、特定の事業部門または技術領域（NLP・CV・生成AIなど）の"
            "AI戦略を主導する。"
        ),
        "responsibilities_ja": [
            "AI/MLプロジェクトのポートフォリオ管理と優先順位付け",
            "AI研究チーム・エンジニアリングチームのマネジメント（10〜50名規模）",
            "事業部門とのAI要件定義・PoC推進・本番展開支援",
            "AIモデルの品質・公平性・説明可能性の監督",
            "AI技術動向の把握と社内技術戦略への反映",
        ],
        "background_ja": (
            "機械学習・データサイエンスの深い技術バックグラウンドを持ち、"
            "10名以上のチームマネジメント経験が必要。博士号保有者も多い。"
        ),
    },
    "VP of AI / AI Strategy Lead": {
        "name_en": "VP of AI / AI Strategy Lead",
        "name_ja": "AI担当VP / AI戦略リード",
        "icon": "📈",
        "color": "#6a4a9a",
        "keywords": [
            "VP of AI",
            "VP AI",
            "AI Strategy Lead",
            "AI Vice President",
            "AI戦略責任者",
            "AI戦略リード",
            "AIストラテジスト",
        ],
        "description_ja": (
            "AIの事業価値化・マネタイズ戦略を主導する経営幹部職。技術的なAI知識と事業戦略の双方を橋渡しし、"
            "AI投資のROI最大化・新規AI事業の立ち上げ・パートナーシップ構築を担う。"
            "外資系企業での設置が先行しているが日本企業でも増加中。"
        ),
        "responsibilities_ja": [
            "AI投資ポートフォリオの戦略立案とROI管理",
            "AI新規事業の立ち上げとP&L責任",
            "経営幹部・取締役会向けのAI戦略プレゼンテーション",
            "AI関連M&A・パートナーシップの主導",
            "AI規制動向・競合分析の把握と戦略反映",
        ],
        "background_ja": (
            "戦略コンサルタント・投資銀行出身者やAI系スタートアップ経験者が多い。"
            "MBAまたは技術系修士以上が一般的。"
        ),
    },
    "AI Product Lead / AI事業責任者": {
        "name_en": "AI Product Lead / AI Business Lead",
        "name_ja": "AIプロダクトリード / AI事業責任者",
        "icon": "🚀",
        "color": "#2a7a5a",
        "keywords": [
            "AI Product Lead",
            "AI事業責任者",
            "AIプロダクトリード",
            "AI Product Director",
            "Head of AI Product",
            "AI Product Manager Lead",
            "AI事業開発責任者",
        ],
        "description_ja": (
            "AI機能・AIプロダクトの企画から市場投入まで責任を持つプロダクト経営職。"
            "エンジニア・デザイナー・ビジネス開発チームを横断的に率い、顧客価値に直結する"
            "AIプロダクトを高速で開発・改善する。SaaS・プラットフォーム企業での需要が最も高い。"
        ),
        "responsibilities_ja": [
            "AI機能のプロダクトロードマップ策定と優先順位管理",
            "クロスファンクショナルチーム（エンジニア・DS・UX・ビジネス）のリード",
            "ユーザーリサーチに基づくAIプロダクト要件定義",
            "AIプロダクトのKPI設計・A/Bテスト・改善サイクルの運営",
            "AIプロダクトの価格戦略・GTM（市場投入）戦略の立案",
        ],
        "background_ja": (
            "プロダクトマネージャー経験5年以上、かつAIプロダクトの開発経験が必要。"
            "技術的なAI知識（APIの仕組み・モデル評価など）も求められる。"
        ),
    },
}

# ── Search keywords per role ──────────────────────────────────────────────────

EXEC_KEYWORDS = [
    "CAIO",
    "Chief AI Officer",
    "AI Director",
    "Head of AI",
    "VP of AI",
    "AI戦略責任者",
    "AI事業責任者",
    "AIプロダクトリード",
    "AI Product Lead",
    "AIディレクター",
    "AI部門長",
]

# ── Skills to extract ─────────────────────────────────────────────────────────

EXEC_SKILLS = [
    "AI戦略",
    "組織変革",
    "LLM",
    "生成AI",
    "機械学習",
    "ステークホルダー管理",
    "英語",
    "MBA",
    "P&L管理",
    "予算管理",
    "チームビルディング",
    "Python",
    "データ分析",
    "プロダクト管理",
    "アジャイル",
    "クラウド",
    "AWS",
    "GCP",
    "Azure",
    "MLOps",
    "Board reporting",
    "DX推進",
    "事業戦略",
    "M&A",
]

# ── Company type heuristics ───────────────────────────────────────────────────

COMPANY_TYPE_PATTERNS = [
    (["コンサル", "Consulting", "Deloitte", "McKinsey", "BCG", "Accenture", "PwC", "KPMG", "EY"], "コンサルティング"),
    (["Bank", "銀行", "Mizuho", "みずほ", "三菱UFJ", "三井住友", "野村", "大和"], "金融・銀行"),
    (["Microsoft", "Google", "Amazon", "Apple", "Meta", "IBM", "SAP", "Oracle", "Salesforce"], "外資系IT"),
    (["SoftBank", "ソフトバンク", "NTT", "KDDI", "au ", "Rakuten", "楽天", "LINE", "Yahoo"], "通信・インターネット"),
    (["Toyota", "トヨタ", "Honda", "ホンダ", "Sony", "ソニー", "Panasonic", "パナソニック", "Hitachi", "日立", "Fujitsu", "富士通", "NEC", "Canon", "キヤノン", "Denso", "デンソー"], "製造・電機"),
    (["Mercari", "メルカリ", "PKSHA", "LayerX", "Preferred", "Abeja", "スタートアップ"], "AIスタートアップ・IT"),
    (["Recruit", "リクルート", "Persol", "パーソル", "Mynavi", "マイナビ"], "HR・人材"),
]


def infer_company_type(company: str) -> str:
    for patterns, label in COMPANY_TYPE_PATTERNS:
        for p in patterns:
            if p.lower() in company.lower():
                return label
    return "IT・通信"


# ── Salary parsing ────────────────────────────────────────────────────────────

_SALARY_IGNORE = re.compile(r"応相談|非公開|要相談|面談|詳細|給与詳細", re.IGNORECASE)
_SALARY_RANGE = re.compile(r"(\d[\d,，]*)\s*[〜~－\-]\s*(\d[\d,，]*)\s*万円", re.IGNORECASE)
_SALARY_SINGLE = re.compile(r"(?:年収|給与)?(\d[\d,，]+)\s*万円", re.IGNORECASE)
_SALARY_OVER = re.compile(r"年収\s*(\d[\d,，]+)\s*万円以上", re.IGNORECASE)


def _clean_num(s: str) -> int:
    return int(s.replace(",", "").replace("，", ""))


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    """Return (salary_min_万円, salary_max_万円) or (None, None)."""
    if not text:
        return None, None
    if _SALARY_IGNORE.search(text):
        return None, None

    m = _SALARY_RANGE.search(text)
    if m:
        return _clean_num(m.group(1)), _clean_num(m.group(2))

    m = _SALARY_OVER.search(text)
    if m:
        v = _clean_num(m.group(1))
        return v, None

    m = _SALARY_SINGLE.search(text)
    if m:
        v = _clean_num(m.group(1))
        return v, v

    return None, None


# ── Role classification ───────────────────────────────────────────────────────

def classify_role(title: str, description: str = "") -> str:
    combined = f"{title} {description}".lower()
    for role_name, meta in ROLE_METADATA.items():
        for kw in meta["keywords"]:
            if kw.lower() in combined:
                return role_name
    return "その他AI関連"


# ── Skills extraction ─────────────────────────────────────────────────────────

def extract_skills(text: str) -> list[str]:
    found = []
    low = text.lower()
    for skill in EXEC_SKILLS:
        if skill.lower() in low:
            found.append(skill)
    return found


# ── Deduplication key ─────────────────────────────────────────────────────────

def dedup_key(job: dict) -> tuple:
    title = re.sub(r"\s+", "", job.get("title", "")).lower()
    company = re.sub(r"\s+", "", job.get("company", "")).lower()
    return (title, company)


# ══════════════════════════════════════════════════════════════════════════════
#  Source: Doda  (httpx + BeautifulSoup)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_doda(keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    seen: set = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for kw in keywords:
            for page in range(1, MAX_PAGES_HTTPX + 1):
                url = (
                    f"https://doda.jp/DodaFront/View/JobSearchList/"
                    f"j_keyword={httpx.URL('').copy_with(params={'q': kw}).params}/"
                    f"j_page={page}/"
                )
                # Build URL manually to keep path segments correct
                encoded_kw = kw.replace(" ", "+")
                url = (
                    f"https://doda.jp/DodaFront/View/JobSearchList/"
                    f"j_keyword={encoded_kw}/j_page={page}/"
                )
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        break
                    page_jobs = _parse_doda_page(resp.text, url)
                    if not page_jobs:
                        break
                    for j in page_jobs:
                        k = dedup_key(j)
                        if k not in seen:
                            seen.add(k)
                            jobs.append(j)
                except Exception as exc:
                    print(f"[Doda] error on {url}: {exc}")
                    break
                time.sleep(REQUEST_DELAY)

    print(f"[Doda] {len(jobs)} jobs collected")
    return jobs


def _parse_doda_page(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    # Try JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("JobPosting", "jobPosting"):
                    title = item.get("title", "")
                    company = ""
                    org = item.get("hiringOrganization", {})
                    if isinstance(org, dict):
                        company = org.get("name", "")
                    location = ""
                    loc = item.get("jobLocation", {})
                    if isinstance(loc, dict):
                        addr = loc.get("address", {})
                        location = addr.get("addressLocality", "") or addr.get("addressRegion", "")
                    salary_text = item.get("baseSalary", {})
                    if isinstance(salary_text, dict):
                        salary_text = str(salary_text.get("value", ""))
                    else:
                        salary_text = str(salary_text)
                    sal_min, sal_max = parse_salary(salary_text)
                    description = item.get("description", "")[:200]
                    url = item.get("url", page_url)
                    posted = item.get("datePosted", "")
                    skills = extract_skills(f"{title} {description}")
                    role = classify_role(title, description)
                    if role == "その他AI関連":
                        continue
                    jobs.append({
                        "title": title,
                        "company": company,
                        "company_type": infer_company_type(company),
                        "location": location or "日本",
                        "salary_min": sal_min,
                        "salary_max": sal_max,
                        "role_category": role,
                        "skills": skills,
                        "source": "doda.jp",
                        "source_label": "Doda",
                        "url": url,
                        "posted": posted,
                        "description": description,
                    })
        except Exception:
            pass

    if jobs:
        return jobs

    # Fallback: HTML selectors
    # Title selectors
    title_sel = [".cassette__title a", ".unitJob__title a", "h3 a", ".jobTitle a"]
    company_sel = [".cassette__company", "[class*='company']"]
    salary_sel = [".cassette__salary", "[class*='salary']"]

    cards = soup.select(
        "article.cassette, li.cassette, .unitJob, [class*='jobCard'], [class*='job-card']"
    )
    if not cards:
        cards = soup.select("li")  # broad fallback

    for card in cards:
        title_el = None
        for sel in title_sel:
            title_el = card.select_one(sel)
            if title_el:
                break
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        company = ""
        for sel in company_sel:
            el = card.select_one(sel)
            if el:
                company = el.get_text(strip=True)
                break

        salary_text = ""
        for sel in salary_sel:
            el = card.select_one(sel)
            if el:
                salary_text = el.get_text(strip=True)
                break

        href = title_el.get("href", "")
        url = f"https://doda.jp{href}" if href.startswith("/") else href or page_url
        sal_min, sal_max = parse_salary(salary_text)
        description = card.get_text(separator=" ", strip=True)[:200]
        skills = extract_skills(f"{title} {description}")
        role = classify_role(title, description)
        if role == "その他AI関連":
            continue

        jobs.append({
            "title": title,
            "company": company,
            "company_type": infer_company_type(company),
            "location": "日本",
            "salary_min": sal_min,
            "salary_max": sal_max,
            "role_category": role,
            "skills": skills,
            "source": "doda.jp",
            "source_label": "Doda",
            "url": url,
            "posted": "",
            "description": description,
        })

    return jobs


# ══════════════════════════════════════════════════════════════════════════════
#  Source: 求人ボックス  (httpx + BeautifulSoup)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_kyujinbox(keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    seen: set = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for kw in keywords:
            for page in range(1, MAX_PAGES_HTTPX + 1):
                url = f"https://kyujinbox.com/search?q={kw.replace(' ', '+')}&page={page}"
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        break
                    page_jobs = _parse_kyujinbox_page(resp.text, url)
                    if not page_jobs:
                        break
                    for j in page_jobs:
                        k = dedup_key(j)
                        if k not in seen:
                            seen.add(k)
                            jobs.append(j)
                except Exception as exc:
                    print(f"[求人ボックス] error on {url}: {exc}")
                    break
                time.sleep(REQUEST_DELAY)

    print(f"[求人ボックス] {len(jobs)} jobs collected")
    return jobs


def _parse_kyujinbox_page(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    # Job card selectors
    cards = soup.select("article, .job-card, [class*='job_item'], [class*='jobItem']")
    if not cards:
        # Try broader: any div/li with a heading link
        cards = soup.select("li, div.item")

    for card in cards:
        title_el = card.select_one("h2 a, h3 a, h1 a, .job-title a, [class*='title'] a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        company = ""
        for sel in ["[class*='company']", "[class*='employer']", "span.company"]:
            el = card.select_one(sel)
            if el:
                company = el.get_text(strip=True)
                break

        salary_text = ""
        for sel in ["[class*='salary']", "[class*='wage']", "[class*='pay']"]:
            el = card.select_one(sel)
            if el:
                salary_text = el.get_text(strip=True)
                break

        href = title_el.get("href", "")
        url = f"https://kyujinbox.com{href}" if href.startswith("/") else href or page_url
        sal_min, sal_max = parse_salary(salary_text)
        description = card.get_text(separator=" ", strip=True)[:200]
        skills = extract_skills(f"{title} {description}")
        role = classify_role(title, description)
        if role == "その他AI関連":
            continue

        jobs.append({
            "title": title,
            "company": company,
            "company_type": infer_company_type(company),
            "location": "日本",
            "salary_min": sal_min,
            "salary_max": sal_max,
            "role_category": role,
            "skills": skills,
            "source": "kyujinbox.com",
            "source_label": "求人ボックス",
            "url": url,
            "posted": "",
            "description": description,
        })

    return jobs


# ══════════════════════════════════════════════════════════════════════════════
#  Source: Indeed Japan  (Playwright, async)
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_indeed(keywords: list[str], browser) -> list[dict]:
    jobs: list[dict] = []
    seen: set = set()

    for kw in keywords:
        encoded_kw = kw.replace(" ", "+")
        url = (
            f"https://jp.indeed.com/jobs?q={encoded_kw}"
            f"&l=%E6%97%A5%E6%9C%AC&sort=date"
        )
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=30000)
            # Wait for job cards
            try:
                await page.wait_for_selector(
                    '[data-testid="slider_item"], .job_seen_beacon',
                    timeout=10000,
                )
            except Exception:
                pass
            await asyncio.sleep(2)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            cards = soup.select('[data-testid="slider_item"], .job_seen_beacon, .jobsearch-ResultsList > li')
            for card in cards:
                # Title
                title_el = card.select_one(
                    '[data-testid="jobTitle"] span, h2.jobTitle span, h2.jobTitle a'
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue

                # Company
                company_el = card.select_one('[data-testid="company-name"]')
                company = company_el.get_text(strip=True) if company_el else ""

                # Location
                location_el = card.select_one('[data-testid="text-location"]')
                location = location_el.get_text(strip=True) if location_el else "日本"

                # Salary
                salary_el = card.select_one('[data-testid="attribute_snippet_testid"]')
                salary_text = salary_el.get_text(strip=True) if salary_el else ""
                sal_min, sal_max = parse_salary(salary_text)

                # URL
                link_el = card.select_one("a[href*='/rc/clk'], a[id*='job_']")
                href = link_el.get("href", "") if link_el else ""
                job_url = f"https://jp.indeed.com{href}" if href.startswith("/") else href or url

                description = card.get_text(separator=" ", strip=True)[:200]
                skills = extract_skills(f"{title} {description}")
                role = classify_role(title, description)
                if role == "その他AI関連":
                    continue

                j = {
                    "title": title,
                    "company": company,
                    "company_type": infer_company_type(company),
                    "location": location,
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "role_category": role,
                    "skills": skills,
                    "source": "jp.indeed.com",
                    "source_label": "Indeed",
                    "url": job_url,
                    "posted": "",
                    "description": description,
                }
                k = dedup_key(j)
                if k not in seen:
                    seen.add(k)
                    jobs.append(j)

        except Exception as exc:
            print(f"[Indeed] error on {url}: {exc}")
        finally:
            await page.close()
            await asyncio.sleep(2)

    print(f"[Indeed] {len(jobs)} jobs collected")
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
#  Source: LinkedIn  (Playwright, async, best-effort)
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_linkedin(keywords: list[str], browser) -> list[dict]:
    jobs: list[dict] = []
    seen: set = set()

    try:
        for kw in keywords:
            encoded_kw = kw.replace(" ", "%20")
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={encoded_kw}&location=Japan&f_TP=1"
            )
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=30000)
                try:
                    await page.wait_for_selector(
                        ".base-card, .job-search-card",
                        timeout=10000,
                    )
                except Exception:
                    pass
                await asyncio.sleep(2)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                cards = soup.select(".base-card, .job-search-card")
                for card in cards:
                    title_el = card.select_one("h3.base-search-card__title")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title:
                        continue

                    company_el = card.select_one("h4.base-search-card__subtitle")
                    company = company_el.get_text(strip=True) if company_el else ""

                    location_el = card.select_one("span.job-search-card__location")
                    location = location_el.get_text(strip=True) if location_el else "日本"

                    link_el = card.select_one("a.base-card__full-link, a[href*='linkedin.com/jobs']")
                    job_url = link_el.get("href", url) if link_el else url

                    description = card.get_text(separator=" ", strip=True)[:200]
                    skills = extract_skills(f"{title} {description}")
                    role = classify_role(title, description)
                    if role == "その他AI関連":
                        continue

                    j = {
                        "title": title,
                        "company": company,
                        "company_type": infer_company_type(company),
                        "location": location,
                        "salary_min": None,
                        "salary_max": None,
                        "role_category": role,
                        "skills": skills,
                        "source": "linkedin.com",
                        "source_label": "LinkedIn",
                        "url": job_url,
                        "posted": "",
                        "description": description,
                    }
                    k = dedup_key(j)
                    if k not in seen:
                        seen.add(k)
                        jobs.append(j)

            except Exception as exc:
                print(f"[LinkedIn] error on {url}: {exc}")
            finally:
                await page.close()
                await asyncio.sleep(2)

    except Exception as exc:
        print(f"[LinkedIn] scrape failed (best-effort, continuing): {exc}")

    print(f"[LinkedIn] {len(jobs)} jobs collected")
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
#  Async Playwright runner
# ══════════════════════════════════════════════════════════════════════════════

async def run_playwright_scrapers(keywords: list[str]) -> tuple[list[dict], list[dict]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Playwright] not installed — skipping Indeed & LinkedIn")
        return [], []

    indeed_jobs: list[dict] = []
    linkedin_jobs: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        indeed_jobs, linkedin_jobs = await asyncio.gather(
            scrape_indeed(keywords, browser),
            scrape_linkedin(keywords, browser),
        )
        await browser.close()

    return indeed_jobs, linkedin_jobs


# ══════════════════════════════════════════════════════════════════════════════
#  Aggregation helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_role_aggregations(jobs: list[dict]) -> dict:
    """Build per-role stats: count, salary stats, top_skills, top_companies."""
    role_jobs: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        role_jobs[j["role_category"]].append(j)

    result: dict = {}
    for role_name, meta in ROLE_METADATA.items():
        rjobs = role_jobs.get(role_name, [])
        salaries_min = [j["salary_min"] for j in rjobs if j.get("salary_min")]
        salaries_max = [j["salary_max"] for j in rjobs if j.get("salary_max")]
        all_salaries = salaries_min + salaries_max

        salary_stat = None
        if all_salaries:
            salary_stat = {
                "min": min(salaries_min) if salaries_min else None,
                "avg": round(sum(all_salaries) / len(all_salaries)),
                "max": max(salaries_max) if salaries_max else None,
            }

        skill_counter: Counter = Counter()
        for j in rjobs:
            for s in j.get("skills", []):
                skill_counter[s] += 1
        top_skills = [s for s, _ in skill_counter.most_common(6)]

        company_counter: Counter = Counter()
        for j in rjobs:
            if j.get("company"):
                company_counter[j["company"]] += 1
        top_companies = [c for c, _ in company_counter.most_common(5)]

        result[role_name] = {
            "name_en": meta["name_en"],
            "name_ja": meta["name_ja"],
            "icon": meta["icon"],
            "color": meta["color"],
            "description_ja": meta["description_ja"],
            "responsibilities_ja": meta["responsibilities_ja"],
            "background_ja": meta["background_ja"],
            "count": len(rjobs),
            "salary": salary_stat,
            "top_skills": top_skills,
            "top_companies": top_companies,
        }

    return result


def build_output(jobs: list[dict], sources: list[str], is_sample: bool = False) -> dict:
    by_source: Counter = Counter(j["source"] for j in jobs)
    by_role: Counter = Counter(j["role_category"] for j in jobs)
    roles = build_role_aggregations(jobs)

    out = {
        "updated_at": datetime.now().isoformat(),
        "sources": sources,
        "total": len(jobs),
        "roles": roles,
        "jobs": jobs[:MAX_JOBS],
        "by_source": dict(by_source),
        "by_role": dict(by_role),
    }
    if is_sample:
        out["note"] = "サンプルデータ。scrape_exec_jobs.pyを実行してリアルデータに差し替えてください。"
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=== Executive AI Jobs Scraper ===")

    # 1. httpx-based scrapers (synchronous)
    doda_jobs = scrape_doda(EXEC_KEYWORDS)
    kyujin_jobs = scrape_kyujinbox(EXEC_KEYWORDS)

    # 2. Playwright-based scrapers (async)
    indeed_jobs, linkedin_jobs = asyncio.run(
        run_playwright_scrapers(EXEC_KEYWORDS)
    )

    # 3. Combine all jobs
    all_jobs: list[dict] = doda_jobs + kyujin_jobs + indeed_jobs + linkedin_jobs

    # 4. Global deduplication by (title, company)
    seen: set = set()
    deduped: list[dict] = []
    for j in all_jobs:
        k = dedup_key(j)
        if k not in seen:
            seen.add(k)
            deduped.append(j)

    print(f"\nTotal after dedup: {len(deduped)} jobs")

    # 5. Guard: if nothing found, don't overwrite existing file
    if len(deduped) == 0:
        print(
            f"No jobs found — keeping existing {OUT_PATH} intact (if present)."
        )
        return

    # 6. Determine which sources actually returned data
    sources = sorted({j["source"] for j in deduped})

    # 7. Build output and write
    output = build_output(deduped, sources, is_sample=False)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(deduped)} jobs to {OUT_PATH}")


if __name__ == "__main__":
    main()
