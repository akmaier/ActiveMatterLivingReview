"""amlr: Active Matter Living Review pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml
from rich import print as rprint

from . import __version__
from .config import REPO_ROOT, load_tdm_config

app = typer.Typer(no_args_is_help=True, help=__doc__)

CORPUS = REPO_ROOT / "data" / "corpus.jsonl"


@app.command()
def version() -> None:
    """Print the amlr package version."""
    rprint(f"amlr {__version__}")


@app.command("config-check")
def config_check() -> None:
    """Show which TDM credentials are set (never prints values)."""
    rprint(load_tdm_config().redacted())


@app.command("search-count")
def search_count() -> None:
    """Hit count per source for the current concept blocks (no records stored)."""
    from .search import SYNTAX, count

    for src in SYNTAX:
        try:
            rprint(f"{src:20s} {count(src)['count']:>7}")
        except Exception as e:  # one failing source should not hide the others
            rprint(f"{src:20s} [red]{type(e).__name__}: {e}[/red]")


@app.command("search-validate")
def search_validate() -> None:
    """Known-item recall on protocol/search_strategies/seed_set.yml (OpenAlex and arXiv)."""
    from .search import validate_seed_set

    rows = validate_seed_set()
    mark = {True: "[green]hit[/green]", False: "[red]MISS[/red]", None: "-"}
    for r in rows:
        rprint(f"OA {mark[r['openalex']]:>18}  arXiv {mark[r['arxiv']]:>18}  abs={'y' if r['has_abstract'] else 'n'}  {r['title'][:70]}")
    either = sum(bool(r["openalex"] or r["arxiv"]) for r in rows)
    rprint(f"recall (either source): {either}/{len(rows)}")


@app.command()
def fetch(source: str = typer.Argument(..., help="openalex | arxiv | pubmed | hal | europepmc_biorxiv | crossref | all")) -> None:
    """Retrieve all records for a source into data/raw/ and log the dated strategy file."""
    from .fetch import FETCHERS
    from .fetch import fetch as run

    for src in (FETCHERS if source == "all" else [source]):
        try:
            rprint(run(src))
        except Exception as e:  # keep going so one outage does not block the other sources
            rprint(f"[red]{src}: {type(e).__name__}: {e}[/red]")


FROZEN_FILES = ["protocol/PROTOCOL.md", "protocol/PICO.md", "protocol/screening_prompt.md",
                "protocol/extraction_prompt.md",
                "protocol/search_strategies/concepts.yml", "protocol/search_strategies/seed_set.yml"]


@app.command()
def freeze(note: str = typer.Option("", help="Why this freeze (e.g. 'pre-screening', 'amendment 1')")) -> None:
    """Write protocol/freeze-<UTC timestamp>.json with SHA-256 of every frozen protocol file."""
    import hashlib
    import subprocess
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "protocol"],
                                capture_output=True, text=True).stdout.strip())
    manifest = {
        "frozen_at_utc": now.isoformat(timespec="seconds"),
        "note": note,
        "git_head": head,
        "protocol_uncommitted_at_freeze": dirty,
        "sha256": {f: hashlib.sha256((REPO_ROOT / f).read_bytes()).hexdigest() for f in FROZEN_FILES},
    }
    out = REPO_ROOT / "protocol" / f"freeze-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rprint(f"wrote {out.relative_to(REPO_ROOT)}")
    rprint(manifest)


@app.command("build-corpus")
def build_corpus() -> None:
    """Deduplicate the latest retrieval of every source into data/corpus.jsonl (keeps screening state)."""
    from .corpus import build

    rprint(build())


@app.command()
def dedup(
    inputs: list[Path] = typer.Argument(None),
    out: Path = typer.Option(CORPUS, "--out"),
) -> None:
    """Merge per-source JSONL files into the canonical corpus."""
    from .dedup import merge_records
    from .storage import read_jsonl, write_jsonl

    records: list[dict] = []
    for p in inputs or []:
        records.extend(read_jsonl(p))
    merged = merge_records(records)
    out.unlink(missing_ok=True)
    n = write_jsonl(out, merged)
    rprint(f"{len(records)} records in, {n} after merge → {out}")


@app.command("screen-export")
def screen_export(
    corpus: Path = typer.Option(CORPUS),
    out: Path = typer.Option(REPO_ROOT / "data" / "screening" / "to_screen.csv"),
) -> None:
    """Emit a CSV for ASReview Lab."""
    from .screen import export_for_asreview
    from .storage import read_jsonl

    n = export_for_asreview(read_jsonl(corpus), out)
    rprint(f"exported {n} records → {out}")


@app.command("screen-llm")
def screen_llm(
    stage: str = typer.Option("title_abstract", help="title_abstract | full_text"),
    corpus: Path = typer.Option(CORPUS),
    limit: int = typer.Option(None, help="Screen at most this many records"),
    workers: int = typer.Option(6, help="Concurrent requests for R1/R2"),
    tiebreak_workers: int = typer.Option(4, help="Concurrent requests for R3"),
    mode: str = typer.Option("adaptive", help="adaptive (R3 only where it can matter) | full"),
    audit: bool = typer.Option(True, help="R3 also votes on the fixed 10% audit sample"),
) -> None:
    """Have the three-LLM panel vote on eligible records and apply majority decisions."""
    from .fulltext.dispatch import text_for
    from .schema import Stage
    from .screen_llm import run_panel

    rprint(run_panel(Stage(stage), corpus, mode=mode, audit=audit, limit=limit, workers=workers,
                     tiebreak_workers=tiebreak_workers,
                     full_text_for=text_for if stage == "full_text" else None))


@app.command()
def fulltext(
    corpus: Path = typer.Option(CORPUS),
    limit: int = typer.Option(None),
    workers: int = typer.Option(4),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only summarize what would be tried"),
    retry: bool = typer.Option(False, "--retry", help="Only untried routes for records still missing"),
    force_route: list[str] = typer.Option([], "--force-route", help="Route to retry even if already tried"),
) -> None:
    """Tier 1 (TDM / institutional) and tier 2 (open access) PDFs for screened-in records into docs/."""
    from .fulltext.dispatch import run

    rprint(run(corpus, limit=limit, workers=workers, dry_run=dry_run, retry=retry, force_routes=frozenset(force_route)))


@app.command()
def extract(
    corpus: Path = typer.Option(CORPUS),
    limit: int = typer.Option(None),
    workers: int = typer.Option(4),
) -> None:
    """Panel data extraction and risk-of-bias rating for included studies (R1 + R3, R2 arbitrates)."""
    from .extract import run
    from .fulltext.dispatch import text_for

    rprint(run(corpus, text_for, limit=limit, workers=workers))


@app.command("fulltext-browser")
def fulltext_browser(
    corpus: Path = typer.Option(CORPUS),
    limit: int = typer.Option(None),
    publisher: str = typer.Option(None, help="Restrict to hosts containing this string, e.g. ieee"),
    exclude: str = typer.Option(None, help="Skip hosts containing this string, e.g. ieee"),
    wait_for_human: int = typer.Option(300, help="Seconds to wait at a bot check for the person at the screen (0: skip host)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Tier 3: visible Chrome over FAU institutional access for records the APIs could not supply."""
    from .fulltext.browser import run

    rprint(run(corpus, limit=limit, publisher=publisher, exclude=exclude, dry_run=dry_run,
               wait_for_human_s=wait_for_human))


