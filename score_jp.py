"""
Score Japanese occupations on two dimensions using an LLM via OpenRouter:
  1. AI Exposure (0-10): How much will AI reshape this occupation?
  2. Employment Outlook (-5 to +5): Employment growth/decline trend score

Reads from occupations_jp.json + jobtag description text
Writes scores to scores_jp.json (incrementally, resumable)

Usage:
    export OPENROUTER_API_KEY=your_key_here
    uv run python score_jp.py                    # score all 556 occupations
    uv run python score_jp.py --start 0 --end 10 # test first 10
    uv run python score_jp.py --force            # re-score all
    uv run python score_jp.py --model google/gemini-flash-1.5
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import csv

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.0-flash-001"
SCORES_FILE = "scores_jp.json"


# ── Prompts ──────────────────────────────────────────────────────────────────

AI_EXPOSURE_SYSTEM = """You are an expert labor economist analyzing how AI will reshape occupations in Japan's job market.

Score each occupation's AI exposure from 0 to 10:

0-1 (Minimal): Physical/manual work AI cannot replicate. Examples: 大工, 農家, 介護ヘルパー (physical hands-on)
2-3 (Low): Mostly physical with some digital components. Examples: 調理師, 建設作業員, 配管工
4-5 (Moderate): Mix of physical and knowledge work. Examples: 営業職, 小売店員, 看護師
6-7 (High): Primarily knowledge/digital work with human interaction barriers. Examples: 教師, 医師, 弁護士
8-9 (Very High): Digital work where AI excels. Examples: プログラマー, データアナリスト, 翻訳者
10 (Maximum): Almost entirely digital/cognitive work AI can fully automate. Examples: データ入力, 単純な文書作成

Key principle: Work done entirely on a computer (writing, coding, analyzing, communicating digitally) scores 7+.
Physical presence, real-time human judgment, and hands-on manipulation are natural barriers.

Important: A high score does NOT mean the job disappears. It means AI will significantly reshape how the work is done.
Japan-specific context: Consider Japan's labor shortage, aging society, and cultural preference for human service in your assessment.

Respond in this exact JSON format (no markdown fences):
{"exposure": <integer 0-10>, "rationale": "<2-3 sentences in English explaining the score>"}"""

AI_EXPOSURE_USER = """Occupation: {title}
Category: {category}
Description: {description}

Score this occupation's AI exposure (0-10)."""


OUTLOOK_SYSTEM = """You are a labor market analyst specializing in Japan's employment trends.

Score each occupation's employment outlook from -5 to +5:

-5 (Rapid decline): Occupation losing 20%+ of workers over next decade. Structural decline.
-3 (Declining): Losing 10-20% of workers. Clear downward trend.
-1 (Slight decline): Losing 0-10% of workers. Mild headwinds.
 0 (Stable): Roughly flat employment. Supply and demand in balance.
+1 (Slight growth): Growing 0-5%. Modest positive outlook.
+3 (Growing): Growing 5-15%. Strong demand.
+5 (Rapid growth): Growing 15%+ over next decade. Critical shortage.

Consider these Japan-specific factors:
- Aging society creating strong demand for healthcare, nursing, eldercare (大きな需要増)
- Declining birthrate reducing demand for education, childcare
- Manufacturing automation reducing factory workers
- Digital transformation creating IT/tech demand
- Labor shortages in construction, trucking, nursing
- Population decline reducing retail, food service demand
- Government infrastructure investment supporting construction
- Tourism growth creating hospitality demand
- Current 有効求人倍率 (job opening ratio) as a signal

Respond in this exact JSON format (no markdown fences):
{"outlook": <integer -5 to 5>, "outlook_desc": "<8 words or less describing the trend in Japanese>"}"""

OUTLOOK_USER = """Occupation: {title}
Category: {category}
Description: {description}
Current average annual income: {pay}万円
Approximate workers: {jobs}人

Score the 10-year employment outlook (-5 to +5) for this occupation in Japan."""


# ── API call ─────────────────────────────────────────────────────────────────

def call_llm(system_prompt, user_prompt, model):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        print("  Get a key at: https://openrouter.ai/keys")
        sys.exit(1)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/aleclee/ai2job",
            "X-Title": "Japan AI Job Market Visualizer",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_json(text):
    """Strip markdown fences and parse JSON, handling +N numeric values."""
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = text.rstrip("`").strip()
    # Fix +N JSON values (e.g. "+3" → 3) which are invalid JSON
    text = re.sub(r':\s*\+(\d+)', r': \1', text)
    # Find first complete JSON object
    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return json.loads(text)


