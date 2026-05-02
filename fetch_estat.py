"""
e-Stat API data fetcher for Japanese job market visualizer.
Fetches: 賃金構造基本統計調査（職種別）and 労働力調査（職業別就業者数）

Usage:
    export ESTAT_API_KEY=your_key_here
    python fetch_estat.py --search     # discover available datasets
    python fetch_estat.py --wages      # fetch wage data by occupation
    python fetch_estat.py --employment # fetch employment data by occupation
"""

import json
import os
import sys
import time
import argparse
import urllib.request
import urllib.parse

BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json"


def get(endpoint, params):
    api_key = os.environ.get("ESTAT_API_KEY")
    if not api_key:
        print("ERROR: Set ESTAT_API_KEY environment variable")
        print("  Register at: https://www.e-stat.go.jp/mypage/user/preregister")
        sys.exit(1)
    params["appId"] = api_key
    url = f"{BASE_URL}/{endpoint}?" + urllib.parse.urlencode(params, encoding="utf-8")
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))


def search_datasets(keyword):
    """Search for datasets by keyword."""
    print(f"\n=== Searching: {keyword} ===")
    data = get("getStatsList", {"searchWord": keyword, "searchKind": 2, "limit": 20, "lang": "J"})
    result = data.get("GET_STATS_LIST", {}).get("DATALIST_INF", {})
    tables = result.get("TABLE_INF", [])
    if isinstance(tables, dict):
        tables = [tables]
    for t in tables:
        print(f"  ID: {t.get('@id')}  | {t.get('STAT_NAME', {}).get('$', '')} | {t.get('TITLE', {}).get('$', '')}")
    return tables


def fetch_table(stats_data_id, label=""):
    """Fetch a specific stats table by ID."""
    print(f"\n=== Fetching table: {stats_data_id} ({label}) ===")
    data = get("getStatsData", {
        "statsDataId": stats_data_id,
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
        "limit": 10000,
        "lang": "J",
    })
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", action="store_true", help="Search for relevant datasets")
    parser.add_argument("--wages", action="store_true", help="Fetch wage data by occupation")
    parser.add_argument("--employment", action="store_true", help="Fetch employment data by occupation")
    parser.add_argument("--table-id", help="Fetch a specific table by ID")
    args = parser.parse_args()

    if args.search:
        # Search for key datasets
        search_datasets("賃金構造基本統計調査 職種")
        time.sleep(0.5)
        search_datasets("労働力調査 職業")
        time.sleep(0.5)
        search_datasets("国勢調査 職業別就業者")

    elif args.wages:
        # 賃金構造基本統計調査 - 職種別賃金 (令和6年 / 2024)
        # Known table IDs for occupation-level wage data:
        WAGE_TABLE_IDS = [
            ("0003534960", "職種別賃金 令和6年"),  # update after --search
        ]
        for tid, label in WAGE_TABLE_IDS:
            result = fetch_table(tid, label)
            with open(f"estat_wages_{tid}.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"  Saved to estat_wages_{tid}.json")

    elif args.employment:
        # 労働力調査 - 職業別就業者数
        EMPLOYMENT_TABLE_IDS = [
            ("0003307266", "労働力調査 職業別就業者数"),  # update after --search
        ]
        for tid, label in EMPLOYMENT_TABLE_IDS:
            result = fetch_table(tid, label)
            with open(f"estat_employment_{tid}.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"  Saved to estat_employment_{tid}.json")

    elif args.table_id:
        result = fetch_table(args.table_id, "custom")
        with open(f"estat_table_{args.table_id}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  Saved to estat_table_{args.table_id}.json")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
