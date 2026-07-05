import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SECTIONS = [
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
    ("docs", "Documentation"),
    ("ci", "CI"),
    ("refactor", "Refactoring"),
]
TYPES = {t for t, _ in SECTIONS}
COMMIT_RE = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<subject>.+)$")


def tags() -> list[str]:
    out = subprocess.run(
        ["git", "tag", "--sort=-creatordate"], capture_output=True, text=True, check=True
    ).stdout.split()
    return [t for t in out if re.match(r"^v?\d+\.\d+", t)]


def commits(rev_range: str) -> list[str]:
    out = subprocess.run(
        ["git", "log", rev_range, "--pretty=%s", "--no-merges"], capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line]


def group(subjects: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for subject in subjects:
        match = COMMIT_RE.match(subject)
        if not match or match["type"] not in TYPES:
            continue
        scope = f"**{match['scope']}**: " if match["scope"] else ""
        prefix = "**BREAKING** " if match["breaking"] else ""
        grouped[match["type"]].append(f"{prefix}{scope}{match['subject']}")
    return grouped


def render_release(title: str, rev_range: str) -> str:
    grouped = group(commits(rev_range))
    if not grouped:
        return ""
    lines = [f"## {title}", ""]
    for key, heading in SECTIONS:
        if grouped.get(key):
            lines.append(f"### {heading}")
            lines += [f"- {item}" for item in grouped[key]]
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    all_tags = tags()
    blocks = ["# Changelog", "", "Generated from conventional commits (`scripts/gen_changelog.py`).", ""]
    latest = all_tags[0] if all_tags else None
    unreleased = render_release("Unreleased", f"{latest}..HEAD" if latest else "HEAD")
    if unreleased:
        blocks.append(unreleased)
    for newer, older in zip(all_tags, all_tags[1:] + [None], strict=False):
        rev_range = f"{older}..{newer}" if older else newer
        block = render_release(newer, rev_range)
        if block:
            blocks.append(block)
    output = "\n".join(blocks).rstrip() + "\n"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("CHANGELOG.md")
    target.write_text(output)
    print(f"wrote {target} ({len(all_tags)} tagged releases)")


if __name__ == "__main__":
    main()
