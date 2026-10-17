---
layout: page
title: "Taxonomy"
permalink: /taxonomy/
---

The taxonomy is built from the data extracted for every included study, so it has no fixed shape.
Choose which attributes form the levels and in what order. The root is the whole corpus, and the
tree re-forms as you change it. Click a node to open or close it and to list its studies.
Attributes that can carry several labels (phenomena, theory, interaction) place a study under
each of its labels, so the counts at one level can add up to more than the parent.

<link rel="stylesheet" href="{{ '/assets/css/taxonomy.css' | relative_url }}">
<div id="tx" data-src="{{ '/assets/taxonomy.json' | relative_url }}"><p class="tx-muted">Loading the taxonomy…</p></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script src="{{ '/assets/js/taxonomy.js' | relative_url }}"></script>
