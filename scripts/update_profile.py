#!/usr/bin/env python3
"""Regenerate the auto-updating sections of the profile README.

Reads live data from the public GitHub API and rewrites only the content
between the START_SECTION / END_SECTION markers in README.md. Everything
outside those markers is left untouched. Stdlib only, no dependencies.

Sections owned by this script:
  - counters    (repo/star/fork/follower totals + last-updated stamp)
  - tech-stack  (language badges from live byte totals, forks excluded)
  - top-repos   (top repos by stars, tiebreak: most recently pushed)
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone

USER = "AdityaAgrawal08"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(ROOT, "README.md")

TOP_LANGUAGES = 8
TOP_REPOS = 6
MAX_DESC = 96

# language -> (badge color, simple-icons logo slug or None, logo color).
# Logo slugs were verified against cdn.simpleicons.org; anything missing
# a slug renders as a plain badge with no icon.
BADGES = {
    "C": ("A8B9CC", "c", "black"),
    "Go": ("00ADD8", "go", "white"),
    "TypeScript": ("3178C6", "typescript", "white"),
    "Python": ("3776AB", "python", "white"),
    "Lua": ("2C2D72", "lua", "white"),
    "JavaScript": ("F7DF1E", "javascript", "black"),
    "Shell": ("89e051", "gnubash", "black"),
    "CSS": ("663399", None, "white"),
    "HTML": ("e34c26", None, "white"),
    "Dockerfile": ("2496ED", "docker", "white"),
    "Makefile": ("427819", None, "white"),
    "PowerShell": ("012456", None, "white"),
    "Jupyter Notebook": ("DA5B0B", None, "white"),
}
FALLBACK_BADGE = ("555555", None, "white")


def api_get(url):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme-updater",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_repos():
    repos, page = [], 1
    while True:
        batch = api_get(
            f"https://api.github.com/users/{USER}/repos"
            f"?per_page=100&page={page}&type=owner&sort=pushed"
        )
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def shields_escape(label):
    # shields.io static-badge convention: '-' -> '--', '_' -> '__',
    # ' ' -> '_', '#' must be percent-encoded.
    return (
        label.replace("-", "--")
        .replace("_", "__")
        .replace(" ", "_")
        .replace("#", "%23")
    )


def badge(language):
    color, logo, logo_color = BADGES.get(language, FALLBACK_BADGE)
    url = (
        f"https://img.shields.io/badge/"
        f"{shields_escape(language)}-{color}?style=for-the-badge"
    )
    if logo:
        url += f"&logo={logo}&logoColor={logo_color}"
    return f"![{language}]({url})"


def build_counters(user, stars, forks):
    return (
        "<p align=\"center\">\n"
        f"  \U0001f4e6 <b>{user['public_repos']}</b> public repos"
        f" &nbsp;\u00b7&nbsp; \u2b50 <b>{stars}</b> stars"
        f" &nbsp;\u00b7&nbsp; \U0001f374 <b>{forks}</b> forks"
        f" &nbsp;\u00b7&nbsp; \U0001f465 <b>{user['followers']}</b> followers\n"
        "</p>\n"
        "\n"
        f"<sub>Last updated: {datetime.now(timezone.utc):%Y-%m-%d} UTC"
        " \u00b7 refreshes every Monday</sub>"
    )


def build_tech_stack(lang_bytes):
    top = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[
        :TOP_LANGUAGES
    ]
    return "\n".join(badge(lang) for lang, _ in top)


def build_top_repos(repos):
    # Stars descending, tiebreak: most recently pushed first.
    # Two stable sorts because the keys need opposite directions.
    ranked = sorted(repos, key=lambda r: r.get("pushed_at", ""), reverse=True)
    ranked = sorted(
        ranked, key=lambda r: r.get("stargazers_count", 0), reverse=True
    )[:TOP_REPOS]
    lines = [
        "| Repository | About | Language | \u2b50 Stars | Updated |",
        "|---|---|---|---|---|",
    ]
    for r in ranked:
        desc = (r.get("description") or "\u2014").replace("|", "\\|")
        if len(desc) > MAX_DESC:
            desc = desc[: MAX_DESC - 1] + "\u2026"
        pushed = (r.get("pushed_at") or "")[:10] or "\u2014"
        lines.append(
            f"| [{r['name']}]({r['html_url']}) | {desc}"
            f" | {r.get('language') or '\u2014'}"
            f" | {r.get('stargazers_count', 0)} | {pushed} |"
        )
    return "\n".join(lines)


def replace_section(text, name, new_inner):
    pattern = re.compile(
        r"(<!--START_SECTION:" + name + r"-->)(.*?)(<!--END_SECTION:" + name + r"-->)",
        re.DOTALL,
    )

    def _repl(match):
        return match.group(1) + "\n" + new_inner.strip("\n") + "\n" + match.group(3)

    new_text, count = pattern.subn(_repl, text)
    if count != 1:
        raise SystemExit(f"marker pair for '{name}' found {count} times, expected 1")
    return new_text


def main():
    user = api_get(f"https://api.github.com/users/{USER}")
    repos = fetch_repos()
    # Profile repo itself (USER/USER) never ranks: it holds this README.
    active = [
        r
        for r in repos
        if not r.get("fork")
        and not r.get("archived")
        and r.get("name", "").lower() != USER.lower()
    ]

    stars = sum(r.get("stargazers_count", 0) for r in active)
    forks = sum(r.get("forks_count", 0) for r in active)

    lang_bytes = {}
    for r in active:
        langs = api_get(r["languages_url"])
        if isinstance(langs, dict):
            for lang, nbytes in langs.items():
                lang_bytes[lang] = lang_bytes.get(lang, 0) + nbytes

    with open(README_PATH, encoding="utf-8") as f:
        text = f.read()

    text = replace_section(text, "counters", build_counters(user, stars, forks))
    text = replace_section(text, "tech-stack", build_tech_stack(lang_bytes))
    text = replace_section(text, "top-repos", build_top_repos(active))

    with open(README_PATH, encoding="utf-8") as f:
        old = f.read()
    if old != text:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print("README.md updated")
    else:
        print("README.md already up to date")


if __name__ == "__main__":
    main()
