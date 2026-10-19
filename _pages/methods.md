---
layout: page
title: "Methods"
permalink: /methods/
---

The frozen protocol, eligibility criteria, and per-database search
strings live under [`protocol/`](https://github.com/akmaier/ActiveMatterLivingReview/tree/main/protocol)
in the repository. The review is registered on OSF Registries:
[osf.io/g7c8d](https://osf.io/g7c8d).

## Databases queried

{% for s in site.data.sources %}
- **{{ s.name }}** — {{ s.endpoint }} (last run: {{ s.last_run | default: "pending" }})
{% endfor %}

## Eligibility criteria

See [`protocol/PICO.md`](https://github.com/akmaier/ActiveMatterLivingReview/blob/main/protocol/PICO.md).

## PRISMA 2020 checklist

The 27-item checklist, with per-item anchors into the repository, lives
at [`protocol/prisma_checklist.md`](https://github.com/akmaier/ActiveMatterLivingReview/blob/main/protocol/prisma_checklist.md).
