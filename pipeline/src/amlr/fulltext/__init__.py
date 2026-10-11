"""Three-tier full-text acquisition.

Tier 1 — publisher TDM APIs (Elsevier, Wiley, Springer, PLOS).
Tier 2 — Unpaywall OA fallback (reuses experteye `acquisition/unpaywall.py`).
Tier 3 — Claude in Chrome under the FAU VPN (per-batch user approval).

The dispatcher in `fulltext.dispatch` decides per DOI which tier applies,
based on publisher prefix and OA status.
"""
