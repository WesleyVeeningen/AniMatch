"""Download the deck the app uses: the 1,500 most popular anime on AniList.

Same query and filters as public/index.html, so offline results describe the catalogue
users actually swipe through. Stays under AniList's 30 requests per minute.
"""
import json
import time
from pathlib import Path

import requests

API = "https://graphql.anilist.co"
OUT = Path(__file__).parent / "data" / "catalog.json"
PAGES = 30
QUERY = """query($page:Int){Page(page:$page,perPage:50){pageInfo{hasNextPage}
  media(type:ANIME,sort:POPULARITY_DESC,isAdult:false){
    id idMal title{romaji english} genres tags{name rank isMediaSpoiler isAdult}
    averageScore popularity seasonYear format
    relations{edges{relationType(version:2) node{type format popularity}}}}}}"""


def is_sequel(m):
    """Port of isSequel() in public/index.html."""
    for e in m["relations"]["edges"]:
        n = e["node"]
        if e["relationType"] == "PREQUEL" and n["type"] == "ANIME" and (
            n["format"] in ("TV", "TV_SHORT") or (n["popularity"] or 0) > (m["popularity"] or 0)
        ):
            return True
    return False


def features(m):
    """Port of features() in public/index.html."""
    f = {f"g:{g}": 1 for g in m["genres"]}
    for t in m["tags"]:
        if not t["isMediaSpoiler"] and not t["isAdult"] and t["rank"] >= 55:
            f[f"t:{t['name']}"] = 0.7 * t["rank"] / 100
    return f


def main():
    items = []
    for page in range(1, PAGES + 1):
        while True:
            r = requests.post(API, json={"query": QUERY, "variables": {"page": page}}, timeout=30)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 30)) + 1)
                continue
            r.raise_for_status()
            break
        for m in r.json()["data"]["Page"]["media"]:
            items.append({
                "id": m["id"], "idMal": m["idMal"], "title": m["title"]["english"] or m["title"]["romaji"],
                "f": features(m), "averageScore": m["averageScore"], "popularity": m["popularity"],
                "year": m["seasonYear"], "sequel": is_sequel(m),
            })
        print(f"page {page}/{PAGES}: {len(items)} titles", flush=True)
        time.sleep(2.2)
    OUT.write_text(json.dumps(items, ensure_ascii=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
