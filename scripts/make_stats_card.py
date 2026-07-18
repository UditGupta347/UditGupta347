"""
Self-hosted replacement for the github-readme-stats.vercel.app cards.

That public service is a known, frequently-down free instance (rate limits /
deployment pauses are common -- see anuraghazra/github-readme-stats issues).
Rather than depend on it, this script pulls your public GitHub data directly
from the REST API and renders two SVG cards locally, in the same dark
neofetch style as info-card.svg:

  stats-card.svg  -- public repos, followers, total stars, contributions
  langs-card.svg  -- top languages across your public repos, by bytes

Run with GH_PROFILE_USER set (defaults to uditgupta347). In CI, GITHUB_TOKEN
is picked up automatically for a much higher rate limit; locally it falls
back to unauthenticated requests (60/hr, fine for occasional runs).
"""
import html
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
USER = os.environ.get("GH_PROFILE_USER", "uditgupta347")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
STATIC = bool(os.environ.get("STATIC"))

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
MUTED = "#7d8590"
INK = "#c9d1d9"
SECTION = "#58a6ff"
GREEN = "#3fb950"
ACCENT = "#22d3ee"

LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Python": "#3572A5",
    "C++": "#f34b7d", "C": "#555555", "HTML": "#e34c26", "CSS": "#563d7c",
    "Java": "#b07219", "Flask": "#000000", "Jupyter Notebook": "#DA5B0B",
    "Shell": "#89e051", "EJS": "#a91e50", "PHP": "#4F5D95", "Go": "#00ADD8",
}
DEFAULT_LANG_COLOR = "#8b949e"


def esc(s):
    return html.escape(str(s))


def api_get(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-readme")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def fetch_github_data():
    user = api_get(f"/users/{USER}")
    repos = []
    page = 1
    while True:
        batch = api_get(f"/users/{USER}/repos?per_page=100&page={page}&type=owner")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    lang_bytes = {}
    for r in repos:
        if r.get("fork"):
            continue
        try:
            langs = api_get(f"/repos/{USER}/{r['name']}/languages")
        except Exception:
            continue
        for lang, n in langs.items():
            lang_bytes[lang] = lang_bytes.get(lang, 0) + n

    return {
        "public_repos": user.get("public_repos", len(repos)),
        "followers": user.get("followers", 0),
        "total_stars": total_stars,
        "lang_bytes": lang_bytes,
    }


def load_contributions():
    path = os.path.join(HERE, "..", "data", "contributions.json")
    try:
        with open(path) as f:
            return json.load(f).get("total", 0)
    except Exception:
        return None


def card_shell(w, h, title):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        '<defs><linearGradient id="cbg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/></linearGradient></defs>',
        f'<rect width="{w}" height="{h}" rx="12" fill="url(#cbg)"/>',
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="12" fill="none" stroke="{FRAME}"/>',
        f'<text x="20" y="30" fill="{SECTION}" font-size="14" font-weight="700">{esc(title)}</text>',
        f'<line x1="20" y1="40" x2="{w-20}" y2="40" stroke="{FRAME}" stroke-opacity="0.8"/>',
    ]


def rise(inner, i):
    if STATIC:
        return f"<g>{inner}</g>"
    delay = 0.15 + i * 0.08
    return (f'<g opacity="0" transform="translate(0,5)">{inner}'
            f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" dur="0.4s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" '
            f'begin="{delay:.2f}s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/></g>')


def render_stats_card(data, contributions):
    W, H = 400, 165
    parts = card_shell(W, H, f"{USER}'s GitHub Stats")
    rows = [
        ("Public Repos:", str(data["public_repos"])),
        ("Followers:", str(data["followers"])),
        ("Total Stars:", str(data["total_stars"])),
    ]
    if contributions is not None:
        rows.append(("Contributions (last yr):", str(contributions)))
    y = 66
    for i, (k, v) in enumerate(rows):
        inner = (f'<text x="20" y="{y}" fill="{MUTED}" font-size="12.5">{esc(k)}</text>'
                 f'<text x="{W-20}" y="{y}" fill="{GREEN}" font-size="12.5" font-weight="700" '
                 f'text-anchor="end">{esc(v)}</text>')
        parts.append(rise(inner, i))
        y += 24
    parts.append("</svg>")
    return "".join(parts)


def render_langs_card(lang_bytes):
    W, H = 400, 165
    parts = card_shell(W, H, "Most Used Languages")

    total = sum(lang_bytes.values()) or 1
    top = sorted(lang_bytes.items(), key=lambda kv: -kv[1])[:6]
    top = [(l, n, n / total * 100) for l, n in top]

    bar_x, bar_y, bar_w, bar_h = 20, 58, W - 40, 10
    x = bar_x
    for i, (lang, n, pct) in enumerate(top):
        seg_w = bar_w * (n / total)
        color = LANG_COLORS.get(lang, DEFAULT_LANG_COLOR)
        parts.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{seg_w:.1f}" height="{bar_h}" fill="{color}"/>')
        x += seg_w
    parts.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="3" '
                 f'fill="none" stroke="{FRAME}"/>')

    ly = bar_y + 30
    col_w = (W - 40) / 2
    for i, (lang, n, pct) in enumerate(top):
        col, row = i % 2, i // 2
        lx = 20 + col * col_w
        cy = ly + row * 22
        color = LANG_COLORS.get(lang, DEFAULT_LANG_COLOR)
        inner = (f'<circle cx="{lx+5}" cy="{cy-4}" r="4" fill="{color}"/>'
                 f'<text x="{lx+15}" y="{cy}" fill="{INK}" font-size="11.5">{esc(lang)} {pct:.1f}%</text>')
        parts.append(rise(inner, i))
    parts.append("</svg>")
    return "".join(parts)


if __name__ == "__main__":
    data = fetch_github_data()
    contributions = load_contributions()

    stats_svg = render_stats_card(data, contributions)
    langs_svg = render_langs_card(data["lang_bytes"])

    stats_path = os.path.join(HERE, "..", "stats-card.svg")
    langs_path = os.path.join(HERE, "..", "langs-card.svg")
    with open(stats_path, "w") as f:
        f.write(stats_svg)
    with open(langs_path, "w") as f:
        f.write(langs_svg)

    print("wrote", stats_path, len(stats_svg), "bytes")
    print("wrote", langs_path, len(langs_svg), "bytes")
