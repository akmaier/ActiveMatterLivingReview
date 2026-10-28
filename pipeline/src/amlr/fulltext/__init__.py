"""Three-tier full-text acquisition.

Tier 1 — publisher TDM APIs (Elsevier, Wiley, Springer, PLOS).
Tier 2 — Unpaywall OA fallback.
Tier 3 — a visible Chrome driven by Playwright over institutional access (`fulltext-browser`),
         then the author's own browser (`fulltext-list`, `fulltext-import`); see pipeline/BROWSER.md.

The dispatcher in `fulltext.dispatch` decides per DOI which tier applies,
based on publisher prefix and OA status.
"""
