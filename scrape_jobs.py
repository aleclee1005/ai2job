#!/usr/bin/env python3
"""
Scrape AI-related job listings from Doda and generate site/live_jobs.json.

Usage:
    pip install httpx beautifulsoup4
    python scrape_jobs.py

The script searches Doda for multiple AI keywords, deduplicates results,
and writes site/live_jobs.json which the frontend reads automatically.

Note: Doda's HTML structure may change. If no jobs are found, inspect the
selectors in parse_html_job() against the current Doda HTML.
"""

import httpx
import json
import re
import time
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Keywords to search; each produces up to MAX_PAGES pages of results
AI_KEYWORDS = [
    "AIエンジニア",
    "機械学習エンジニア",
    "データサイエンティスト",
    "生成AI",
    "LLMエンジニア",
    "MLOpsエンジニア",
    "データエンジニア",
]

MAX_PAGES = 3        # pages per keyword (Doda shows ~20 jobs/page)
REQUEST_DELAY = 1.5  # seconds between requests — be polite

# ── Role classification ───────────────────────────────────────────────────────

ROLE_PATTERNS = {
    "生成AI・LLM":             ["生成AI", "LLM", "ChatGPT", "GPT", "Gemini", "生成系AI", "RAG"],
    "MLOps・AI基盤":           ["MLOps", "ML基盤", "AI基盤", "Kubeflow", "MLflow"],
    "機械学習エンジニア":       ["機械学習", "Machine Learning", "深層学習", "ディープラーニング",
                                 "コンピュータビジョン", "自然言語処理", "NLP", "CV"],
    "データサイエンティスト":   ["データサイエンティスト", "Data Scientist", "統計解析", "分析モデル"],
    "データエンジニア":         ["データエンジニア", "Data Engineer", "データ基盤", "ETL", "パイプライン",
                                 "dbt", "Spark", "データウェアハウス"],
    "AIプロダクトマネージャー": ["AIプロダクト", "AI PM", "AIビジネス", "AI戦略", "DXコンサル"],
    "AIエンジニア":             ["AIエンジニア", "AI開発", "AI engineer"],  # broad fallback
}

SKILL_KEYWORDS = [
    "Python", "SQL", "R言語", "Scala", "Julia",
    "PyTorch", "TensorFlow", "scikit-learn", "Keras", "JAX",
    "LangChain", "LlamaIndex", "OpenAI API", "Hugging Face",
    "Spark", "BigQuery", "Redshift", "Snowflake", "dbt",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes",
    "MLflow", "Airflow", "Kubeflow", "Prefect",
    "Tableau", "Looker", "Power BI",
    "機械学習", "深層学習", "自然言語処理", "画像認識", "強化学習",
]


