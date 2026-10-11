---
layout: page
title: "Change log"
permalink: /changelog/
---

Append-only. One entry per `amlr update` run.

{% if site.data.changelog %}
{% for entry in site.data.changelog %}
### {{ entry.date }} — {{ entry.title }}

{{ entry.summary }}

{% if entry.added %}- Added: {{ entry.added }}{% endif %}
{% if entry.removed %}- Removed: {{ entry.removed }}{% endif %}
{% if entry.modified %}- Modified: {{ entry.modified }}{% endif %}

{% endfor %}
{% else %}
_No updates recorded yet._
{% endif %}
