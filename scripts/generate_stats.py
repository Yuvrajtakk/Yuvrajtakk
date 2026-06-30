"""
Generates stats.svg for the GitHub profile README.
Pulls real contribution / language data via the GitHub GraphQL API and
renders it as a single self-contained SVG in the same cursed-fire palette
as banner.svg. Runs inside GitHub Actions — see .github/workflows/update-stats.yml.

No external image services, no shared rate limits: this script's only
dependency is the GitHub API call made by the Action runner itself.
"""

import os
import sys
import datetime
import requests

GH_TOKEN = os.environ.get("GH_TOKEN")
GH_USERNAME = os.environ.get("GH_USERNAME", "Yuvrajtakk")

API_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"bearer {GH_TOKEN}"}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
    followers { totalCount }
  }
}
"""


def fetch_data(login):
    resp = requests.post(
        API_URL,
        json={"query": QUERY, "variables": {"login": login}},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        print(payload["errors"], file=sys.stderr)
        sys.exit(1)
    return payload["data"]["user"]


def compute_streaks(weeks):
    days = []
    for week in weeks:
        for day in week["contributionDays"]:
            days.append((day["date"], day["contributionCount"]))
    days.sort(key=lambda d: d[0])

    today = datetime.date.today().isoformat()

    # current streak: walk backwards from the most recent day, skipping
    # "today" itself if it still has zero contributions (day isn't over yet)
    current = 0
    idx = len(days) - 1
    if idx >= 0 and days[idx][0] == today and days[idx][1] == 0:
        idx -= 1
    while idx >= 0 and days[idx][1] > 0:
        current += 1
        idx -= 1

    # longest streak: max run of consecutive non-zero days across the year
    longest = 0
    running = 0
    for _, count in days:
        if count > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    return current, longest


def compute_languages(repo_nodes, top_n=5):
    totals = {}
    colors = {}
    for repo in repo_nodes:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#ff8a3c"
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    grand_total = sum(totals.values()) or 1
    return [
        {"name": name, "pct": round(size / grand_total * 100, 1), "color": colors[name]}
        for name, size in ranked
    ]


def flame_scale(streak):
    # visual flame height responds to the real streak number
    # 0 streak -> embers barely alive, 30+ streak -> full blaze
    return max(0.35, min(1.0, 0.35 + streak / 30 * 0.65))


def render_svg(total_contribs, current_streak, longest_streak, languages, stars, repos):
    scale = flame_scale(current_streak)
    flame_h = round(70 * scale)
    flame_opacity = round(0.4 + 0.6 * scale, 2)

    lang_rows = ""
    y = 0
    for lang in languages:
        bar_w = round(lang["pct"] * 1.7, 1)
        lang_rows += f"""
        <g transform="translate(0,{y})">
          <text x="0" y="13" font-family="'Segoe UI', Helvetica, Arial, sans-serif"
            font-size="12.5" fill="#e8c8a8">{lang['name']}</text>
          <text x="300" y="13" text-anchor="end" font-family="'Segoe UI', Helvetica, Arial, sans-serif"
            font-size="12" fill="#9c5a3a">{lang['pct']}%</text>
          <rect x="0" y="19" width="300" height="6" rx="3" fill="#2a0f08"/>
          <rect x="0" y="19" width="{bar_w}" height="6" rx="3" fill="{lang['color']}"/>
        </g>"""
        y += 29

    svg = f"""<svg viewBox="0 0 760 230" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="bg" cx="80%" cy="30%" r="90%">
      <stop offset="0%" stop-color="#220a04"/>
      <stop offset="100%" stop-color="#050202"/>
    </radialGradient>
    <linearGradient id="flameGrad" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#ff3d12" stop-opacity="0.95"/>
      <stop offset="55%" stop-color="#ff8a1e" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#ffd27a" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="titleGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#ffd9a0"/>
      <stop offset="100%" stop-color="#ff4d1c"/>
    </linearGradient>
    <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <rect x="0" y="0" width="760" height="230" rx="14" fill="url(#bg)"/>
  <rect x="0.75" y="0.75" width="758.5" height="228.5" rx="14" fill="none" stroke="#3d0a05" stroke-width="1.5"/>

  <text x="28" y="38" font-family="'Segoe UI', Helvetica, Arial, sans-serif" font-size="18"
    font-weight="700" fill="url(#titleGrad)" filter="url(#glow)" letter-spacing="1">cursed_stats.exe</text>

  <!-- left column: numbers -->
  <g font-family="'Segoe UI', Helvetica, Arial, sans-serif">
    <text x="28" y="80" font-size="30" font-weight="700" fill="#ffd9a0">{total_contribs}</text>
    <text x="28" y="100" font-size="12" fill="#9c5a3a">contributions / yr</text>

    <text x="28" y="140" font-size="30" font-weight="700" fill="#ff8a3c">{current_streak}</text>
    <text x="28" y="160" font-size="12" fill="#9c5a3a">current streak (days)</text>

    <text x="28" y="200" font-size="30" font-weight="700" fill="#ffd9a0">{longest_streak}</text>
    <text x="28" y="220" font-size="12" fill="#9c5a3a">longest streak (days)</text>
  </g>

  <!-- center: the responsive flame, height driven by current_streak -->
  <g transform="translate(255,205)" filter="url(#glow)">
    <path d="M -22,0 C -26,-{flame_h*0.55:.0f} 4,-{flame_h*0.45:.0f} -6,-{flame_h} C 22,-{flame_h*0.5:.0f} 18,-{flame_h*0.18:.0f} 28,0 Z"
      fill="url(#flameGrad)" opacity="{flame_opacity}">
      <animate attributeName="d" dur="2.4s" repeatCount="indefinite"
        values="M -22,0 C -26,-{flame_h*0.55:.0f} 4,-{flame_h*0.45:.0f} -6,-{flame_h} C 22,-{flame_h*0.5:.0f} 18,-{flame_h*0.18:.0f} 28,0 Z;
                 M -20,0 C -28,-{flame_h*0.6:.0f} 6,-{flame_h*0.4:.0f} -4,-{flame_h*1.04:.0f} C 24,-{flame_h*0.46:.0f} 16,-{flame_h*0.2:.0f} 26,0 Z;
                 M -22,0 C -26,-{flame_h*0.55:.0f} 4,-{flame_h*0.45:.0f} -6,-{flame_h} C 22,-{flame_h*0.5:.0f} 18,-{flame_h*0.18:.0f} 28,0 Z"/>
    </path>
  </g>
  <text x="255" y="222" text-anchor="middle" font-family="'Courier New', monospace" font-size="10"
    fill="#9c5a3a">{repos} repos · {stars}&#9733;</text>

  <!-- right column: top languages -->
  <g transform="translate(420,55)">
    <text x="0" y="0" font-family="'Segoe UI', Helvetica, Arial, sans-serif" font-size="12.5"
      fill="#ff8a3c" letter-spacing="1">TOP LANGUAGES</text>
    <g transform="translate(0,20)">{lang_rows}
    </g>
  </g>

  <text x="28" y="218" font-family="'Courier New', monospace" font-size="9.5"
    fill="#5c2f1a" opacity="0.8"></text>
</svg>
"""
    return svg


def main():
    if not GH_TOKEN:
        print("GH_TOKEN env var is required", file=sys.stderr)
        sys.exit(1)

    data = fetch_data(GH_USERNAME)
    calendar = data["contributionsCollection"]["contributionCalendar"]
    total_contribs = calendar["totalContributions"]
    current_streak, longest_streak = compute_streaks(calendar["weeks"])

    repos = data["repositories"]
    languages = compute_languages(repos["nodes"])
    stars = sum(r["stargazerCount"] for r in repos["nodes"])

    svg = render_svg(
        total_contribs=total_contribs,
        current_streak=current_streak,
        longest_streak=longest_streak,
        languages=languages,
        stars=stars,
        repos=repos["totalCount"],
    )

    with open("stats.svg", "w") as f:
        f.write(svg)

    print(f"stats.svg written — {total_contribs} contributions, "
          f"streak {current_streak}/{longest_streak}")


if __name__ == "__main__":
    main()
