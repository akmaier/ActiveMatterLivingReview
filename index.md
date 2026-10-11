---
layout: home
title: "Active Matter Living Review"
---

A **living systematic review** of **robotic active matter**, built to the
[PRISMA 2020](https://www.prisma-statement.org/prisma-2020) standard.

The companion manuscript is being prepared for *Reviews of Modern
Physics*; this site is updated monthly from the same corpus the paper
cites.

## What you'll find here

{% assign counts = site.data.prisma_counts %}

- [**Corpus**]({{ "/corpus/" | relative_url }}) — the current included
  studies ({{ counts.included_studies | default: "0" }} records as of
  {{ counts.snapshot_date | default: "pre-registration" }}).
- [**PRISMA flow**]({{ "/prisma/" | relative_url }}) — the identification
  → screening → included counts.
- [**Methods**]({{ "/methods/" | relative_url }}) — the frozen protocol,
  eligibility criteria, and per-database search strings.
- [**Taxonomy**]({{ "/taxonomy/" | relative_url }}) — the robotic
  active-matter taxonomy the review structures its findings around.
- [**Change log**]({{ "/changelog/" | relative_url }}) — what changed
  since the last snapshot.

## Status

First review cycle in progress (started 2026-10-11): searches run and
title/abstract screening under way. The PRISMA counts on this site are
updated when each stage completes. Once the OSF registration is minted,
its DOI will appear here.

## How to cite

See [`CITATION.cff`](https://github.com/akmaier/ActiveMatterLivingReview/blob/main/CITATION.cff).
