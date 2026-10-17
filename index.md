---
layout: page
title: "Robotic active matter: a living review"
---

{% assign counts = site.data.prisma_counts %}
<p class="home-lead">A living systematic review (PRISMA 2020) of physical collectives of interacting robots and
programmable active particles: <strong>{{ counts.included_studies }}</strong> included studies, snapshot
{{ counts.snapshot_date }}. Arrange the taxonomy below by any of the extracted attributes, or
<a href="{{ '/contribute/' | relative_url }}">propose a paper</a> we missed.</p>

{% include taxonomy.html %}

## About this review

The companion manuscript is being prepared for *Reviews of Modern Physics*. Every number on this
site comes from the same corpus the paper cites and is regenerated with each update.

- [**Corpus**]({{ "/corpus/" | relative_url }}): all included studies with their extracted data.
- [**PRISMA flow**]({{ "/prisma/" | relative_url }}): identification, screening and inclusion counts.
- [**Methods**]({{ "/methods/" | relative_url }}): the frozen protocol, its amendments and the search strings.
- [**Human check**]({{ "/check/" | relative_url }}): the author's validation and adjudication queue.
- [**Contribute**]({{ "/contribute/" | relative_url }}): add a paper through a reviewed GitHub pull request.
- [**Change log**]({{ "/changelog/" | relative_url }}): what changed in each update.

## How to cite

See [`CITATION.cff`](https://github.com/akmaier/ActiveMatterLivingReview/blob/main/CITATION.cff).
