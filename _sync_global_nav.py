#!/usr/bin/env python3
"""Sync the global nav (header + mobile-nav) on every HTML page so they all
match the upgraded version defined in _build_pages.py HEADER.

The script:
  1. Pulls the canonical HEADER block from _build_pages.py
  2. For every *.html under the site (except build-output that's already current),
     replaces the existing <header class="site-header">…</header> + mobile-nav
     <div class="mobile-nav"…>…</div> block with the canonical HEADER.

Run after editing _build_pages.py's HEADER to propagate the change to non-built
pages (index.html, blog.html, resources/refinancing-during-divorce.html, and
all blog posts).
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent

# 1. Extract HEADER from _build_pages.py
build_pages = (ROOT / "_build_pages.py").read_text()
match = re.search(r"HEADER = '''(.+?)'''", build_pages, re.DOTALL)
if not match:
    raise SystemExit("Could not find HEADER in _build_pages.py")
HEADER = match.group(1)

# 2. Pattern that matches <header class="site-header">...</header>\s*<div class="mobile-nav"...>...</div>
#    (greedy enough to capture the whole panel, conservative enough to stop before <main>)
PATTERN = re.compile(
    r'<header class="site-header">.*?</header>\s*<div class="mobile-nav"[^>]*>.*?</div>\s*</div>\s*</div>',
    re.DOTALL,
)

# Simpler: match through to the line before <main id="main">
MAIN_BOUNDARY = re.compile(
    r'<header class="site-header">.*?(?=\s*(?:<!--[^>]*-->\s*)?<main\s+id="main")',
    re.DOTALL,
)


def needs_update(html: str) -> bool:
    """Old nav pages have <strong>Conventional</strong><span>Traditional` directly
    (no dd-icon span wrapping). The upgraded nav has it but with dd-icon nearby."""
    return ('class="dd-icon"' not in html) or html.count('class="dd-icon"') < 5


def update_file(path: Path) -> bool:
    html = path.read_text()
    if not needs_update(html):
        return False
    new_html, n = MAIN_BOUNDARY.subn(HEADER, html, count=1)
    if n == 0:
        print(f"  ! could not match nav boundary in {path.relative_to(ROOT)}")
        return False
    path.write_text(new_html)
    return True


targets = []
# Top-level pages
targets.extend(ROOT.glob("*.html"))
# Resource sub-pages
targets.extend(ROOT.glob("resources/*.html"))
# Blog posts
targets.extend(ROOT.glob("blog/*.html"))

updated = 0
checked = 0
for path in sorted(targets):
    if path.name in ("og-template.html",):
        continue
    checked += 1
    if update_file(path):
        updated += 1
        print(f"  ✓ updated {path.relative_to(ROOT)}")

print(f"\nDone. Updated {updated} of {checked} pages.")
