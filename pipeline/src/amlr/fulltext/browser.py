"""Tier 3: real-browser retrieval through FAU institutional access (VPN IP entitlement).

A visible Chrome (Playwright `channel="chrome"`, its own profile under ~/.amlr) loads the
publisher pages as a person would: no user-agent override and no stealth plugins. A publisher
that answers with a CAPTCHA or bot challenge is skipped for the rest of the run; nothing
attempts to get past it. Requests are spaced per host and capped per run so that the
institution's access is not flagged for systematic downloading.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..config import REPO_ROOT
from ..schema import PrismaPhase
from ..storage import read_jsonl
from .dispatch import LEDGER, PDF_DIR, apply, extract_text, is_pdf, pdf_pages, slug

PROFILE = Path.home() / ".amlr" / "browser_profile"
CHALLENGE = re.compile(r"captcha|are you a robot|verify you are human|just a moment\.\.\.|unusual traffic|"
                       r"access denied|request unsuccessful|cf-chl|bot detection", re.IGNORECASE)
SPACING_S = {"ieeexplore.ieee.org": 25.0}
DEFAULT_SPACING_S = 15.0
CAP_PER_HOST = 40
ROUTE = "browser"


class Challenged(RuntimeError):
    pass


class Browser:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self._pw = self._ctx = None
        self._last: dict[str, float] = {}

    def __enter__(self) -> "Browser":
        from playwright.sync_api import sync_playwright

        PROFILE.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=self.headless, accept_downloads=True)
        return self

    def __exit__(self, *exc) -> None:
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()

    def _space(self, host: str) -> None:
        wait = self._last.get(host, 0) + SPACING_S.get(host, DEFAULT_SPACING_S) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    @staticmethod
    def _challenged(page) -> bool:
        try:
            html, title = page.content(), page.title()
        except Exception:
            return False
        return bool(CHALLENGE.search(title or "")) or "challenge-platform" in html or "perfdrive.com" in page.url

    def open(self, url: str, wait_for_human_s: int = 0) -> tuple[str, str]:
        """Load a page; return (final URL, HTML).

        On a bot check: with `wait_for_human_s` > 0 the page is brought to the front and left open
        for the person at the screen to solve it; the run resumes once the publisher page loads.
        Otherwise, or if it is not solved in time, raises Challenged.
        """

        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)
            if self._challenged(page):
                if not wait_for_human_s:
                    raise Challenged(page.url)
                page.bring_to_front()
                print(f"[waiting for you] bot check at {page.url[:80]} — please solve it in the Chrome window "
                      f"(up to {wait_for_human_s // 60} min)", flush=True)
                deadline = time.monotonic() + wait_for_human_s
                while self._challenged(page) and time.monotonic() < deadline:
                    page.wait_for_timeout(3000)
                if self._challenged(page):
                    raise Challenged(page.url)
                page.wait_for_timeout(2000)
                print(f"[resumed] {page.url[:80]}", flush=True)
            return page.url, page.content()
        finally:
            page.close()

    def pdf(self, url: str, referer: str = "") -> bytes | None:
        """Fetch a PDF with the page's cookies; fall back to navigating to it."""

        headers = {"Accept": "application/pdf"} | ({"Referer": referer} if referer else {})
        try:
            resp = self._ctx.request.get(url, headers=headers, timeout=90_000)
            body = resp.body() if resp.ok else b""
            if is_pdf(body):
                return body
        except Exception:
            pass
        page = self._ctx.new_page()
        try:
            try:
                with page.expect_download(timeout=30_000) as dl:
                    try:
                        page.goto(url, timeout=60_000)
                    except Exception:
                        pass  # navigation is aborted when the response is a download
                data = Path(dl.value.path()).read_bytes()
                return data if is_pdf(data) else None
            except Exception:
                return None
        finally:
            page.close()


_META = re.compile(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)'
                   r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url', re.I)


def plan(record: dict) -> tuple[str, str] | None:
    """(publisher host, entry URL) for a record, or None if there is nothing to open."""

    doi = (record.get("doi") or "").lower()
    arnumber = (record.get("source_ids") or {}).get("ieee")
    if arnumber and str(arnumber).isdigit():
        return "ieeexplore.ieee.org", f"https://ieeexplore.ieee.org/document/{arnumber}"
    if doi:
        host = {"10.1109": "ieeexplore.ieee.org", "10.1126": "www.science.org", "10.1073": "www.pnas.org",
                "10.1088": "iopscience.iop.org", "10.1016": "www.sciencedirect.com"}.get(doi.split("/")[0], doi.split("/")[0])
        return host, f"https://doi.org/{doi}"
    return None


