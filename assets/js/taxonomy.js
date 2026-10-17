/* Reconfigurable taxonomy of the included studies (/taxonomy/).
 * The reader picks which extracted attributes form the levels and in what order; the tree is
 * re-grouped from assets/taxonomy.json and animates between configurations. Nodes are keyed by
 * their path, so a node that survives a change glides to its new place. Requires d3 v7. */
(function () {
  "use strict";

  var root = document.getElementById("tx");
  if (!root || !window.d3) return;
  var d3 = window.d3;
  var DUR = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650;
  var MAX_CHILDREN = 12;
  var DEFAULT = ["platform_class", "phenomena", "theory_compared"];

  var data, facets, byId, levels = [], tree, svg, gLinks, gNodes, color, selected = null;
  var expanded = {}; // path -> bool (user toggles survive re-grouping where paths survive)

  function esc(s) {
    return String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function readHash() {
    var m = /levels=([^&]+)/.exec(window.location.hash || "");
    if (!m) return null;
    var ids = decodeURIComponent(m[1]).split(",").filter(function (id) { return byId[id]; });
    return ids.length ? ids : null;
  }
  function writeHash() {
    try { history.replaceState(null, "", "#levels=" + levels.join(",")); } catch (e) { /* sandboxed */ }
  }

  // ---- grouping ----------------------------------------------------------------------------
  function group(studies, depth, path) {
    if (depth >= levels.length) return null;
    var f = levels[depth], buckets = {};
    studies.forEach(function (s) {
      (s.f[f] || ["not reported"]).forEach(function (v) { (buckets[v] = buckets[v] || []).push(s); });
    });
    var kids = Object.keys(buckets).map(function (k) { return { label: k, studies: buckets[k] }; })
      .sort(function (a, b) { return b.studies.length - a.studies.length || a.label.localeCompare(b.label); });
    if (kids.length > MAX_CHILDREN) {
      var tail = kids.splice(MAX_CHILDREN - 1), seen = {}, rest = [];
      tail.forEach(function (k) { k.studies.forEach(function (s) { if (!seen[s.key]) { seen[s.key] = 1; rest.push(s); } }); });
      kids.push({ label: "other (" + tail.length + " values)", studies: rest, other: tail.map(function (t) { return t.label; }) });
    }
    return kids.map(function (k) {
      var p = path + "/" + f + "=" + k.label;
      return { id: p, label: k.label, facet: f, studies: k.studies, other: k.other, children: group(k.studies, depth + 1, p) };
    });
  }

  function build() {
    var pool = matching();
    var top = { id: "root", label: query ? "Matching studies" : "All included studies", studies: pool, children: group(pool, 0, "root") };
    var h = d3.hierarchy(top, function (d) {
      if (!d.children) return null;
      var open = d.id === "root" || expanded[d.id] === true || (expanded[d.id] === undefined && depthOf(d.id) < 1);
      return open ? d.children : null;
    });
    return h;
  }
  // Search (as in the living review of Matl et al.): keep studies whose title, platform name or any
  // facet label contains every word of the query.
  var query = "";
  function matching() {
    if (!query) return data.studies;
    var words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return data.studies.filter(function (s) {
      if (!s._hay) {
        var parts = [s.title || "", s.platform_name || "", String(s.year || "")];
        Object.keys(s.f).forEach(function (k) { parts = parts.concat(s.f[k]); });
        s._hay = parts.join(" ").toLowerCase();
      }
      return words.every(function (w) { return s._hay.indexOf(w) >= 0; });
    });
  }
  function depthOf(id) { return id === "root" ? 0 : id.split("/").length - 1; }

  // ---- layout ----------------------------------------------------------------------------
  var margin = { top: 16, bottom: 16, left: 16, right: 8 };
  var LINE = 15, MIN_COL = 120, lastPos = {}, height = 0, zoom, zoomG, content = { w: 1, h: 1 };
  var ctx = document.createElement("canvas").getContext("2d");

  function labelFont() {
    var cs = window.getComputedStyle(root);
    return "12.5px " + cs.fontFamily;
  }

  // Greedy word wrap measured with the page font, so a label breaks before it reaches the next level.
  function wrap(text, maxW) {
    ctx.font = labelFont();
    var words = String(text).split(/\s+/), lines = [], cur = "";
    words.forEach(function (w) {
      var test = cur ? cur + " " + w : w;
      if (!cur || ctx.measureText(test).width <= maxW) cur = test;
      else { lines.push(cur); cur = w; }
    });
    if (cur) lines.push(cur);
    return lines;
  }

  function render(animate, keepId) {
    var h = build();
    var avail = root.querySelector(".tx-canvas").clientWidth;
    var depthMax = Math.max(1, levels.length);
    // One column per level plus one for the labels of the deepest level; scroll only when narrow.
    var colW = Math.max(MIN_COL, (avail - margin.left - margin.right) / (depthMax + 1));
    var width = Math.ceil(margin.left + margin.right + colW * (depthMax + 1));
    var n = d3.max(h.descendants(), function (d) { return d.data.studies.length; }) || 1;
    var r = d3.scaleSqrt().domain([1, n]).range([3.5, 15]);
    h.each(function (d) {
      d.rad = r(d.data.studies.length);
      d.lines = wrap(d.data.label + " (" + d.data.studies.length + ")", d.depth === 0 ? colW - 12 : colW - d.rad - 18);
    });
    tree = d3.tree().nodeSize([LINE, colW]).separation(function (a, b) {
      var need = (a.lines.length + b.lines.length) / 2 + 0.7;
      return a.parent === b.parent ? need : need + 0.5;
    });
    tree(h);
    var minX = Infinity, maxX = -Infinity;
    h.each(function (d) {
      d.y = d.depth * colW; // fixed column per level, so the tree grows rightwards as it unfolds
      var half = Math.max(d.rad, (d.lines.length * LINE) / 2);
      minX = Math.min(minX, d.x - half - (d.depth === 0 ? d.lines.length * LINE + 6 : 0));
      maxX = Math.max(maxX, d.x + half);
    });
    h.each(function (d) { d.x -= minX; });
    height = Math.ceil(maxX - minX);
    content = { w: width, h: height + margin.top + margin.bottom };
    var t = svg.transition().duration(animate ? DUR : 0).ease(d3.easeCubicInOut);
    // The viewport stays put: a clicked node keeps its place on screen while the tree re-forms
    // around it, by shifting the pan by however far the layout moved that node.
    if (keepId && lastPos[keepId]) {
      var moved = h.descendants().filter(function (d) { return d.data.id === keepId; })[0];
      if (moved) {
        var k = d3.zoomTransform(svg.node());
        var next = k.translate(-(moved.y - lastPos[keepId].y), -(moved.x - lastPos[keepId].x));
        svg.transition(t).call(zoom.transform, next);
      }
    }

    var nodes = h.descendants(), links = h.links();
    var origin = function (d) {
      // Enter from the nearest ancestor's previous position, so new branches unfold out of their parent.
      for (var a = d.parent; a; a = a.parent) if (lastPos[a.data.id]) return lastPos[a.data.id];
      return { x: lastPos.root ? lastPos.root.x : height / 2, y: 0 };
    };

    var link = gLinks.selectAll("path").data(links, function (d) { return d.target.data.id; });
    var diag = d3.linkHorizontal().x(function (d) { return d.y; }).y(function (d) { return d.x; });
    link.join(
      function (enter) {
        return enter.append("path").attr("class", "tx-link")
          .attr("d", function (d) { var o = origin(d.target); return diag({ source: o, target: o }); })
          .attr("stroke", function (d) { return tint(d.target); }).attr("stroke-opacity", 0)
          .call(function (e) { e.transition(t).attr("d", diag).attr("stroke-opacity", 0.55); });
      },
      function (update) { return update.call(function (u) { u.transition(t).attr("d", diag).attr("stroke", function (d) { return tint(d.target); }); }); },
      function (exit) {
        return exit.call(function (x) {
          x.transition(t).attr("stroke-opacity", 0).attr("d", function (d) {
            var p = nearestSurvivor(d.target, nodes); return diag({ source: p, target: p });
          }).remove();
        });
      });

    var node = gNodes.selectAll("g.tx-node").data(nodes, function (d) { return d.data.id; });
    node.join(
      function (enter) {
        var g = enter.append("g").attr("class", "tx-node")
          .attr("transform", function (d) { var o = origin(d); return "translate(" + o.y + "," + o.x + ")"; })
          .attr("opacity", 0)
          .on("click", function (ev, d) { toggle(d); })
          .on("keydown", function (ev, d) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(d); } })
          .attr("tabindex", 0).attr("role", "button");
        g.append("circle");
        g.append("text").attr("class", "tx-label");
        g.append("title");
        return g;
      },
      function (update) { return update; },
      function (exit) {
        return exit.call(function (x) {
          x.transition(t).attr("opacity", 0).attr("transform", function (d) {
            var p = nearestSurvivor(d, nodes); return "translate(" + p.y + "," + p.x + ")";
          }).remove();
        });
      })
      .call(function (g) {
        g.transition(t).attr("opacity", 1).attr("transform", function (d) { return "translate(" + d.y + "," + d.x + ")"; });
        g.classed("is-selected", function (d) { return selected === d.data.id; })
          .classed("has-kids", function (d) { return !!d.data.children; })
          .attr("aria-label", function (d) { return d.data.label + ", " + d.data.studies.length + " studies"; });
        g.select("circle").transition(t)
          .attr("r", function (d) { return r(d.data.studies.length); })
          .attr("fill", function (d) { return d.data.children && !d.children ? tint(d) : "#fff"; })
          .attr("stroke", function (d) { return tint(d); });
        g.select("text").each(function (d) {
          // Root: label above its circle. Others: label to the right, centred on the node.
          var x = d.depth === 0 ? -d.rad : d.rad + 6;
          var y0 = d.depth === 0 ? -d.rad - 6 - (d.lines.length - 1) * LINE : -((d.lines.length - 1) * LINE) / 2 + 4;
          d3.select(this).selectAll("tspan").data(d.lines).join("tspan")
            .attr("x", x).attr("y", function (l, i) { return y0 + i * LINE; }).text(function (l) { return l; });
        });
        g.select("title").text(function (d) {
          return d.data.label + " — " + d.data.studies.length + " studies" + (d.data.other ? "\n" + d.data.other.join(", ") : "") +
            (d.data.children ? (d.children ? "\nClick to fold" : "\nClick to unfold") : "");
        });
      });

    lastPos = {};
    nodes.forEach(function (d) { lastPos[d.data.id] = { x: d.x, y: d.y }; });
    if (!selected || !nodes.some(function (d) { return d.data.id === selected; })) selected = "root";
    showStudies(nodes.filter(function (d) { return d.data.id === selected; })[0]);
  }

  function nearestSurvivor(d, nodes) {
    var ids = {};
    nodes.forEach(function (n) { ids[n.data.id] = n; });
    for (var a = d.parent; a; a = a.parent) if (ids[a.data.id]) return { x: ids[a.data.id].x, y: ids[a.data.id].y };
    return { x: lastPos.root ? lastPos.root.x : 0, y: 0 };
  }

  function tint(d) {
    var a = d;
    while (a.depth > 1) a = a.parent;
    return a.depth === 0 ? "#6b7280" : color(a.data.label);
  }

  function toggle(d) {
    selected = d.data.id;
    if (d.data.children) expanded[d.data.id] = !d.children;
    render(true, d.data.id);
  }

  // ---- side panel ------------------------------------------------------------------------
  function showStudies(d) {
    var panel = root.querySelector(".tx-list");
    if (!d) { panel.innerHTML = ""; return; }
    var crumbs = d.ancestors().reverse().map(function (a) {
      return a.depth === 0 ? "All" : '<span class="tx-crumb-f">' + esc(byId[a.data.facet].label) + ":</span> " + esc(a.data.label);
    }).join(' <span class="tx-sep">›</span> ');
    var list = d.data.studies.slice().sort(function (a, b) { return (b.year || 0) - (a.year || 0); });
    panel.innerHTML = '<div class="tx-crumbs">' + crumbs + '</div><p class="tx-count">' + list.length + " studies</p><ol>" +
      list.map(function (s) {
        var t = esc(s.title);
        return "<li>" + (s.doi ? '<a href="https://doi.org/' + esc(s.doi) + '" target="_blank" rel="noopener">' + t + "</a>" : t) +
          ' <span class="tx-meta">' + esc(s.year || "") + (s.platform_name ? " · " + esc(s.platform_name) : "") +
          (s.n ? " · N = " + esc(s.n) : "") + (s.abstract_only ? " · abstract only" : "") + "</span></li>";
      }).join("") + "</ol>";
  }

  // ---- level controls ----------------------------------------------------------------------
  function controls() {
    var box = root.querySelector(".tx-levels");
    var chosen = levels.map(function (id, i) {
      return '<li class="tx-chip on" draggable="true" data-id="' + id + '"><span class="tx-grip" aria-hidden="true">⋮⋮</span>' +
        '<span class="tx-lvl">' + (i + 1) + "</span>" + esc(byId[id].label) +
        '<button type="button" data-act="up" aria-label="Move ' + esc(byId[id].label) + ' up"' + (i === 0 ? " disabled" : "") + ">↑</button>" +
        '<button type="button" data-act="down" aria-label="Move ' + esc(byId[id].label) + ' down"' + (i === levels.length - 1 ? " disabled" : "") + ">↓</button>" +
        '<button type="button" data-act="drop" aria-label="Remove ' + esc(byId[id].label) + '">×</button></li>';
    }).join("");
    var free = facets.filter(function (f) { return levels.indexOf(f.id) < 0; }).map(function (f) {
      return '<li><button type="button" class="tx-chip add" data-act="add" data-id="' + f.id + '">+ ' + esc(f.label) + "</button></li>";
    }).join("");
    box.innerHTML = '<div class="tx-row"><span class="tx-h">Search</span><input type="search" class="tx-search" placeholder="title, platform, phenomenon, theory… e.g. kilobot, hexbug, odd elastic" value="' + esc(query) + '" aria-label="Search the included studies"><span class="tx-hits"></span></div>' +
      '<div class="tx-row"><span class="tx-h">Levels</span><ol class="tx-chosen">' + chosen +
      '</ol></div><div class="tx-row"><span class="tx-h">Add</span><ul class="tx-free">' + free + "</ul>" +
      '<button type="button" class="tx-reset" data-act="reset">Reset</button> <button type="button" class="tx-reset" data-act="fold">Fold all</button></div>';

    box.querySelectorAll("[data-act]").forEach(function (b) {
      b.addEventListener("click", function () {
        var li = b.closest("[data-id]"), id = li ? li.getAttribute("data-id") : b.getAttribute("data-id"), i = levels.indexOf(id);
        var act = b.getAttribute("data-act");
        if (act === "up" && i > 0) levels.splice(i - 1, 0, levels.splice(i, 1)[0]);
        else if (act === "down" && i < levels.length - 1) levels.splice(i + 1, 0, levels.splice(i, 1)[0]);
        else if (act === "drop") { if (levels.length > 1) levels.splice(i, 1); }
        else if (act === "add") levels.push(b.getAttribute("data-id"));
        else if (act === "reset") { levels = DEFAULT.slice(); expanded = {}; }
        else if (act === "fold") expanded = {};
        changed();
      });
    });
    var search = box.querySelector(".tx-search"), timer = null;
    var onSearch = function () {
      if (search.value.trim() === query) return;
      clearTimeout(timer);
      timer = setTimeout(function () {
        query = search.value.trim();
        render(true);
        fit(true);
        hits();
      }, 220);
    };
    search.addEventListener("input", onSearch);
    search.addEventListener("keyup", onSearch);
    hits();
    // Drag to reorder.
    var dragId = null;
    box.querySelectorAll(".tx-chip.on").forEach(function (li) {
      li.addEventListener("dragstart", function (e) { dragId = li.getAttribute("data-id"); li.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
      li.addEventListener("dragend", function () { li.classList.remove("dragging"); });
      li.addEventListener("dragover", function (e) { e.preventDefault(); li.classList.add("over"); });
      li.addEventListener("dragleave", function () { li.classList.remove("over"); });
      li.addEventListener("drop", function (e) {
        e.preventDefault();
        var to = levels.indexOf(li.getAttribute("data-id")), from = levels.indexOf(dragId);
        if (from >= 0 && to >= 0 && from !== to) { levels.splice(to, 0, levels.splice(from, 1)[0]); changed(); }
      });
    });
  }

  function hits() {
    var el = root.querySelector(".tx-hits");
    if (el) el.textContent = query ? matching().length + " of " + data.studies.length + " studies" : "";
  }
  function changed() {
    writeHash();
    controls();
    render(true);
    fit(true);
  }

  // ---- pan and zoom ----------------------------------------------------------------------
  function fit(animate) {
    var box = svg.node().getBoundingClientRect();
    var k = Math.min(1.2, Math.max(0.25, Math.min((box.width - 24) / content.w, (box.height - 24) / content.h)));
    var tx = 12, ty = Math.max(12, (box.height - content.h * k) / 2);
    svg.transition().duration(animate ? DUR : 0).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
  }
  function nudge(dx, dy) { svg.transition().duration(250).call(zoom.translateBy, dx, dy); }
  function zoomBy(f) { svg.transition().duration(250).call(zoom.scaleBy, f); }

  // ---- boot ------------------------------------------------------------------------------
  fetch(root.getAttribute("data-src"), { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (d) {
      data = d;
      facets = d.facets;
      byId = {};
      facets.forEach(function (f) { byId[f.id] = f; });
      levels = readHash() || DEFAULT.slice();
      root.innerHTML = '<div class="tx-levels"></div><div class="tx-main"><div class="tx-canvas"><svg role="img" aria-label="Taxonomy tree"></svg>' +
        '<div class="tx-zoom" role="toolbar" aria-label="Move and zoom the tree">' +
        '<button type="button" data-z="in" title="Zoom in (+)">+</button><button type="button" data-z="out" title="Zoom out (−)">−</button>' +
        '<button type="button" data-z="fit" title="Fit the tree to the view (0)">⤢</button>' +
        '<span class="tx-pad"><button type="button" data-z="up" title="Move up">▲</button><button type="button" data-z="left" title="Move left">◀</button>' +
        '<button type="button" data-z="right" title="Move right">▶</button><button type="button" data-z="down" title="Move down">▼</button></span>' +
        '</div><p class="tx-hint">Drag to move · scroll or pinch to zoom</p></div>' +
        '<aside class="tx-list" aria-live="polite"></aside></div><p class="tx-muted tx-foot">Snapshot ' + esc(d.snapshot) + " · " +
        d.studies.length + " included studies · node size grows with the number of studies</p>";
      svg = d3.select(root).select("svg");
      zoomG = svg.append("g");
      var g = zoomG.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
      zoom = d3.zoom().scaleExtent([0.2, 3]).on("zoom", function (ev) { zoomG.attr("transform", ev.transform); });
      svg.call(zoom).on("dblclick.zoom", null);
      root.querySelectorAll("[data-z]").forEach(function (b) {
        b.addEventListener("click", function () {
          var z = b.getAttribute("data-z"), step = 120;
          if (z === "in") zoomBy(1.3); else if (z === "out") zoomBy(1 / 1.3); else if (z === "fit") fit(true);
          else if (z === "up") nudge(0, step); else if (z === "down") nudge(0, -step);
          else if (z === "left") nudge(step, 0); else if (z === "right") nudge(-step, 0);
        });
      });
      document.addEventListener("keydown", function (e) {
        var tag = e.target && e.target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
        if (e.key === "+" || e.key === "=") zoomBy(1.3); else if (e.key === "-") zoomBy(1 / 1.3); else if (e.key === "0") fit(true);
      });
      gLinks = g.append("g").attr("fill", "none");
      gNodes = g.append("g");
      color = d3.scaleOrdinal(["#003865", "#4f7cac", "#6f9fbf", "#5b8c85", "#8c6d8f", "#b08d57", "#3e6a8a", "#9db4c8", "#7a8b99", "#a8786b", "#56708a", "#8aa39b"]);
      controls();
      render(false);
      fit(false);
      var canvas = root.querySelector(".tx-canvas"), w = canvas.clientWidth, pending = false;
      var onResize = function () {
        var now = canvas.clientWidth;
        if (Math.abs(now - w) < 8 || pending) return;
        pending = true;
        window.requestAnimationFrame(function () { pending = false; w = canvas.clientWidth; render(false); });
      };
      if (window.ResizeObserver) new ResizeObserver(onResize).observe(canvas);
      else window.addEventListener("resize", onResize);
    })
    .catch(function (e) { root.innerHTML = '<p class="tx-muted">The taxonomy could not be loaded (' + esc(e.message) + ").</p>"; });
})();
