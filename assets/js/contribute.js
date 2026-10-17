/* Paper submission form (/contribute/): builds submissions/<slug>.yml and opens GitHub's
 * "propose new file" page, which forks the repository for the visitor and opens a pull request. */
(function () {
  "use strict";

  var REPO = "akmaier/ActiveMatterLivingReview";
  var form = document.getElementById("sub");
  if (!form) return;
  var $ = function (id) { return document.getElementById(id); };
  var msg = $("sub-msg");

  function say(text, kind) { msg.textContent = text; msg.className = "sub-msg " + (kind || ""); }
  function val(id) { return ($(id).value || "").trim(); }
  function q(s) { return '"' + String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"'; }
  function cleanDoi(s) { return s.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, "").toLowerCase(); }

  function yaml() {
    var authors = val("sub-authors").split(";").map(function (a) { return a.trim(); }).filter(Boolean);
    var lines = [
      "# Proposed via the contribute form on the living-review site.",
      "doi: " + (cleanDoi(val("sub-doi")) || ""),
      "arxiv: " + val("sub-arxiv"),
      "title: " + q(val("sub-title")),
      "authors: [" + authors.map(q).join(", ") + "]",
      "year: " + val("sub-year"),
      "venue: " + (val("sub-venue") ? q(val("sub-venue")) : ""),
      "why: >-",
      "  " + val("sub-why").replace(/\s+/g, " "),
      "submitted_by: " + val("sub-by")
    ];
    return lines.join("\n") + "\n";
  }

  function slug() {
    var first = (val("sub-authors").split(";")[0] || "anon").trim().split(/[\s,]+/);
    var last = (first.length > 1 && /,/.test(val("sub-authors").split(";")[0]) ? first[0] : first[first.length - 1]) || "anon";
    var word = (val("sub-title").toLowerCase().match(/[a-z]{4,}/g) || ["paper"])[0];
    return (last + "-" + (val("sub-year") || "nd") + "-" + word).toLowerCase().normalize("NFD").replace(/[^a-z0-9-]+/g, "");
  }

  function refresh() { $("sub-yaml").textContent = yaml(); }
  form.addEventListener("input", refresh);
  refresh();

  $("sub-lookup").addEventListener("click", function () {
    var doi = cleanDoi(val("sub-doi"));
    if (!/^10\.\d{4,9}\/\S+$/.test(doi)) { say("That does not look like a DOI (it starts with 10.).", "bad"); return; }
    say("Looking up the DOI at Crossref…");
    fetch("https://api.crossref.org/works/" + encodeURIComponent(doi))
      .then(function (r) { if (!r.ok) throw new Error(r.status === 404 ? "Crossref does not know this DOI" : "HTTP " + r.status); return r.json(); })
      .then(function (j) {
        var m = j.message;
        $("sub-title").value = (m.title || [""])[0];
        $("sub-authors").value = (m.author || []).map(function (a) { return [a.given, a.family].filter(Boolean).join(" ") || a.name; }).join("; ");
        var parts = (m.issued && m.issued["date-parts"] && m.issued["date-parts"][0]) || [];
        if (parts[0]) $("sub-year").value = parts[0];
        $("sub-venue").value = (m["container-title"] || [""])[0] || "";
        refresh();
        say("Filled in from Crossref. Add a sentence on why it belongs.", "ok");
        $("sub-why").focus();
      })
      .catch(function (e) { say("Lookup failed: " + e.message + ". Fill in the fields by hand.", "bad"); });
  });

  $("sub-copy").addEventListener("click", function () {
    var text = yaml();
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
      .then(function () { say("YAML copied.", "ok"); })
      .catch(function () { $("sub-yaml").parentNode.open = true; say("Select the preview below and copy it.", ""); });
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var missing = [];
    if (!val("sub-title")) missing.push("title");
    if (!/^\d{4}$/.test(val("sub-year"))) missing.push("year");
    if (!val("sub-why")) missing.push("why it belongs");
    if (!cleanDoi(val("sub-doi")) && !val("sub-arxiv")) missing.push("a DOI or an arXiv id");
    if (missing.length) { say("Please add: " + missing.join(", ") + ".", "bad"); return; }
    var url = "https://github.com/" + REPO + "/new/main/submissions?filename=" + encodeURIComponent(slug() + ".yml") +
      "&value=" + encodeURIComponent(yaml()) +
      "&message=" + encodeURIComponent("Propose: " + val("sub-title").slice(0, 60)) +
      "&description=" + encodeURIComponent(val("sub-why"));
    window.open(url, "_blank", "noopener");
    say("GitHub opened in a new tab: choose \"Propose changes\", then \"Create pull request\".", "ok");
  });
})();
