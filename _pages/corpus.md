---
layout: page
title: "Corpus"
permalink: /corpus/
---

The table below is regenerated from `_data/corpus.yml` on every build.
Each row links to the publisher's DOI resolver; PDFs are not hosted on
this site.

<link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css">
<script type="text/javascript" src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script type="text/javascript" src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>

<table id="corpus" class="display" style="width:100%">
  <thead>
    <tr>
      <th>Year</th>
      <th>Title</th>
      <th>Authors</th>
      <th>Venue</th>
      <th>Platform</th>
      <th>Agents</th>
      <th>DOI</th>
    </tr>
  </thead>
  <tbody>
    {% for row in site.data.corpus %}
    <tr>
      <td>{{ row.year }}</td>
      <td>{{ row.title }}</td>
      <td>{{ row.authors }}</td>
      <td>{{ row.venue }}</td>
      <td>{{ row.platform }}</td>
      <td>{{ row.agents }}</td>
      <td>{% if row.doi %}<a href="https://doi.org/{{ row.doi }}">{{ row.doi }}</a>{% endif %}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<script>
  $(function() {
    $('#corpus').DataTable({ pageLength: 25, order: [[0, 'desc']] });
  });
</script>