@app.command("fulltext-list")
def fulltext_list(
    corpus: Path = typer.Option(CORPUS),
    include_ieee: bool = typer.Option(False, help="Also list IEEE papers (normally fetched by fulltext-browser)"),
) -> None:
    """Write a click-through HTML list of papers still lacking full text, for the author's browser."""
    import subprocess

    from .fulltext.manual import write_list

    out = write_list(corpus, include_ieee)
    rprint(f"wrote {out}")
    subprocess.run(["open", "-a", "Safari", str(out)], check=False)


@app.command("fulltext-import")
def fulltext_import(
    src: Path = typer.Argument(Path.home() / "Downloads"),
    corpus: Path = typer.Option(CORPUS),
    since_hours: float = typer.Option(24, help="Only PDFs modified within this many hours"),
) -> None:
    """Import PDFs the author saved (matched by DOI, Elsevier PII, or title) into docs/."""
    from datetime import datetime, timedelta, timezone

    from .fulltext.manual import import_dir

    rprint(import_dir(corpus, src, since=datetime.now(timezone.utc) - timedelta(hours=since_hours)))


@app.command("fulltext-abstract-only")
def fulltext_abstract_only(
    corpus: Path = typer.Option(CORPUS),
    exclude_ieee: bool = typer.Option(False, help="Leave IEEE records for the browser tier"),
    skip: list[str] = typer.Option([], help="Record ids still being retrieved"),
    include_conference_abstracts: bool = typer.Option(True, help="Also records whose only report is an abstract"),
) -> None:
    """Assess eligibility on the abstract for papers whose full text cannot be obtained."""
    from .fulltext.browser import plan
    from .fulltext.dispatch import mark_abstract_only
    from .fulltext.manual import missing
    from .storage import read_jsonl

    ids = [r["id"] for r in missing(corpus, include_ieee=not exclude_ieee) if r["id"] not in skip]
    if include_conference_abstracts:
        ids += [r["id"] for r in read_jsonl(corpus) if r.get("acquisition_status") == "no_full_report"]
    rprint(mark_abstract_only(corpus, ids, "full text unobtainable after all retrieval tiers; assessed on abstract"))