def categorize_role(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    for role, patterns in ROLE_PATTERNS.items():
        if any(p.lower() in text for p in patterns):
            return role
    return "その他AI関連"


def extract_skills(text: str) -> list[str]:
    return [s for s in SKILL_KEYWORDS if s.lower() in text.lower()]


def parse_salary(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    text = text.replace(",", "").replace("，", "")
    # e.g. "500〜800万円" or "500～800万円"
    m = re.search(r"(\d+)[〜～\-–]+(\d+)万円", text)
    if m:
        return int(m.group(1)) * 10000, int(m.group(2)) * 10000
    m = re.search(r"(\d+)万円", text)
    if m:
        v = int(m.group(1)) * 10000
        return v, v
    return None, None


# ── Doda scraping ─────────────────────────────────────────────────────────────

# Doda's path-based search URL
DODA_SEARCH = "https://doda.jp/DodaFront/View/JobSearchList/j_keyword={kw}/j_page={page}/"

# CSS selector sets to try in order (Doda occasionally renames classes)
TITLE_SELECTORS    = [".cassette__title a", ".unitJob__title a", "h3.jobListUnit__title a", "h3 a"]
COMPANY_SELECTORS  = [".cassette__company", ".unitJob__company", "[class*='company']", "[class*='corp']"]
SALARY_SELECTORS   = [".cassette__salary", ".unitJob__salary", "[class*='salary']", "[class*='money']"]
LOCATION_SELECTORS = [".cassette__area",   ".unitJob__area",   "[class*='area']",   "[class*='place']"]
ITEM_SELECTORS     = [".cassette__item", ".unitJob", ".jobListUnit__item", "[class*='jobItem']", "article"]


def _first_text(soup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return ""


def _first_href(soup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get("href"):
            href = el["href"]
            return href if href.startswith("http") else "https://doda.jp" + href
    return ""


def parse_jsonld_jobs(soup) -> list[dict]:
    jobs = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") != "JobPosting":
                    continue
                title = item.get("title", "")
                desc  = item.get("description", "")
                sal   = item.get("baseSalary", {}).get("value", {})
                smin  = sal.get("minValue")
                smax  = sal.get("maxValue")
                if smin: smin = int(smin)
                if smax: smax = int(smax)
                loc_data = item.get("jobLocation", {})
                if isinstance(loc_data, list):
                    loc_data = loc_data[0] if loc_data else {}
                location = (loc_data.get("address", {}) or {}).get("addressRegion", "")
                jobs.append({
                    "title":         title,
                    "company":       (item.get("hiringOrganization") or {}).get("name", ""),
                    "location":      location,
                    "salary_min":    smin,
                    "salary_max":    smax,
                    "role_category": categorize_role(title, desc),
                    "skills":        extract_skills(desc),
                    "url":           item.get("url", ""),
                    "posted":        item.get("datePosted", ""),
                    "description":   desc[:200],
                })
        except Exception:
            pass
    return jobs


def parse_html_jobs(soup) -> list[dict]:
    jobs = []
    # Try to find job item containers
    items = []
    for sel in ITEM_SELECTORS:
        items = soup.select(sel)
        if len(items) >= 3:
            break
    for item in items:
        title = _first_text(item, TITLE_SELECTORS)
        if not title:
            continue
        url     = _first_href(item, TITLE_SELECTORS)
        company = _first_text(item, COMPANY_SELECTORS)
        sal_txt = _first_text(item, SALARY_SELECTORS)
        loc     = _first_text(item, LOCATION_SELECTORS)
        smin, smax = parse_salary(sal_txt)
        full_text = item.get_text(" ")
        jobs.append({
            "title":         title,
            "company":       company,
            "location":      loc,
            "salary_min":    smin,
            "salary_max":    smax,
            "role_category": categorize_role(title, full_text),
            "skills":        extract_skills(full_text),
            "url":           url,
            "posted":        "",
            "description":   "",
        })
    return jobs


def scrape_keyword(client: httpx.Client, keyword: str, max_pages: int) -> list[dict]:
    jobs = []
    for page in range(1, max_pages + 1):
        url = DODA_SEARCH.format(kw=keyword, page=page)
        try:
            r = client.get(url, timeout=20)
            if r.status_code != 200:
                print(f"    HTTP {r.status_code} — stopping pagination")
                break
            soup = BeautifulSoup(r.text, "html.parser")
            found = parse_jsonld_jobs(soup)
            if not found:
                found = parse_html_jobs(soup)
            print(f"    page {page}: {len(found)} jobs")
            jobs.extend(found)
            if not found:
                break
        except Exception as e:
            print(f"    Error: {e}")
            break
        time.sleep(REQUEST_DELAY)
    return jobs


def deduplicate(jobs: list[dict]) -> list[dict]:
    seen: set = set()
    result = []
    for j in jobs:
        key = (j["title"].strip(), j["company"].strip())
        if key not in seen and key[0]:
            seen.add(key)
            result.append(j)
    return result


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(jobs: list[dict]) -> dict:
    by_role: dict[str, list] = defaultdict(list)
    for j in jobs:
        by_role[j["role_category"]].append(j)

    role_counts = {r: len(jj) for r, jj in sorted(by_role.items(), key=lambda x: -len(x[1]))}

    salary_by_role: dict[str, dict] = {}
    for role, jj in by_role.items():
        vals = [j["salary_min"] for j in jj if j.get("salary_min")]
        maxs = [j["salary_max"] for j in jj if j.get("salary_max")]
        if vals:
            salary_by_role[role] = {
                "min": min(vals),
                "avg": int(sum(vals) / len(vals)),
                "max": max(maxs) if maxs else max(vals),
            }

    skill_counts: dict[str, int] = defaultdict(int)
    for j in jobs:
        for s in j.get("skills", []):
            skill_counts[s] += 1
    top_skills = dict(sorted(skill_counts.items(), key=lambda x: -x[1])[:20])

    return {
        "updated_at":    datetime.now().isoformat(),
        "source":        "doda.jp",
        "total":         len(jobs),
        "jobs":          jobs[:200],
        "by_role":       role_counts,
        "salary_by_role": salary_by_role,
        "top_skills":    top_skills,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Scraping AI jobs from doda.jp …")
    all_jobs: list[dict] = []

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for kw in AI_KEYWORDS:
            print(f"  Keyword: {kw}")
            jobs = scrape_keyword(client, kw, MAX_PAGES)
            print(f"  → {len(jobs)} raw results")
            all_jobs.extend(jobs)

    all_jobs = deduplicate(all_jobs)
    print(f"\nTotal after deduplication: {len(all_jobs)}")

    if not all_jobs:
        print(
            "\nWARNING: No jobs found. Doda's HTML structure may have changed.\n"
            "Inspect the page source and update the selectors in parse_html_jobs()."
        )

    out = aggregate(all_jobs)
    out_path = Path(__file__).parent / "site" / "live_jobs.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Saved → {out_path}  ({len(all_jobs)} jobs)")


if __name__ == "__main__":
    main()