def score_occupation(occ, model):
    """Score a single occupation for both AI exposure and employment outlook."""
    title = occ["title"]
    category = occ["category"]
    desc = occ.get("description", "")[:500]
    pay = occ.get("pay_10k") or "不明"
    jobs = f"{occ['jobs']:,}" if occ.get("jobs") else "不明"

    # Score AI exposure
    exposure_resp = call_llm(
        AI_EXPOSURE_SYSTEM,
        AI_EXPOSURE_USER.format(title=title, category=category, description=desc),
        model,
    )
    exposure_text = exposure_resp["choices"][0]["message"]["content"]
    exposure_data = extract_json(exposure_text)

    time.sleep(0.2)

    # Score employment outlook
    outlook_resp = call_llm(
        OUTLOOK_SYSTEM,
        OUTLOOK_USER.format(title=title, category=category, description=desc, pay=pay, jobs=jobs),
        model,
    )
    outlook_text = outlook_resp["choices"][0]["message"]["content"]
    outlook_data = extract_json(outlook_text)

    return {
        "occ_id": occ["occ_id"],
        "title": title,
        "exposure": int(exposure_data["exposure"]),
        "rationale": exposure_data["rationale"],
        "outlook": int(outlook_data["outlook"]),
        "outlook_desc": outlook_data["outlook_desc"],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Score Japanese occupations with LLM")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model ID")
    parser.add_argument("--start", type=int, default=0, help="Start index (0-based)")
    parser.add_argument("--end", type=int, default=None, help="End index (exclusive)")
    parser.add_argument("--force", action="store_true", help="Re-score even if cached")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between occupations (seconds)")
    args = parser.parse_args()

    # Load occupations
    with open("occupations_jp.json", encoding="utf-8") as f:
        occupations = json.load(f)

    # Load existing scores (for resuming)
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, encoding="utf-8") as f:
            scores_list = json.load(f)
    else:
        scores_list = []
    scores_by_id = {s["occ_id"]: s for s in scores_list}

    # Determine which occupations to score
    subset = occupations[args.start : args.end]
    to_score = [o for o in subset if args.force or o["occ_id"] not in scores_by_id]

    print(f"Model: {args.model}")
    print(f"Total occupations: {len(occupations)}")
    print(f"Subset: {len(subset)} (index {args.start}–{args.end or len(occupations)})")
    print(f"Already scored: {len(scores_by_id)}")
    print(f"To score: {len(to_score)}")
    print()

    if not to_score:
        print("Nothing to score. Use --force to re-score.")
        return

    errors = 0
    for i, occ in enumerate(to_score):
        print(f"[{i+1}/{len(to_score)}] {occ['title']}...", end=" ", flush=True)
        try:
            result = score_occupation(occ, args.model)
            scores_by_id[occ["occ_id"]] = result
            # Save incrementally after each occupation
            with open(SCORES_FILE, "w", encoding="utf-8") as f:
                json.dump(list(scores_by_id.values()), f, ensure_ascii=False, indent=2)
            print(f"exposure={result['exposure']}/10  outlook={result['outlook']:+d}/5")
        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1
            if errors > 30:
                print("Too many errors, stopping.")
                break

        if i < len(to_score) - 1:
            time.sleep(args.delay)

    # Print summary
    all_scores = list(scores_by_id.values())
    if all_scores:
        exposures = [s["exposure"] for s in all_scores if s.get("exposure") is not None]
        outlooks = [s["outlook"] for s in all_scores if s.get("outlook") is not None]
        print(f"\n{'='*50}")
        print(f"Scored: {len(all_scores)} occupations  |  Errors: {errors}")
        if exposures:
            avg_exp = sum(exposures) / len(exposures)
            print(f"Avg AI exposure: {avg_exp:.1f}/10")
            buckets = {
                "Minimal (0-1)": sum(1 for x in exposures if x <= 1),
                "Low (2-3)":     sum(1 for x in exposures if 2 <= x <= 3),
                "Moderate (4-5)":sum(1 for x in exposures if 4 <= x <= 5),
                "High (6-7)":    sum(1 for x in exposures if 6 <= x <= 7),
                "Very High (8+)":sum(1 for x in exposures if x >= 8),
            }
            for label, count in buckets.items():
                bar = "█" * count
                print(f"  {label:20s}: {count:3d} {bar[:40]}")
        if outlooks:
            avg_out = sum(outlooks) / len(outlooks)
            print(f"Avg outlook: {avg_out:+.1f}/5")
        print(f"\nSaved to {SCORES_FILE}")


if __name__ == "__main__":
    main()