@app.command("fulltext-finalize")
def fulltext_finalize(corpus: Path = typer.Option(CORPUS)) -> None:
    """After the Chrome tier: mark records still lacking full text as not retrieved."""
    from .fulltext.dispatch import finalize

    rprint(f"{finalize(corpus)} records marked fulltext_not_retrieved")


@app.command("screen-report")
def screen_report(stage: str = typer.Option("title_abstract")) -> None:
    """Fleiss' and pairwise Cohen's kappa for the panel at one stage."""
    from .schema import Stage
    from .screen_llm import agreement_report

    rprint(agreement_report(Stage(stage)))


@app.command()
def prisma(corpus: Path = typer.Option(CORPUS)) -> None:
    """Emit PRISMA counts (site + snapshot) and the flow SVG (site + paper)."""
    from .prisma import compute_counts, write_flow_svg, write_flow_tikz
    from .storage import read_jsonl

    manifest_path = REPO_ROOT / "data" / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    counts = compute_counts(read_jsonl(corpus), manifest=manifest)
    (REPO_ROOT / "_data" / "prisma_counts.yml").write_text(
        yaml.safe_dump(counts, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    snap = REPO_ROOT / "data" / "snapshots" / counts["snapshot_date"]
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "prisma_counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    write_flow_svg(counts, REPO_ROOT / "assets" / "prisma_flow.svg")
    write_flow_tikz(counts, REPO_ROOT / "paper" / "figures" / "prisma_flow.tex")
    rprint(f"PRISMA counts and flow written (snapshot {counts['snapshot_date']})")


@app.command()
def render(corpus: Path = typer.Option(CORPUS)) -> None:
    """Emit _data/corpus.yml, paper/refs.bib, the included-studies snapshot and the /check/ queue."""
    from .human import build_queue
    from .render import write_bibtex, write_corpus_yml, write_snapshot
    from .storage import read_jsonl

    rows = read_jsonl(corpus)
    rprint(f"wrote {write_corpus_yml(rows)}, {write_bibtex(rows)} and {write_snapshot(rows)}")
    rprint(f"human-check queue: {build_queue(corpus)}")


@app.command()
def evidence(
    corpus: Path = typer.Option(CORPUS),
    kind: list[str] = typer.Option(["ft_split", "extraction"], help="ft_split and/or extraction"),
    reviewer: list[str] = typer.Option(["R1", "R2", "R3"], help="Models to ask"),
    ledger: str = typer.Option("", help="Suffix for a separate ledger file (parallel runs)"),
    limit: int = typer.Option(None),
    workers: int = typer.Option(6),
) -> None:
    """Ask each model for verbatim evidence behind its answer on every conflict (for /check/)."""
    from .evidence import LEDGER, run
    from .fulltext.dispatch import text_for
    from .human import build_queue

    path = LEDGER.with_name(f"{LEDGER.stem}-{ledger}.jsonl") if ledger else LEDGER
    rprint(run(corpus, text_for, kinds=tuple(kind), reviewers=tuple(reviewer), limit=limit,
               workers=workers, ledger=path))
    rprint(f"human-check queue: {build_queue(corpus)}")


@app.command("human-queue")
def human_queue(corpus: Path = typer.Option(CORPUS)) -> None:
    """Write assets/human_check.json, the queue behind the site's /check/ page."""
    from .human import build_queue

    rprint(build_queue(corpus))


@app.command("human-import")
def human_import(
    files: list[Path] = typer.Argument(..., help="JSON exports from the /check/ page"),
    corpus: Path = typer.Option(CORPUS),
) -> None:
    """Append the author's labels to data/human_check/labels.jsonl and apply them to the corpus."""
    from .human import apply, import_labels, report

    for f in files:
        rprint(f"{f.name}: {import_labels(f)}")
    rprint(apply(corpus))
    rprint(report(corpus))


@app.command("human-report")
def human_report(corpus: Path = typer.Option(CORPUS)) -> None:
    """Panel sensitivity, specificity and kappa against the author's labels."""
    from .human import report

    rprint(report(corpus))


@app.command()
def draft(
    section: str = typer.Argument(..., help="Section id from paper/sections.yml"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the prompt instead of sending it"),
) -> None:
    """Have Codex draft a paper section via the local bridge."""
    from .codex import draft_section

    draft_section(section=section, dry_run=dry_run)


if __name__ == "__main__":  # pragma: no cover
    app()
