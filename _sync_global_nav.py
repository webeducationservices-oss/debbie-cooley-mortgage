#!/usr/bin/env python3
"""Sync the global nav (HEADER) AND FOOTER on every HTML page so they all
match the canonical versions defined in _build_pages.py.

The script:
  1. Pulls the canonical HEADER and FOOTER blocks from _build_pages.py.
  2. For every *.html in the site, replaces:
       - <header class="site-header">…</header> + mobile-nav block →  HEADER
       - <footer class="site-footer">…</footer></body></html>  →  FOOTER

Run after editing _build_pages.py's HEADER or FOOTER to propagate the change
to non-built pages (index.html, blog.html, blog/*.html, resources/*.html,
and any other hand-maintained pages).

Always idempotent — if a file already matches the canonical version, the
replacement is a no-op (re.subn count returns 0 in some branches but the
content stays identical).
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent

# 1. Extract HEADER + FOOTER from _build_pages.py
build_pages = (ROOT / "_build_pages.py").read_text()

m_header = re.search(r"HEADER = '''(.+?)'''", build_pages, re.DOTALL)
if not m_header:
    raise SystemExit("Could not find HEADER in _build_pages.py")
HEADER = m_header.group(1)

m_footer = re.search(r"FOOTER = '''(.+?)'''", build_pages, re.DOTALL)
if not m_footer:
    raise SystemExit("Could not find FOOTER in _build_pages.py")
FOOTER = m_footer.group(1)

# Boundaries:
#   HEADER block: from <header class="site-header"> ... right before <main id="main">
#   FOOTER block: from <footer class="site-footer"> ... through </html>
HEADER_BOUNDARY = re.compile(
    r'<header class="site-header">.*?(?=\s*(?:<!--[^>]*-->\s*)?<main\s+id="main")',
    re.DOTALL,
)
FOOTER_BOUNDARY = re.compile(
    r'<footer class="site-footer">.*?</html>\s*$',
    re.DOTALL,
)


def update_file(path: Path) -> tuple[bool, list[str]]:
    """Returns (changed?, list of segments updated)."""
    html = path.read_text()
    original = html
    changes = []

    new_html, n_h = HEADER_BOUNDARY.subn(HEADER, html, count=1)
    if n_h:
        html = new_html
        if original != html:
            changes.append("header")

    new_html, n_f = FOOTER_BOUNDARY.subn(FOOTER, html, count=1)
    if n_f:
        if html != new_html:
            changes.append("footer")
        html = new_html

    if html != original:
        path.write_text(html)
        return True, changes
    return False, []


targets = []
targets.extend(ROOT.glob("*.html"))
targets.extend(ROOT.glob("resources/*.html"))
targets.extend(ROOT.glob("blog/*.html"))
targets.extend(ROOT.glob("tools/*.html"))

updated = 0
for path in sorted(targets):
    if path.name in ("og-template.html",):
        continue
    changed, segments = update_file(path)
    if changed:
        updated += 1
        print(f"  ✓ {path.relative_to(ROOT)} ({', '.join(segments)})")

print(f"\nDone. Updated {updated} pages.")