def pdf_url(host: str, record: dict, final_url: str, html: str) -> str | None:
    doi = (record.get("doi") or "").lower()
    if host == "ieeexplore.ieee.org":
        m = re.search(r"/document/(\d+)", final_url) or re.search(r"arnumber=(\d+)", final_url)
        return f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={m.group(1)}" if m else None
    if host == "www.science.org" and doi:
        return f"https://www.science.org/doi/pdf/{doi}?download=true"
    if host == "www.pnas.org" and doi:
        return f"https://www.pnas.org/doi/pdf/{doi}?download=true"
    if host == "iopscience.iop.org" and doi:
        return f"https://iopscience.iop.org/article/{doi}/pdf"
    m = _META.search(html)
    return (m.group(1) or m.group(2)) if m else None


def candidates(corpus: Path, publisher: str | None = None, exclude: str | None = None) -> list[dict]:
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    out = []
    for r in read_jsonl(corpus):
        a = latest.get(r["id"])
        if r.get("phase") != PrismaPhase.fulltext_sought.value or (a and a["status"] == "retrieved"):
            continue
        if a and ROUTE in a.get("tried", []):
            continue
        p = plan(r)
        if p and (publisher is None or publisher in p[0]) and (exclude is None or exclude not in p[0]):
            out.append(r)
    return out


def run(corpus: Path, *, limit: int | None = None, publisher: str | None = None, exclude: str | None = None,
        dry_run: bool = False, headless: bool = False, wait_for_human_s: int = 300) -> dict:
    # Publishers other than IEEE first: those are the ones that show bot checks, best handled
    # while the person who can solve them is at the screen.
    todo = sorted(candidates(corpus, publisher, exclude), key=lambda r: plan(r)[0] == "ieeexplore.ieee.org")[: limit or None]
    if dry_run:
        return {"would_try": len(todo), "by_host": dict(Counter(plan(r)[0] for r in todo).most_common())}
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    stats: Counter[str] = Counter()
    per_host: Counter[str] = Counter()
    blocked: set[str] = set()
    with Browser(headless=headless) as br, LEDGER.open("a", encoding="utf-8") as fh:
        for r in todo:
            host, entry = plan(r)
            if host in blocked or per_host[host] >= CAP_PER_HOST:
                stats["deferred"] += 1
                continue
            per_host[host] += 1
            prior = latest.get(r["id"], {})
            row = {"record_id": r["id"], "doi": r.get("doi"), "tier": 3, "route": None,
                   "tried": sorted(set(prior.get("tried", [])) | {ROUTE}),
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "not_retrieved"}
            try:
                br._space(host)
                final, html = br.open(entry, wait_for_human_s)
                url = pdf_url(host, r, final, html)
                data = br.pdf(url, referer=final) if url else None
                if data and pdf_pages(data) > 1:
                    PDF_DIR.mkdir(parents=True, exist_ok=True)
                    path = PDF_DIR / f"{slug(r)}.pdf"
                    path.write_bytes(data)
                    text = extract_text(path, r)
                    row |= {"status": "retrieved", "route": f"{ROUTE}:{host}", "pdf": str(path.relative_to(REPO_ROOT)),
                            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                            "text": str(text.relative_to(REPO_ROOT)) if text else None}
            except Challenged as e:
                blocked.add(host)
                row["tried"].remove(ROUTE)  # not a real attempt: retry once the challenge is resolved
                row["inconclusive"] = [ROUTE]
                row["challenge"] = str(e)
            except Exception as e:  # page timeouts, navigation errors: this record only, not the run
                row["tried"].remove(ROUTE)
                row["inconclusive"] = [ROUTE]
                row["error"] = f"{type(e).__name__}: {e}"[:300]
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            stats[row["route"] or ("challenged" if "challenge" in row else "not_retrieved")] += 1
    apply(corpus)
    return {"attempted": len(todo), "by_outcome": dict(stats), "challenged_hosts": sorted(blocked)}
