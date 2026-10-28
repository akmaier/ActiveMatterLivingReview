# Browser work: full texts the APIs cannot supply, and drafting in a chat interface

Two steps of the review run in a real browser: retrieving full texts the publisher APIs and
open-access routes could not supply, and (optionally) drafting manuscript prose in a web chat
such as ChatGPT. This file records how both were done, including the details that made them
work.

## 1. Full text, tier 3: a visible Chrome driven by Playwright (`amlr fulltext-browser`)

Run it after `amlr fulltext` (tier 1, publisher TDM APIs, and tier 2, open access), for the
records still lacking a full text.

**Prerequisites**

- Google Chrome installed. amlr starts it through Playwright with `channel="chrome"`, so no
  Playwright browser download (`playwright install`) is needed; the `playwright` Python package
  comes with `pip install -e "pipeline[dev]"`.
- Institutional access by IP: run on the campus network or the institution's VPN, so the
  publisher pages recognise the subscription.
- A desktop session. The window is visible on purpose; a person must be at the screen.

**Commands**

```bash
amlr fulltext-browser --dry-run                 # how many records, per publisher host
amlr fulltext-browser --exclude ieee            # everything except IEEE first
amlr fulltext-browser --publisher ieee          # then IEEE
amlr fulltext-browser --only <record_id> ...    # retry named records
```

**How it works, and why**

- *Its own persistent profile* at `~/.amlr/browser_profile`. Cookies and logins survive
  between runs and stay separate from your everyday browser. If a publisher wants a login
  (Shibboleth / "access through your institution"), do it once in that window; later runs
  reuse it.
- *A browser as a person uses it*: no user-agent override, no stealth plugins, no
  CAPTCHA solving. A page that shows a bot check (CAPTCHA, "verify you are human", a Cloudflare
  challenge, a Radware `perfdrive.com` redirect) is brought to the front and left for the person at the screen for up
  to `--wait-for-human` seconds (default 300). Solved in time, the run resumes; otherwise the
  host is skipped for the rest of the run. A challenged record is logged as *inconclusive*,
  not as tried, so the next run attempts it again.
- *Polite pacing*: at least 15 s between requests to the same host (25 s for IEEE Xplore) and
  at most 40 records per host per run, so the institution's access is not flagged for
  systematic downloading. Hosts other than IEEE run first, because they are the ones that show
  bot checks, best handled while you are at the screen.
- *Finding the PDF*: the record's landing page is opened through `https://doi.org/<doi>` (IEEE
  by its article number), then the PDF URL is derived per publisher:
  IEEE `stampPDF/getPDF.jsp?tp=&arnumber=<n>`, Science and PNAS `/doi/pdf/<doi>?download=true`,
  IOP `/article/<doi>/pdf`, and for every other publisher the page's
  `<meta name="citation_pdf_url">`.
- *Downloading with the page's session*: the PDF is requested through the browser context
  (same cookies, `Referer` set to the landing page, `Accept: application/pdf`). If that does
  not return a PDF, the URL is opened as a navigation and the browser download is captured.
- *Checks*: only a real PDF (`%PDF-` header, minimum size) with more than one page is kept;
  a one-page file is usually a cover sheet or a first-page preview. Text is extracted at once
  into `data/fulltext_text/`.
- Every attempt is a row in the full-text ledger, so the route, the file hash and the outcome
  of each record are on record.

## 2. Full text, tier 4: your own browser (`amlr fulltext-list`, `amlr fulltext-import`)

For what tier 3 could not fetch.

```bash
amlr fulltext-list                # writes data/fulltext/manual-<date>.html and opens it
# open each link, use the publisher's own "Download PDF", save to ~/Downloads
amlr fulltext-import              # matches the new PDFs in ~/Downloads to records
amlr fulltext-import /other/dir --since-hours 72
```

- The list is ordered by DOI prefix, so one publisher's papers come together; a record without
  a DOI gets a Google Scholar title search instead. IEEE is left out unless
  `--include-ieee`, because tier 3 handles it. On macOS the list opens in Safari, which
  keeps your publisher logins out of the Playwright profile; elsewhere in the default browser.
