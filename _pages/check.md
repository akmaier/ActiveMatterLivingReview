---
layout: page
title: "Human check"
permalink: /check/
---

These are the items the protocol (§6 *Validation*, §7) leaves to the author. Each queue opens
one item at a time. Your labels are saved in this browser only. **Export** downloads them as a
JSON file, and `amlr human-import <file>` writes them into the review.

- **Title/abstract sample:** 200 records drawn at random from the screened records. The panel
  votes stay hidden until you decide, so this label is independent and measures the panel's
  sensitivity and specificity.
- **Full-text splits:** all reports where one of the three models disagreed. Your decision
  replaces the panel decision. Panel includes are listed first.
- **Extraction conflicts:** fields where all three extractors gave different answers. Pick one of
  their answers or enter your own.
- **Seed papers:** the known-item set, including the PULS brainbot papers the panel excluded as
  single-agent (E1).

Keys: <kbd>I</kbd> include · <kbd>1</kbd>–<kbd>6</kbd> exclude with E1–E6 · <kbd>U</kbd> unsure ·
<kbd>←</kbd>/<kbd>→</kbd> previous/next · <kbd>N</kbd> next open item · <kbd>V</kbd> show the
panel votes.

<link rel="stylesheet" href="{{ '/assets/css/check.css' | relative_url }}">
<div id="hc" data-queue="{{ '/assets/human_check.json' | relative_url }}"><p class="hc-loading">Loading the queue…</p></div>
<script src="{{ '/assets/js/check.js' | relative_url }}"></script>
