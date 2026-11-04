"""Builds assets/contributions-dark.svg and assets/contributions-light.svg.

Donut charts of the GitHub contributions of GH_LOGIN: the all-time total
split by year, then each recent year split by type. The README shows the
file that matches the reader's theme.

Run every day by .github/workflows/contributions.yml, which commits the SVGs
only when a number has changed.

  GH_LOGIN      GitHub username (default: BerkmKuzu1)
  GITHUB_TOKEN  any token that can read public contribution data

Local run:  GITHUB_TOKEN=ghp_xxx python tools/build_contributions.py

The Actions token counts contributions to private repositories without
saying what they were, so they get a "Private" slice of their own. A personal
token can see into the private repositories it may read, and files those
contributions under their real type instead.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from math import pi
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets"

LOGIN = os.environ.get("GH_LOGIN") or "BerkmKuzu1"
TOKEN = os.environ.get("GITHUB_TOKEN")

# How many recent years get a donut of their own next to the total.
YEARS_SHOWN = 3

# GraphQL field and legend label of each contribution type.
TYPES = [
    ("totalCommitContributions", "Commits"),
    ("totalPullRequestContributions", "Pull requests"),
    ("totalPullRequestReviewContributions", "Code reviews"),
    ("totalIssueContributions", "Issues"),
    ("totalRepositoryContributions", "New repos"),
    ("restrictedContributionsCount", "Private"),
]

# GitHub's own greys and type colours; the years use the orange of
# berkkuzu.com, newest year brightest.
THEMES = {
    "dark": {
        "text": "#e6edf3", "muted": "#8b949e", "line": "#30363d", "track": "#21262d",
        "years": ["#f59410", "#a35f02", "#5c3a05"],
        "Commits": "#2f81f7", "Pull requests": "#a371f7", "Code reviews": "#db61a2",
        "Issues": "#3fb950", "New repos": "#d29922", "Private": "#6e7681",
        "Other": "#484f58",
    },
    "light": {
        "text": "#1f2328", "muted": "#59636e", "line": "#d1d9e0", "track": "#eff2f5",
        "years": ["#d97706", "#f2a93b", "#fbd38d"],
        "Commits": "#0969da", "Pull requests": "#8250df", "Code reviews": "#bf3989",
        "Issues": "#1a7f37", "New repos": "#9a6700", "Private": "#8c959f",
        "Other": "#d1d9e0",
    },
}

# Geometry, in SVG user units, relative to one panel.
PANEL_W = 280
CX, CY = PANEL_W // 2, 136
RADIUS = 64
STROKE = 20
LEGEND_Y = 236
ROW = 18

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',"
        "Helvetica,Arial,sans-serif")


def graphql(query, variables):
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN is not set")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-contribution-charts",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)

    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    if not body.get("data", {}).get("user"):
        raise SystemExit(f"No such user: {LOGIN}")
    return body["data"]["user"]


def fetch_years():
    """Every year with contributions, newest first, with totals per type."""
    user = graphql(
        "query($login: String!) { user(login: $login) {"
        " contributionsCollection { contributionYears } } }",
        {"login": LOGIN},
    )
    years = sorted(user["contributionsCollection"]["contributionYears"], reverse=True)
    if not years:
        return []

    # One collection may span a year at most, so ask for each year by alias.
    fields = " ".join(field for field, _ in TYPES)
    parts = [
        f'y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", '
        f'to: "{year}-12-31T23:59:59Z") '
        f"{{ contributionCalendar {{ totalContributions }} {fields} }}"
        for year in years
    ]
    user = graphql(
        f"query($login: String!) {{ user(login: $login) {{ {' '.join(parts)} }} }}",
        {"login": LOGIN},
    )

    result = []
    for year in years:
        data = user[f"y{year}"]
        total = data["contributionCalendar"]["totalContributions"]
        types = {label: data[field] for field, label in TYPES if data[field]}
        # The calendar also counts things no field itemises, such as
        # discussions; keep the slices summing to the calendar total.
        other = total - sum(types.values())
        if other > 0:
            types["Other"] = other
        result.append({"year": year, "total": total, "types": types})
    return result


def percent(part, whole):
    """Whole percent, escaped for the SVG it goes into."""
    share = 100 * part / whole
    if share < 1:
        return "&lt;1%"
    if share < 100 and int(share + 0.5) == 100:
        return "&gt;99%"
    return f"{int(share + 0.5)}%"


def panel(title, caption, total, slices, theme):
    """One donut with its title, centre total and legend.

    slices: (label, count, colour), drawn clockwise from twelve o'clock.
    """
    circumference = 2 * pi * RADIUS
    parts = [
        f'<text class="title" x="{CX}" y="30">{title}</text>',
        f'<text class="caption" x="{CX}" y="48">{caption}</text>',
        f'<circle cx="{CX}" cy="{CY}" r="{RADIUS}" fill="none" '
        f'stroke="{theme["track"]}" stroke-width="{STROKE}"/>',
        f'<g fill="none" stroke-width="{STROKE}" transform="rotate(-90 {CX} {CY})">',
    ]

    start = 0.0
    for label, count, colour in slices:
        length = circumference * count / total
        parts.append(
            f'<circle cx="{CX}" cy="{CY}" r="{RADIUS}" stroke="{colour}" '
            f'stroke-dasharray="{length:.2f} {circumference:.2f}" '
            f'stroke-dashoffset="{0 - start:.2f}">'
            f"<title>{label}: {count:,} ({percent(count, total)})</title></circle>"
        )
        start += length
    parts.append("</g>")

    parts.append(f'<text class="count" x="{CX}" y="{CY + 4}">{total:,}</text>')
    parts.append(f'<text class="unit" x="{CX}" y="{CY + 22}">contributions</text>')

    if not slices:
        parts.append(f'<text class="caption" x="{CX}" y="{LEGEND_Y}">None yet</text>')

    for row, (label, count, colour) in enumerate(slices):
        y = LEGEND_Y + row * ROW
        parts.append(f'<circle cx="44" cy="{y - 4}" r="5" fill="{colour}"/>')
        parts.append(f'<text class="label" x="56" y="{y}">{label}</text>')
        parts.append(
            f'<text class="value" x="236" y="{y}">'
            f"{count:,} &#183; {percent(count, total)}</text>"
        )

    return parts, len(slices)


def build_svg(years, theme_name):
    theme = THEMES[theme_name]
    this_year = datetime.now(timezone.utc).year
    shown = years[:YEARS_SHOWN]
    grand_total = sum(y["total"] for y in years)

    panels = []
    by_year = [
        (str(y["year"]), y["total"], theme["years"][min(i, len(theme["years"]) - 1)])
        for i, y in enumerate(years) if y["total"]
    ]
    first = years[-1]["year"] if years else this_year
    panels.append(panel("Total", f"by year, since {first}", grand_total, by_year, theme))

    for y in shown:
        slices = sorted(
            ((label, count) for label, count in y["types"].items() if label != "Other"),
            key=lambda item: -item[1],
        )
        if "Other" in y["types"]:
            slices.append(("Other", y["types"]["Other"]))
        caption = "by type, so far" if y["year"] == this_year else "by type"
        panels.append(panel(
            str(y["year"]), caption, y["total"],
            [(label, count, theme[label]) for label, count in slices], theme,
        ))

    width = PANEL_W * len(panels)
    rows = max(rows for _, rows in panels)
    height = LEGEND_Y + max(rows - 1, 0) * ROW + 22

    summary = (
        f"{grand_total:,} contributions since {first}: "
        + ", ".join(f'{y["total"]:,} in {y["year"]}' for y in years) + ". "
        + " ".join(
            f'{y["year"]} by type: '
            + ", ".join(f"{label} {count:,}" for label, count in y["types"].items())
            + "."
            for y in shown
        )
    )

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">',
        f'<title id="t">GitHub contributions of {LOGIN}</title>',
        f'<desc id="d">{summary}</desc>',
        "<style>"
        f"text{{font-family:{FONT};fill:{theme['muted']};font-size:12px}}"
        f".title{{fill:{theme['text']};font-size:15px;font-weight:600;text-anchor:middle}}"
        ".caption,.unit{font-size:11px;text-anchor:middle}"
        f".count{{fill:{theme['text']};font-size:26px;font-weight:600;text-anchor:middle}}"
        f".label{{fill:{theme['text']}}}"
        ".value{text-anchor:end;font-variant-numeric:tabular-nums}"
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" '
        f'fill="none" stroke="{theme["line"]}"/>',
    ]
    for i in range(1, len(panels)):
        out.append(
            f'<line x1="{i * PANEL_W}" y1="16" x2="{i * PANEL_W}" y2="{height - 16}" '
            f'stroke="{theme["line"]}"/>'
        )
    for i, (parts, _) in enumerate(panels):
        out.append(f'<g transform="translate({i * PANEL_W} 0)">')
        out.extend(parts)
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    years = fetch_years()
    OUT_DIR.mkdir(exist_ok=True)

    for theme in THEMES:
        path = OUT_DIR / f"contributions-{theme}.svg"
        path.write_text(build_svg(years, theme), encoding="utf-8", newline="\n")

    print(
        "Wrote assets/contributions-{dark,light}.svg: "
        + ", ".join(f'{y["year"]}: {y["total"]}' for y in years)
    )


if __name__ == "__main__":
    main()
