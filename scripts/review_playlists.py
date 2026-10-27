"""List the channel's playlists with the category/program each one maps to.

Use it to refine config/category_rules.json. Needs only YOUTUBE_API_KEY (in .env or the environment).

    python scripts/review_playlists.py            # table in the terminal
    python scripts/review_playlists.py --csv out.csv
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.categorize import classify_text, load_rules  # noqa: E402
from pipeline.config import load_settings  # noqa: E402
from pipeline.youtube_client import YouTubeClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", help="write the result to this CSV file")
    args = parser.parse_args()

    settings = load_settings()
    settings.require_youtube()
    rules, default_category = load_rules(settings.rules_path)
    yt = YouTubeClient(settings.youtube_api_key)
    channel = yt.get_channel(settings.channel_id, settings.channel_handle)
    playlists = yt.list_playlists(channel["id"])

    rows = []
    for p in playlists:
        title = p["snippet"]["title"]
        category, program = classify_text(title, rules, default_category)
        rows.append({
            "playlist_id": p["id"],
            "playlist_title": title,
            "items": (p.get("contentDetails") or {}).get("itemCount", ""),
            "category": category,
            "program": program or title,
        })
    rows.sort(key=lambda r: (r["category"], r["playlist_title"].lower()))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["playlist_id"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} playlists to {args.csv}")
    else:
        for r in rows:
            print(f"{r['category']:<15} {str(r['items']):>6}  {r['playlist_title']}  [{r['playlist_id']}]")
    unmapped = sum(1 for r in rows if r["category"] == default_category)
    print(f"\n{len(rows)} playlists for {channel['snippet']['title']}; {unmapped} fall into '{default_category}'. "
          f"API units used: {yt.units_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
