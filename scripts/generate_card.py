#!/usr/bin/env python3
"""Generate a neofetch-style ASCII profile card SVG from a GitHub avatar.

Pulls the avatar, converts it to ASCII art with Pillow, fetches public stats
from the GitHub REST API, and renders dark_mode.svg + light_mode.svg into the
output/ directory. Runs standalone (no external card service).
"""

import datetime
import html
import json
import os
import urllib.request
from io import BytesIO

from PIL import Image, ImageOps

HANDLE = os.environ.get("GH_HANDLE", "gabrieljdsena")
COLS = int(os.environ.get("ASCII_COLS", "52"))
ROLE = os.environ.get("GH_ROLE", "Developer")

# Dense -> sparse. Bright pixels pick sparse glyphs, dark pixels dense glyphs.
RAMP = "@%#+*=-:. "

PAD = 16
FONT_SIZE = 16
ROW_HEIGHT = 20
CHAR_WIDTH = 9.9
COLUMN_GAP = 24
Y_START = 30

THEMES = {
    "dark": {
        "bg": "#161b22", "text": "#c9d1d9", "key": "#ffa657",
        "value": "#a5d6ff", "dots": "#616e7f",
    },
    "light": {
        "bg": "#f6f8fa", "text": "#24292f", "key": "#953800",
        "value": "#0a3069", "dots": "#9ba3ae",
    },
}

UTF8 = "utf-8"


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ascii-card-bot",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def get_stats():
    user = json.loads(fetch(f"https://api.github.com/users/{HANDLE}").decode(UTF8))
    repos = json.loads(fetch(f"https://api.github.com/users/{HANDLE}/repos?per_page=100&sort=updated").decode(UTF8))
    stars = sum(r.get("stargazers_count") or 0 for r in repos)
    lang_counter = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counter[lang] = lang_counter.get(lang, 0) + 1
    top = ", ".join(sorted(lang_counter, key=lang_counter.get, reverse=True)[:4]) or "-"
    return user, stars, top


def avatar_to_ascii():
    data = fetch(f"https://github.com/{HANDLE}.png?size=600")
    img = Image.open(BytesIO(data)).convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    rows = max(1, round(COLS * CHAR_WIDTH / ROW_HEIGHT))
    img = img.resize((COLS, rows), Image.Resampling.LANCZOS)
    px = img.load()
    lines = []
    for y in range(rows):
        line = ""
        for x in range(COLS):
            lum = px[x, y]
            idx = (255 - lum) * (len(RAMP) - 1) // 255
            line += RAMP[idx]
        lines.append(line.rstrip())
    return lines


def uptime_string(created_at):
    created = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    months = max(0, (now.year - created.year) * 12 + (now.month - created.month))
    years, rem = divmod(months, 12)
    if years and rem:
        return f"{years} years, {rem} months"
    if years:
        return f"{years} years"
    return f"{rem} months"


def esc(s):
    return html.escape(s or "", quote=False)


def build_svg(theme_name, ascii_lines, right_lines):
    t = THEMES[theme_name]
    left_w = COLS * CHAR_WIDTH
    right_x = PAD + left_w + COLUMN_GAP

    max_key = max((len(item[1]) for item in right_lines if item[0] == "kv"), default=0)
    value_col = max_key + 3

    rendered = []
    right_width = 0
    for item in right_lines:
        kind = item[0]
        if kind == "blank":
            rendered.append(("", 0))
        elif kind == "header":
            text = item[1]
            rule = "\u2500" * (value_col + 12)
            widths = (len(text) + value_col + 12) * CHAR_WIDTH
            rendered.append((f'{esc(text)} <tspan class="dots">{rule}</tspan>', widths))
        elif kind == "section":
            text = item[1]
            rule = "\u2500" * (value_col + 6)
            widths = (len(text) + 2 + value_col + 6) * CHAR_WIDTH
            rendered.append((f'- {esc(text)} <tspan class="dots">{rule}</tspan>', widths))
        else:
            key, value = item[1], item[2]
            dots = value_col - len(key)
            markup = (
                f'<tspan class="dots">. </tspan>'
                f'<tspan class="key">{esc(key)}</tspan>'
                f'<tspan class="dots">{"." * dots}</tspan> '
                f'<tspan class="value">{esc(value)}</tspan>'
            )
            widths = (2 + value_col + 1 + len(value)) * CHAR_WIDTH
            rendered.append((markup, widths))
        right_width = max(right_width, rendered[-1][1])

    n_rows = max(len(ascii_lines), len(rendered))
    height = PAD * 2 + n_rows * ROW_HEIGHT
    width = max(round(right_x + right_width + PAD), round(left_w + PAD * 2))

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px"',
        f' font-family="\'JetBrains Mono\', \'Cascadia Code\', Consolas, monospace" font-size="{FONT_SIZE}px">',
        "<style>",
        f'.key {{fill: {t["key"]};}}',
        f'.value {{fill: {t["value"]};}}',
        f'.dots {{fill: {t["dots"]};}}',
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="{width}px" height="{height}px" fill="{t["bg"]}" rx="15"/>',
        f'<text fill="{t["text"]}" xml:space="preserve">',
    ]

    for i in range(n_rows):
        y = Y_START + i * ROW_HEIGHT
        left = ascii_lines[i] if i < len(ascii_lines) else ""
        right = rendered[i][0] if i < len(rendered) and rendered[i][0] else ""
        if left:
            svg.append(f'<tspan x="{PAD}" y="{y}">{esc(left)}</tspan>')
        if right:
            svg.append(f'<tspan x="{right_x}" y="{y}">{right}</tspan>')

    svg.append("</text>")
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def main():
    user, stars, top = get_stats()
    ascii_lines = avatar_to_ascii()

    uptime = uptime_string(user["created_at"])
    right_lines = [
        ("header", HANDLE),
        ("kv", "Role", ROLE),
        ("kv", "Uptime", f"{uptime} on GitHub"),
        ("blank",),
        ("section", "GitHub Stats"),
        ("kv", "Repos", str(user["public_repos"])),
        ("kv", "Stars", str(stars)),
        ("kv", "Followers", str(user["followers"])),
        ("kv", "Top Languages", top),
    ]

    os.makedirs("output", exist_ok=True)
    for theme in ("dark", "light"):
        svg_path = os.path.join("output", f"{theme}_mode.svg")
        with open(svg_path, "w", encoding=UTF8) as f:
            f.write(build_svg(theme, ascii_lines, right_lines))
        print(f"wrote {svg_path}")


if __name__ == "__main__":
    main()