- File names do not matter. A PDF is matched by the DOI on its first pages, by an Elsevier PII,
  or by the record's title in the title region of page 1 (at least 90 % of the title words;
  ties count as no match). One-page files are rejected. Unmatched PDFs are listed and left
  where they are.
- Two helpers in `amlr.fulltext.manual` have no CLI command: `organize_downloads()` moves new
  matches into `docs/` and sends duplicates to the Trash (dry run by default; nothing is
  deleted permanently), and `import_page_text()` imports article text read from a publisher's
  HTML page when no PDF is offered (at least 5,000 characters per record).

What still has no full text is then assessed on the abstract (`amlr fulltext-abstract-only`,
PROTOCOL.md §6), and `amlr fulltext-finalize` marks the rest as not retrieved for the PRISMA
flow.

**Copyright**: PDFs go to `docs/` and extracted text to `data/fulltext_text/`; both are
gitignored. Never commit subscriber content.

## 3. Drafting prose in the ChatGPT web interface with an agent in Chrome

`amlr draft` sends one section at a time to Codex through `amlr bridge` (pipeline/README.md).
When Codex ran out of credits on 2026-10-17, the manuscript was drafted instead in one ChatGPT
web conversation, driven by Claude in Chrome (a browser-automation extension); the log is
`paper/drafts/chatgpt-2026-10-17.md`. This is the procedure.

**Set-up**

1. Put the context files in one folder, as in `data/chatgpt_context/`: the included-studies
   CSV of the snapshot, the PRISMA counts, a protocol bundle, the validation results,
   `paper/sections.yml`, the figure list and the voice guide.
2. Write the kickoff message with the hard rules (`data/chatgpt_context/kickoff.txt` is the
   one used): LaTeX only in one fenced block, `\cite` keys only from the CSV and
   `\todocite{}` otherwise, every number computed from the files with the chat's Python tool,
   cite broadly, typesetting rules for two-column pages, figures from the list, placeholders
   for facts the files do not hold, and the CONTINUE rule for long sections.
3. Open a new conversation, attach the files, send the kickoff, and wait for "Ready" with the
   study count and snapshot date before asking for the first section.

**Techniques that made the automation reliable**

- *Long messages as attachments*: copy the text to the clipboard (`pbcopy < request.txt` on
  macOS) and paste it into the message box with Cmd+V. The web interface turns a long paste
  into an attachment, which is sent intact; typing it key by key is slow and can be cut off.
- *Sending*: click the send button by script,
  `document.querySelector('button[data-testid="send-button"]').click()`, rather than by screen
  coordinates, which move with the layout.
- *Waiting*: a long section takes many minutes. Poll the page every minute or two from
  outside (a background `sleep`, then check whether the stop button is gone) instead of one
  long wait inside the browser tool, which times out.
- *Collecting the answer*: ask the model to begin each returned file with a marker line, e.g.
  `% FILE: sections/methods.tex`. Then select the message elements whose text starts with
  that marker and save their text through a Blob download
  (`URL.createObjectURL(new Blob([text]))` on an `<a download>` link) into `~/Downloads`.
  Copying from the screen loses characters and line breaks.
- *Long sections*: if a reply ends with CONTINUE, ask for the rest; the model continues in a
  new code block without repeating anything.
- *Check every reply before using it*: citation keys, numbers, and macros against the
  previous version and the CSV (counts per key and per grouping); a model may pool
  citations at paragraph ends, drop list items, or invent expansions of acronyms. Reject and
  re-request rather than repair by hand where the damage is broad.
- *Leave the account alone*: the agent does not click purchase, upgrade or "auto-reload
  credits" offers, and never enters credentials. A login is the person's job.

Every request and reply is archived in `paper/drafts/` and disclosed in the paper's
acknowledgments and methods, as APS policy requires for AI-assisted writing.
