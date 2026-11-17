/* ReelReady Studio: Library (#library), Review (#review[/<export>]), Styles (#styles). No dependencies. */
(function () {
  "use strict";

  var GROUPS = ["Talking to camera", "B-roll", "Voice notes", "Photos", "Too short"];
  var GDESC = {
    "Talking to camera": "You, talking. These lead your reels.",
    "B-roll": "Shots without talking. Claude cuts to these.",
    "Voice notes": "Sound only. Good for scripts and voice-overs.",
    "Photos": "Stills for b-roll beats and covers.",
    "Too short": "Under 1.5 seconds, so they stay out of edits.",
    "Not sorted yet": "New, or left where they were (same name already in a folder)."
  };
  var KIND = { hook: "Hook title", lower_third: "Lower third", end_card: "End card", cta: "Call to action",
               post_caption: "Post caption", other: "Other text" };
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var S = { status: null, lib: null, libStamp: "", filter: "all", q: "", exports: [], cur: null, rv: null,
            dec: {}, trims: {}, swaps: {}, hook: null, sent: false, page: null, polls: {} };

  /* ---------------------------------------------------------------- helpers */
  function $(s, r) { return (r || document).querySelector(s); }
  function h(tag, a) {
    var e = document.createElement(tag), i, k;
    a = a || {};
    for (k in a) {
      if (!Object.prototype.hasOwnProperty.call(a, k) || a[k] == null || a[k] === false) continue;
      var v = a[k];
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k === "html") e.innerHTML = v;            /* only ever used with our own static SVG strings */
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else if (k === "style") e.style.cssText = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (i = 2; i < arguments.length; i++) add(e, arguments[i]);
    return e;
  }
  function add(e) {
    for (var i = 1; i < arguments.length; i++) {
      var kid = arguments[i];
      if (kid == null || kid === false) continue;
      if (Array.isArray(kid)) { kid.forEach(function (k) { add(e, k); }); continue; }
      e.appendChild(typeof kid === "string" || typeof kid === "number" ? document.createTextNode(String(kid)) : kid);
    }
  }
  function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }
  function api(path, opts) {
    return fetch(path, Object.assign({ cache: "no-store" }, opts || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { j.__status = r.status; return j; });
    });
  }
  function mediaUrl(rel) { return "/media/" + String(rel).split("/").map(encodeURIComponent).join("/"); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fmtDur(s) {
    s = Math.max(0, Math.round(+s || 0));
    var m = Math.floor(s / 60), hh = Math.floor(m / 60);
    return hh ? hh + ":" + pad(m % 60) + ":" + pad(s % 60) : m + ":" + pad(s % 60);
  }
  function fmtT(s) { s = Math.max(0, +s || 0); var m = Math.floor(s / 60); var r = (s - m * 60).toFixed(1); return m + ":" + (r < 10 ? "0" : "") + r; }
  function fmtDay(iso) {
    if (!iso) return null;
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  }
  function fmtSize(b) { if (!b) return "-"; return b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : (b / 1e6).toFixed(b > 1e7 ? 0 : 1) + " MB"; }
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || "null"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
  var toastT;
  function toast(msg) { var t = $("#toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(function () { t.classList.remove("on"); }, 3200); }
  function shuffle(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function gauss() { var u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }

  var ICON = {
    folder: '<svg viewBox="0 0 44 34" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 7.5A3.5 3.5 0 0 1 6.5 4h9l4 4.5h18A3.5 3.5 0 0 1 41 12v15.5a3.5 3.5 0 0 1-3.5 3.5h-31A3.5 3.5 0 0 1 3 27.5z"/><path d="M3 13h38" opacity=".35"/></svg>',
    search: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="7" r="5"/><path d="m11 11 3.5 3.5"/></svg>',
    check: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m3 8.5 3.2 3L13 4.5"/></svg>',
    play: '<svg width="11" height="11" viewBox="0 0 16 16"><path d="M4 2.5v11l9.5-5.5z" fill="currentColor"/></svg>',
    info: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 7.2v4.3M8 4.6v.1"/></svg>',
    send: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8h11M9 3.5 13.5 8 9 12.5"/></svg>'
  };

  /* ---------------------------------------------------------------- routing */
  function route() {
    var parts = location.hash.replace(/^#/, "").split("/");
    var page = ["library", "review", "styles"].indexOf(parts[0]) >= 0 ? parts[0] : "library";
    S.page = page;
    ["library", "review", "styles"].forEach(function (p) {
      $("#page-" + p).hidden = p !== page;
      var tab = $('.tabs a[data-tab="' + p + '"]');
      if (p === page) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current");
    });
    if (page !== "library" && S.stopStage) S.stopStage();
    if (page !== "review") { var sb = $(".sendbar"); if (sb) sb.remove(); }
    if (page === "styles") { var f = $("#styleFrame"); if (!f.getAttribute("src")) f.setAttribute("src", "/styleguide/"); }
    if (page === "library") loadLibrary(true);
    if (page === "review") loadReview(parts.length > 1 ? decodeURIComponent(parts.slice(1).join("/")) : null);
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  function poll(name, ms, fn) { clearTimeout(S.polls[name]); S.polls[name] = setTimeout(fn, ms); }

  /* ---------------------------------------------------------------- library */
  function loadLibrary(first) {
    return api("/api/library").then(function (lib) {
      var stamp = JSON.stringify([lib.updated, lib.sorting, lib.pending, (lib.last_batch || {}).id, (lib.items || []).length]);
      var changed = stamp !== S.libStamp;
      S.lib = lib; S.libStamp = stamp;
      if (S.page === "library") {
        var played = maybePlay(lib);
        if (!played && (changed || first)) renderLibrary(false);
        poll("lib", lib.sorting || lib.pending ? 2000 : 8000, function () { if (S.page === "library") loadLibrary(false); });
      }
      return lib;
    }).catch(function () { if (S.page === "library") poll("lib", 5000, function () { loadLibrary(false); }); });
  }

  function itemsIn(lib, g) {
    return (lib.items || []).filter(function (i) { return g === "Not sorted yet" ? !i.folder : i.folder === g; });
  }

  function renderLibrary(animate) {
    var lib = S.lib, root = clear($("#page-library"));
    if (!lib) return;
    if (!lib.configured) {
      add(root, emptyState("Not set up yet.", [h("p", { text: "Open Claude Code in the ReelReady folder and say: set up reelready." })]));
      return;
    }
    var items = lib.items || [];
    var batch = lib.last_batch && lib.last_batch.id;
    var head = h("div", { class: "head" },
      h("div", null, h("p", { class: "kicker" }, "Library"), h("h1", { id: "libTitle" }, "Your ", h("em", null, "footage")),
        h("p", { class: "sub", text: items.length ? items.length + " file" + (items.length === 1 ? "" : "s") + " in raw footage, sorted into folders." : "Everything in raw footage, sorted into folders." })),
      items.some(function (i) { return i.folder; }) && !reduce ?
        h("button", { class: "btn btn-ghost", type: "button", onclick: function () { playSort(items.filter(function (i) { return i.folder; }), true); } }, "Replay the sort") : null);
    add(root, head);
    if (lib.sorting) {
      var t = lib.sorting.total || 0, d = lib.sorting.done || 0;
      add(root, h("div", { class: "note" }, h("span", { class: "ic", html: ICON.folder.replace('viewBox="0 0 44 34"', 'viewBox="0 0 44 34" width="16" height="13"') }),
        h("div", { style: "flex:1" }, h("b", null, "Sorting your new clips…"), " " + (t ? d + " of " + t + " checked" : ""),
          h("div", { class: "bar" }, h("i", { style: "width:" + (t ? Math.round(100 * d / t) : 8) + "%" })))));
    } else if (lib.pending) {
      add(root, h("div", { class: "note" }, h("span", { class: "ic", html: ICON.info }),
        h("div", null, h("b", null, lib.pending + " new file" + (lib.pending === 1 ? " isn't" : "s aren't") + " sorted yet."),
          " They get sorted next time you open Claude, or say ", h("b", null, "sort my clips"), ".")));
    }
    if (!items.length) {
      add(root, emptyState("Nothing here yet.", [
        h("p", null, "Drop your phone clips into"), h("p", null, h("span", { class: "path", text: lib.raw_footage || "raw footage" })),
        h("p", { text: "Next time you open Claude they are sorted into folders here: talking clips, b-roll, voice notes and photos." })]));
      return;
    }
    var groups = GROUPS.concat(["Not sorted yet"]).filter(function (g) { return itemsIn(lib, g).length; });
    var pills = h("div", { class: "pills", role: "toolbar", "aria-label": "Show one folder" });
    [["all", "All", items.length]].concat(groups.map(function (g) { return [g, g, itemsIn(lib, g).length]; })).forEach(function (p) {
      add(pills, h("button", { class: "pill", type: "button", "aria-pressed": String(S.filter === p[0]),
        onclick: function () { S.filter = p[0]; renderLibrary(false); } }, p[1], h("span", null, String(p[2]))));
    });
    var q = h("input", { type: "search", placeholder: "Search by file name", "aria-label": "Search by file name", value: S.q, autocomplete: "off" });
    q.addEventListener("input", function () { S.q = q.value.trim(); renderGrid(gridBox, groups, batch, false); });
    add(root, h("div", { class: "toolbar" }, pills, h("label", { class: "search", html: ICON.search }, q)));
    var gridBox = h("div");
    add(root, gridBox);
    renderGrid(gridBox, groups, batch, animate);
  }

  function renderGrid(box, groups, batch, animate) {
    clear(box);
    var q = S.q.toLowerCase(), n = 0, shown = 0;
    groups.forEach(function (g) {
      if (S.filter !== "all" && S.filter !== g) return;
      var list = itemsIn(S.lib, g).filter(function (i) { return !q || i.name.toLowerCase().indexOf(q) >= 0; });
      if (!list.length) return;
      var grid = h("div", { class: "grid" });
      list.forEach(function (it) { var t = tile(it, batch); if (animate) { t.classList.add("in"); t.style.animationDelay = Math.min(n * 18, 700) + "ms"; } n++; add(grid, t); });
      shown += list.length;
      add(box, h("section", { class: "group", "aria-label": g },
        h("div", { class: "group-head" }, h("span", { class: "fold", html: ICON.folder }), h("h2", null, g),
          h("span", { class: "count", text: list.length + (list.length === 1 ? " file" : " files") }), h("p", { text: GDESC[g] || "" })), grid));
    });
    if (!shown) add(box, h("p", { class: "muted", style: "padding:30px 0", text: "Nothing matches that search." }));
  }

  function tile(it, batch, onpick) {
    var thumb = h("div", { class: "thumb" });
    if (it.thumb) add(thumb, h("img", { src: mediaUrl(it.thumb), alt: "", loading: "lazy", decoding: "async" }));
    else add(thumb, h("div", { class: "ph", text: it.kind === "photo" ? "Photo" : "No preview" }));
    if (it.kind !== "photo" && it.duration != null) add(thumb, h("span", { class: "chip dark dur", text: fmtDur(it.duration) }));
    if (batch && it.batch === batch) add(thumb, h("span", { class: "chip acc new", text: "New" }));
    var chips = h("div", { class: "chips" });
    if (it.orientation) add(chips, h("span", { class: "chip", text: it.orientation.charAt(0).toUpperCase() + it.orientation.slice(1) }));
    if (it.shoot_day) add(chips, h("span", { class: "chip", text: fmtDay(it.shoot_day), title: "Shot on (from " + (it.day_from || "file") + ")" }));
    return h("button", { class: "tile", type: "button", title: it.name, onclick: function () { (onpick || openViewer)(it); } },
      thumb, h("div", { class: "meta" }, h("span", { class: "name", text: it.name }), chips));
  }

  function emptyState(big, kids) {
    return h("div", { class: "empty" }, h("span", { class: "empty-art", html: ICON.folder }), h("p", { class: "big", text: big }), kids);
  }

  function openViewer(it) {
    var d = $("#viewer"), media;
    var src = mediaUrl(it.path);
    if (it.kind === "video") media = h("video", { src: src, controls: true, playsinline: true, preload: "metadata", autoplay: true });
    else if (it.kind === "audio") media = h("audio", { src: src, controls: true, preload: "metadata" });
    else media = h("img", { src: src, alt: it.name, onerror: function () { if (it.thumb) media.src = mediaUrl(it.thumb); } });
    var fact = function (k, v) { return v == null ? null : h("div", { class: "fact" }, h("small", null, k), h("span", null, String(v))); };
    clear(d);
    add(d, h("div", { class: "dlg" }, h("div", { class: "dlg-media" }, media),
      h("div", { class: "dlg-main" },
        h("div", { class: "dlg-top" }, h("span", { class: "chip", text: it.folder || "Not sorted yet" }),
          h("button", { class: "dlg-close", type: "button", "aria-label": "Close", onclick: function () { d.close(); } }, "×")),
        h("h2", { text: it.name }),
        h("div", { class: "facts" },
          fact("Length", it.kind === "photo" ? null : fmtDur(it.duration)),
          fact("Shape", it.orientation ? it.orientation + (it.width ? " " + it.width + "×" + it.height : "") : null),
          fact("Shot on", fmtDay(it.shoot_day)),
          fact("Talking", it.kind === "video" && (it.duration || 0) >= 1.5 ? (it.speech ? "Yes" : "No") : null),
          fact("Size", fmtSize(it.size))),
        h("p", { class: "muted", text: "Why this folder: " + (it.reason || "-") }),
        h("p", { class: "muted" }, "In ", h("span", { class: "path", text: it.path })))));
    d.addEventListener("close", function () { if (media.pause) media.pause(); }, { once: true });
    d.showModal();
  }

  /* ---------------------------------------------------------------- the sort moment */
  function seenBatch(id) { if (id) { S.seen = id; store("reelready.studio.seenBatch", id); } return S.seen || store("reelready.studio.seenBatch"); }

  function maybePlay(lib) {
    var b = lib.last_batch;
    if (!b || !b.moved || seenBatch() === b.id) return false;
    seenBatch(b.id);
    if (reduce) return false;
    var moved = (lib.items || []).filter(function (i) { return i.batch === b.id && i.folder; });
    if (!moved.length) return false;
    playSort(moved, false);
    return true;
  }

  function playSort(items, replay) {
    var stage = $("#stage"), CAP = window.innerWidth < 640 ? 160 : 360;
    var fly = shuffle(items.slice()).slice(0, CAP);
    var small = window.innerWidth < 640, fw = small ? 46 : (fly.length > 160 ? 58 : 72), fh = fw * 1.25;
    var total = {}; GROUPS.forEach(function (g) { total[g] = 0; });
    items.forEach(function (i) { if (total[i.folder] != null) total[i.folder]++; });
    var counts = {}; GROUPS.forEach(function (g) { counts[g] = 0; });
    clear(stage); stage.hidden = false; stage.classList.remove("out");
    document.body.style.overflow = "hidden";
    var title = h("h1", null, "Sorting my ", h("em", null, "raw footage"));
    var countLine = h("p", { class: "stage-count" }, h("b", null, String(items.length)), " file" + (items.length === 1 ? "" : "s") + " in the pile");
    var pile = h("div", { class: "pile" });
    var folders = h("div", { class: "folders" }), tiles = {};
    GROUPS.forEach(function (g) {
      var n = h("span", { class: "n", text: "0" });
      tiles[g] = { el: h("div", { class: "folder" }, h("span", { class: "fold-ic", html: ICON.folder }), h("span", { class: "lbl", text: g }), n), n: n };
      add(folders, tiles[g].el);
    });
    var done = false, anims = [];
    S.stopStage = function () {
      done = true; S.stopStage = null;
      anims.forEach(function (a) { try { a.cancel(); } catch (e) {} });
      stage.hidden = true; clear(stage); document.body.style.overflow = "";
    };
    var skip = h("button", { class: "btn btn-ghost", type: "button", onclick: function () { finish(true); } }, "Skip");
    add(stage, h("div", { class: "grain", "aria-hidden": "true" }),
      h("div", { class: "stage-head" }, h("p", { class: "kicker", text: replay ? "Replay" : "Just now" }), title, countLine),
      pile, folders, h("div", { class: "stage-foot" }, skip));

    function finish(skipped) {
      if (done) return; done = true; S.stopStage = null;
      anims.forEach(function (a) { try { a.cancel(); } catch (e) {} });
      clear(pile);
      GROUPS.forEach(function (g) { tiles[g].n.textContent = String(total[g]); tiles[g].el.classList.toggle("done", total[g] > 0); });
      clear(title); add(title, h("em", null, "Sorted."));
      clear(countLine); add(countLine, h("b", null, String(items.length)), " file" + (items.length === 1 ? "" : "s") + " into " + GROUPS.filter(function (g) { return total[g]; }).length + " folders");
      skip.textContent = "See the library";
      skip.onclick = leave;
      var t = setTimeout(leave, skipped ? 500 : 1300);
      function leave() {
        clearTimeout(t);
        stage.classList.add("out");
        setTimeout(function () { stage.hidden = true; clear(stage); document.body.style.overflow = ""; renderLibrary(true); }, 450);
      }
    }

    var imgs = fly.map(function (it) { return it.thumb ? mediaUrl(it.thumb) : null; });
    var loads = imgs.map(function (src) {
      return new Promise(function (res) { if (!src) return res(); var im = new Image(); im.onload = im.onerror = res; im.src = src; });
    });
    var timeout = new Promise(function (res) { setTimeout(res, 1500); });
    Promise.race([Promise.all(loads), timeout]).then(function () { requestAnimationFrame(start); });

    function start() {
      if (done) return;
      var pr = pile.getBoundingClientRect();
      var W = pr.width, H = Math.max(pr.height, 160);
      var DROP = 420, HOLD = 260, WINDOW = 1250, FLY = 650;
      var cards = fly.map(function (it, i) {
        var c = h("div", { class: "flyer" + (it.kind === "audio" ? " audio" : ""), style: "--fw:" + fw + "px" });
        if (imgs[i]) add(c, h("img", { src: imgs[i], alt: "" }));
        var x = W / 2 + gauss() * W * (small ? .18 : .2) - fw / 2, y = H * .48 + gauss() * H * .16 - fh / 2;
        x = Math.max(4, Math.min(W - fw - 4, x)); y = Math.max(4, Math.min(H - fh - 4, y));
        var r = (Math.random() * 2 - 1) * 26;
        add(pile, c);
        return { el: c, it: it, x: x, y: y, r: r };
      });
      cards.forEach(function (c, i) {
        var a = c.el.animate([
          { opacity: 0, transform: "translate(" + c.x + "px," + (c.y - 50) + "px) rotate(" + c.r + "deg) scale(1.15)" },
          { opacity: 1, transform: "translate(" + c.x + "px," + c.y + "px) rotate(" + c.r + "deg) scale(1)" }
        ], { duration: 380, delay: i * (DROP - 380 > 0 ? (DROP - 200) / cards.length : 0), easing: "cubic-bezier(.2,.8,.2,1)", fill: "both" });
        anims.push(a);
      });
      setTimeout(function () {
        if (done) return;
        var pr2 = pile.getBoundingClientRect();
        var finished = 0;
        cards.forEach(function (c, i) {
          var fr = tiles[c.it.folder].el.getBoundingClientRect();     /* FLIP: measure the last position, play the inverse */
          var tx = fr.left - pr2.left + fr.width / 2 - fw / 2 + (Math.random() * 2 - 1) * fr.width * .12;
          var ty = fr.top - pr2.top + fr.height * .32 - fh / 2;
          var mx = (c.x + tx) / 2, my = Math.min(c.y, ty) - 70 - Math.random() * 40;
          var a = c.el.animate([
            { transform: "translate(" + c.x + "px," + c.y + "px) rotate(" + c.r + "deg) scale(1)", opacity: 1 },
            { transform: "translate(" + mx + "px," + my + "px) rotate(" + (c.r / 3) + "deg) scale(.82)", opacity: 1, offset: .5 },
            { transform: "translate(" + tx + "px," + ty + "px) rotate(0deg) scale(.34)", opacity: 1, offset: .86 },
            { transform: "translate(" + tx + "px," + (ty + 10) + "px) rotate(0deg) scale(.22)", opacity: 0 }
          ], { duration: FLY, delay: i * WINDOW / cards.length, easing: "cubic-bezier(.45,.05,.2,1)", fill: "both" });
          anims.push(a);
          a.onfinish = function () {
            if (done) return;
            counts[c.it.folder]++;
            var t = tiles[c.it.folder];
            t.n.textContent = String(counts[c.it.folder]);
            t.el.classList.add("bump");
            clearTimeout(t.timer); t.timer = setTimeout(function () { t.el.classList.remove("bump"); }, 140);
            if (++finished === cards.length) setTimeout(function () { finish(false); }, 200);
          };
        });
      }, DROP + HOLD);
    }
  }

  /* ---------------------------------------------------------------- review */
  function loadExports() {
    return api("/api/exports").then(function (r) {
      S.exports = r.exports || [];
      $("#reviewDot").hidden = !S.exports.some(function (e) { return e.waiting; });
      return S.exports;
    }).catch(function () { return S.exports; });
  }

  function loadReview(name) {
    if (!S.lib) loadLibrary(false);
    loadExports().then(function (list) {
      if (!name) {
        var w = list.filter(function (e) { return e.waiting; })[0] || list[0];
        name = w ? w.name : null;
      }
      if (!name) { S.cur = null; S.rv = null; renderReview(); return; }
      if (S.cur === name && S.rv) { renderReview(); return; }
      api("/api/review/" + encodeURIComponent(name)).then(function (d) {
        if (d.__status !== 200) { S.cur = null; S.rv = null; renderReview(name); return; }
        S.cur = name; S.rv = d; initReview(d); renderReview();
      });
    });
    poll("exports", 6000, function again() {
      if (S.page !== "review") return;
      loadExports().then(function (list) { if (S.page === "review" && !S.rv && list.length) loadReview(null); });
      poll("exports", 6000, again);
    });
  }

  function draftKey() { return "reelready.review." + S.cur + "." + (S.rv.request.requested_at || ""); }

  function initReview(d) {
    var req = d.request, saved = d.review || store(draftKeyFor(d)) || {};
    S.sent = !!d.review;
    S.dec = JSON.parse(JSON.stringify(saved.decisions || {}));
    S.hook = saved.hook || ((req.hook_options || []).length === 1 ? req.hook_options[0].id : null);
    S.trims = {}; S.swaps = {};
    (req.cuts || []).forEach(function (c, i) { S.trims[i] = { start: +c.start, end: +c.end }; });
    (saved.trims || []).forEach(function (t) { if (S.trims[t.cut]) S.trims[t.cut] = { start: +t.start, end: +t.end }; });
    (saved.swaps || []).forEach(function (s) { S.swaps[s.cut] = s.library_item; });
  }
  function draftKeyFor(d) { return "reelready.review." + d.export + "." + (d.request.requested_at || ""); }
  function saveDraft() {
    if (S.sent || !S.rv) return;
    store(draftKey(), { decisions: S.dec, hook: S.hook, trims: trimList(), swaps: swapList() });
  }
  function trimList() {
    return (S.rv.request.cuts || []).map(function (c, i) {
      var t = S.trims[i];
      return Math.abs(t.start - c.start) > 1e-6 || Math.abs(t.end - c.end) > 1e-6 ? { cut: i, start: +t.start.toFixed(2), end: +t.end.toFixed(2) } : null;
    }).filter(Boolean);
  }
  function swapList() {
    return Object.keys(S.swaps).map(function (k) { return { cut: +k, library_item: S.swaps[k] }; });
  }

  function problems() {
    var req = S.rv.request, out = [], items = req.generated || [], undecided = 0;
    items.forEach(function (it) {
      var d = S.dec[it.id];
      if (!d || !d.action) undecided++;
      else if (d.action === "edit" && !(d.text || "").trim()) out.push("“" + (KIND[it.kind] || "Text") + "” needs your new words");
    });
    if (undecided) out.unshift(undecided + " of " + items.length + " line" + (items.length === 1 ? "" : "s") + " still need a yes, an edit or a no");
    var hooks = req.hook_options || [];
    if (hooks.length) {
      var hk = hooks.filter(function (x) { return x.id === S.hook; })[0];
      if (!hk) out.push("Pick hook " + hooks.map(function (x) { return x.id; }).join(" or "));
      else if (hk.source === "generated" && (S.dec[hk.item_id] || {}).action === "reject") out.push("Hook " + hk.id + " uses a line you rejected");
    }
    return out;
  }

  function renderReview(missing) {
    var root = clear($("#page-review"));
    add(root, h("div", { class: "head" }, h("div", null, h("p", { class: "kicker" }, "Review"),
      h("h1", { id: "revTitle" }, "Check it, then ", h("em", null, "send it")),
      h("p", { class: "sub", text: "Nothing is rendered until you have said yes, changed or said no to every line Claude wrote. Your captions stay word for word." }))));
    if (S.exports.length) {
      var ex = h("div", { class: "exports", role: "group", "aria-label": "Edits to review" });
      S.exports.forEach(function (e) {
        add(ex, h("button", { class: "exp", type: "button", "aria-pressed": String(e.name === S.cur), onclick: function () { location.hash = "#review/" + encodeURIComponent(e.name); } },
          h("span", null, e.title, h("small", { text: e.waiting ? "Waiting for you" : "Approved" })),
          e.waiting ? h("span", { class: "chip acc", text: "New" }) : null));
      });
      add(root, ex);
    }
    var sb = $(".sendbar"); if (sb) sb.remove();
    if (!S.rv) {
      add(root, emptyState(missing ? "That edit isn't waiting for a review." : "Nothing to review yet.", [
        h("p", { text: "When Claude plans an edit, it shows up here: the draft, every cut, and each line Claude wrote, for you to approve before anything renders." })]));
      return;
    }
    var d = S.rv, req = d.request;
    if ((d.problems || []).length) add(root, h("div", { class: "note" }, h("span", { class: "ic", html: ICON.info }), h("div", null, h("b", null, "This review file has a problem: "), d.problems.join("; "))));
    if (S.sent) add(root, h("div", { class: "note dark" }, h("span", { class: "ic", html: ICON.check }),
      h("div", null, h("b", null, "You approved this" + (d.review.approved_at ? " at " + new Date(d.review.approved_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "") + "."),
        " Claude is rendering it. Want a change now? Tell Claude in the chat.")));
    var left = h("div"), right = h("div");
    add(root, h("h2", { style: "margin:0 0 16px", text: req.title || d.export }));
    add(root, h("div", { class: "rv" }, left, right));
    renderPlayer(left, d);
    renderRight(right, d);
    add(document.body, sendbar());
  }

  /* ----- left: draft player, cut markers, cuts */
  function renderPlayer(box, d) {
    var req = d.request, cuts = req.cuts || [];
    var total = cuts.length ? Math.max.apply(null, cuts.map(function (c) { return +c.draft_end || 0; })) : 0;
    var video = d.draft_url ? h("video", { src: d.draft_url, controls: true, playsinline: true, preload: "metadata" }) : null;
    var screen = h("div", { class: "screen" }, video || h("p", { class: "noplay", text: "The draft video isn't where the review file says it is." }));
    var tl = h("div", { class: "timeline", role: "slider", "aria-label": "Draft timeline with cut markers", tabindex: "0", "aria-valuemin": "0", "aria-valuemax": String(Math.round(total)) });
    var headEl = h("span", { class: "head" });
    /* talking cuts sit end to end; b-roll cutaways are laid over them, so they float on top at their own time */
    var segs = cuts.map(function (c, i) {
      var len = Math.max(.05, (+c.draft_end || 0) - (+c.draft_start || 0)), br = c.kind === "broll";
      var s = h("button", { class: "seg" + (br ? " broll" : ""), type: "button", title: "Cut " + (i + 1) + ": " + (c.label || ""),
        style: br ? "position:absolute;top:0;height:50%;left:" + (+c.draft_start / (total || 1) * 100) + "%;width:" + (len / (total || 1) * 100) + "%;border-radius:0 0 6px 6px"
                  : "flex:" + len + " 1 0",
        onclick: function (e) { e.stopPropagation(); seek(+c.draft_start + .01); } }, String(i + 1));
      add(tl, s);
      return s;
    });
    add(tl, headEl);
    tl.addEventListener("click", function (e) { var r = tl.getBoundingClientRect(); seek((e.clientX - r.left) / r.width * (video && video.duration || total)); });
    function seek(t) { if (video && isFinite(t)) { video.currentTime = Math.max(0, t); } }
    var rows = [];
    function tick() {
      if (!video) return;
      var dur = video.duration || total || 1, t = video.currentTime;
      headEl.style.left = Math.min(100, t / dur * 100) + "%";
      tl.setAttribute("aria-valuenow", String(Math.round(t)));
      cuts.forEach(function (c, i) {
        var on = t >= +c.draft_start && t < +c.draft_end;
        segs[i].classList.toggle("on", on);
        if (rows[i]) rows[i].classList.toggle("on", on);
      });
    }
    if (video) { video.addEventListener("timeupdate", tick); video.addEventListener("seeked", tick); video.addEventListener("loadedmetadata", tick); }
    var playerPanel = h("div", { class: "panel player" }, screen,
      cuts.length ? tl : null,
      cuts.length ? h("div", { class: "tl-legend" }, h("span", null, "0:00"), h("span", null, cuts.length + " cuts · striped = b-roll"), h("span", null, fmtDur(total))) : null);
    add(box, playerPanel);
    var cutPanel = h("div", { class: "panel" }, h("div", { class: "panel-head" }, h("h3", null, "Cuts"),
      h("span", { class: "count", text: cuts.length ? "Trim a cut, or swap a b-roll shot" : "" })));
    if (!cuts.length) add(cutPanel, h("p", { class: "muted", text: "No cut list in this review." }));
    var list = h("div", { class: "cuts" });
    cuts.forEach(function (c, i) { var r = cutRow(c, i, seek); rows.push(r); add(list, r); });
    add(cutPanel, list);
    add(box, cutPanel);
  }

  function cutRow(c, i, seek) {
    var lo = +c.bounds[0], hi = +c.bounds[1], t = S.trims[i], MIN = .3;
    var row = h("div", { class: "cut" });
    var sV = h("b"), eV = h("b"), sel = h("span", { class: "sel" }), orig = h("span", { class: "orig" });
    var rs = h("input", { type: "range", min: String(lo), max: String(hi), step: "0.1", value: String(t.start), "aria-label": "Cut " + (i + 1) + " start", disabled: S.sent || null });
    var re = h("input", { type: "range", min: String(lo), max: String(hi), step: "0.1", value: String(t.end), "aria-label": "Cut " + (i + 1) + " end", disabled: S.sent || null });
    var foot = h("div", { class: "cut-foot" });
    function pct(v) { return hi > lo ? (v - lo) / (hi - lo) * 100 : 0; }
    function set(start, end) {
      start = Math.round(Math.max(lo, Math.min(start, hi - MIN)) * 100) / 100;
      end = Math.round(Math.min(hi, Math.max(end, start + MIN)) * 100) / 100;
      t.start = start; t.end = end;
      sync(); saveDraft(); updateSendbar();
    }
    function sync() {
      sV.textContent = fmtT(t.start); eV.textContent = fmtT(t.end);
      rs.value = String(t.start); re.value = String(t.end);
      sel.style.left = pct(t.start) + "%"; sel.style.width = (pct(t.end) - pct(t.start)) + "%";
      orig.style.left = pct(+c.start) + "%"; orig.style.width = (pct(+c.end) - pct(+c.start)) + "%";
      clear(foot);
      var changed = Math.abs(t.start - c.start) > 1e-6 || Math.abs(t.end - c.end) > 1e-6;
      add(foot, h("span", { class: "muted", text: (t.end - t.start).toFixed(1) + " s" + (changed ? " · was " + fmtT(c.start) + "–" + fmtT(c.end) : "") }));
      if (changed && !S.sent) add(foot, h("button", { class: "linkbtn", type: "button", onclick: function () { set(+c.start, +c.end); } }, "Undo trim"));
      if (c.kind === "broll" && !S.sent) add(foot, h("button", { class: "btn btn-ghost", type: "button", style: "margin-left:auto;padding:8px 12px;font-size:13px", onclick: function () { pickShot(i, row); } }, S.swaps[i] ? "Change shot" : "Swap shot"));
      var old = row.querySelector(".swap"); if (old) old.remove();
      if (S.swaps[i]) {
        var sw = S.swaps[i];
        add(row, h("div", { class: "swap" }, sw.thumb ? h("img", { src: mediaUrl(sw.thumb), alt: "" }) : null,
          h("span", { text: "Swapped for " + (sw.name || sw.path) }),
          S.sent ? null : h("button", { class: "linkbtn", type: "button", onclick: function () { delete S.swaps[i]; sync(); saveDraft(); } }, "Undo")));
      }
    }
    rs.addEventListener("input", function () { set(+rs.value, t.end); });
    re.addEventListener("input", function () { set(t.start, +re.value); });
    function nudge(which, dv) { return h("button", { type: "button", "aria-label": (dv < 0 ? "Earlier " : "Later ") + which, disabled: S.sent || null,
      onclick: function () { if (which === "start") set(t.start + dv, t.end); else set(t.start, t.end + dv); } }, dv < 0 ? "−" : "+"); }
    add(row,
      h("div", { class: "cut-top" }, h("span", { class: "cut-n", text: String(i + 1) }), h("span", { class: "cut-label", text: c.label || c.source || "" }),
        h("span", { class: "chip", text: c.kind === "broll" ? "B-roll" : "Talking" }),
        h("button", { class: "chip", type: "button", style: "cursor:pointer", onclick: function () { seek(+c.draft_start + .01); }, "aria-label": "Play cut " + (i + 1) },
          h("span", { html: ICON.play }), fmtT(c.draft_start))),
      c.says ? h("p", { class: "cut-says", text: c.says }) : null,
      h("div", { class: "trim" },
        h("span", { class: "nudge" }, "Start", nudge("start", -.1), sV, nudge("start", .1)),
        h("div", { class: "range" }, h("span", { class: "track" }), orig, sel, rs, re),
        h("span", { class: "nudge" }, "End", nudge("end", -.1), eV, nudge("end", .1))),
      foot);
    sync();
    return row;
  }

  function pickShot(i, row) {
    var d = $("#picker"), lib = S.lib || { items: [] };
    var shots = (lib.items || []).filter(function (it) { return it.kind === "video" && (it.folder === "B-roll" || (!it.folder && it.group === "B-roll")); });
    var grid = h("div", { class: "pick-grid" });
    shots.forEach(function (it) {
      var t = tile(it, null, function () {
        S.swaps[i] = { id: it.id, path: it.path, name: it.name, thumb: it.thumb, duration: it.duration };
        d.close(); saveDraft(); renderReview();
      });
      if (S.swaps[i] && S.swaps[i].id === it.id) t.setAttribute("aria-pressed", "true");
      add(grid, t);
    });
    clear(d);
    add(d, h("div", { class: "pick" },
      h("div", { class: "dlg-top" }, h("h2", { style: "font-size:28px" }, "Swap shot ", (i + 1)),
        h("button", { class: "dlg-close", type: "button", "aria-label": "Close", onclick: function () { d.close(); } }, "×")),
      h("p", { class: "muted", style: "margin:0", text: shots.length ? "Pick a b-roll shot from your library. Claude re-renders only this part." : "No b-roll in your library yet. Drop shots in raw footage and they'll be sorted into B-roll." }),
      grid));
    d.showModal();
  }

  /* ----- right: hook A/B, generated lines, caption fixes, brand choices */
  function renderRight(box, d) {
    var req = d.request, hooks = req.hook_options || [], items = req.generated || [];
    if (hooks.length) {
      var hk = h("div", { class: "hooks", role: "radiogroup", "aria-label": "Pick the hook" });
      hooks.forEach(function (o) {
        var gen = o.source === "generated";
        add(hk, h("button", { class: "hook", type: "button", role: "radio", "aria-checked": String(S.hook === o.id), disabled: S.sent || null,
          onclick: function () { S.hook = o.id; saveDraft(); renderReview(); } },
          h("span", { class: "hl" }, h("span", { class: "ab", text: o.id }), h("span", { class: "chip" + (gen ? "" : " acc"), text: gen ? "Written by Claude" : "Your words" })),
          h("q", { text: o.text }), o.note ? h("span", { class: "muted", text: o.note }) : null));
      });
      add(box, h("div", { class: "panel" }, h("div", { class: "panel-head" }, h("h3", null, "Pick the hook"), h("span", { class: "count", text: "The first 2 seconds" })), hk));
    }
    var decided = items.filter(function (it) { return S.dec[it.id] && S.dec[it.id].action; }).length;
    var ip = h("div", { class: "panel" }, h("div", { class: "panel-head" }, h("h3", null, "Lines Claude wrote"),
      h("span", { class: "count", text: items.length ? decided + " of " + items.length + " decided" : "" })));
    if (!items.length) add(ip, h("p", { class: "muted", text: "Claude didn't write any words for this one. Everything on screen is what you said." }));
    items.forEach(function (it) { add(ip, itemCard(it)); });
    add(box, ip);
    var fixes = req.caption_corrections || [];
    add(box, h("div", { class: "panel" }, h("div", { class: "panel-head" }, h("h3", null, "Caption fixes"), h("span", { class: "count", text: "Read only" })),
      fixes.length ? h("ul", { class: "list" }, fixes.map(function (f) {
        return h("li", { class: "fix" }, "Heard ", h("s", { text: f.heard || f.from || "" }), ", you said ", h("b", { text: f.said || f.to || "" }), f.at != null ? " (" + fmtT(f.at) + ")" : "");
      })) : h("p", { class: "muted", text: "None. Your captions are exactly what you said." })));
    var brand = req.brand_choices || [];
    if (brand.length) add(box, h("div", { class: "panel" }, h("div", { class: "panel-head" }, h("h3", null, "Brand choices")),
      h("ul", { class: "list" }, brand.map(function (b) { return h("li", { text: typeof b === "string" ? b : (b.text || JSON.stringify(b)) }); }))));
  }

  function itemCard(it) {
    var d = S.dec[it.id] || {}, act = d.action;
    var card = h("div", { class: "item" + (act === "approve" ? " approved" : act === "edit" ? " edited" : act === "reject" ? " rejected" : "") });
    var shown = act === "edit" && (d.text || "").trim() ? d.text : it.text;
    function choose(a) {
      if (S.sent) return;
      var cur = S.dec[it.id] || {};
      S.dec[it.id] = a === "edit" ? { action: "edit", text: cur.text != null && cur.action === "edit" ? cur.text : it.text } : { action: a };
      saveDraft();
      var fresh = itemCard(it); card.replaceWith(fresh);
      updateSendbar(); refreshCount();
      if (a === "edit") { var ta = fresh.querySelector("textarea"); if (ta) { ta.focus(); ta.select(); } }
    }
    function seg(a, label, cls) {
      return h("button", { class: cls, type: "button", "aria-pressed": String(act === a), disabled: S.sent || null, onclick: function () { choose(a); } },
        a === "approve" ? h("span", { html: ICON.check }) : null, label);
    }
    add(card, h("div", { class: "item-top" }, h("span", { class: "item-kind", text: KIND[it.kind] || "Text" }),
      h("span", { class: "chip", text: act === "edit" ? "Your edit" : "Written by Claude" }),
      it.where || it.when ? h("span", { class: "item-when", text: [it.when, it.where].filter(Boolean).join(" · ") }) : null),
      h("p", { class: "item-text", text: shown }));
    if (act === "edit" && !S.sent) {
      var ta = h("textarea", { "aria-label": "New words for " + (KIND[it.kind] || "this line"), rows: "2" });
      ta.value = d.text || "";
      ta.addEventListener("input", function () { S.dec[it.id].text = ta.value; card.querySelector(".item-text").textContent = ta.value.trim() ? ta.value : it.text; saveDraft(); updateSendbar(); });
      add(card, ta);
    }
    add(card, h("div", { class: "seg3" }, seg("approve", "Approve", "ap"), seg("edit", "Edit", "ed"), seg("reject", "Reject", "rj")));
    return card;
  }
  function refreshCount() {
    var items = S.rv.request.generated || [];
    var n = items.filter(function (it) { return S.dec[it.id] && S.dec[it.id].action; }).length;
    var el = Array.prototype.filter.call(document.querySelectorAll("#page-review .panel-head"), function (x) { return /Lines Claude wrote/.test(x.textContent); })[0];
    if (el) el.querySelector(".count").textContent = n + " of " + items.length + " decided";
  }

  function sendbar() {
    var bar = h("div", { class: "sendbar" + (S.sent ? " sent" : ""), role: "region", "aria-label": "Send to Claude" });
    var msg = h("div", { class: "msg", "aria-live": "polite" });
    var btn = h("button", { class: "btn btn-accent", type: "button", onclick: send }, h("span", { html: ICON.send }), "Approve and render");
    add(bar, msg, S.sent ? null : btn);
    bar._msg = msg; bar._btn = btn;
    setTimeout(updateSendbar, 0);
    return bar;
  }
  function updateSendbar() {
    var bar = $(".sendbar"); if (!bar || !S.rv) return;
    clear(bar._msg);
    if (S.sent) { add(bar._msg, h("b", null, "Sent."), h("span", null, "Claude is rendering.")); return; }
    var p = problems();
    bar._btn.disabled = p.length > 0;
    if (p.length) add(bar._msg, h("b", null, "Almost."), h("span", { text: p.join(" · ") }));
    else add(bar._msg, h("b", null, "Ready."), h("span", { text: "Claude renders exactly what you approved." }));
  }
  function send() {
    if (problems().length || S.sent) return;
    var bar = $(".sendbar"); bar._btn.disabled = true;
    var body = { decisions: S.dec, trims: trimList(), swaps: swapList(), hook: S.hook };
    api("/api/review/" + encodeURIComponent(S.cur), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) {
        if (r.__status === 200 && r.ok) {
          store(draftKey(), null);
          S.sent = true; S.rv.review = r.review;
          loadExports().then(function () { renderReview(); });
          toast("Sent. Claude is rendering.");
        } else {
          bar._btn.disabled = false;
          toast((r.errors || [r.error || "Couldn't send. Is Claude's Studio still running?"]).join(" · "));
        }
      }).catch(function () { bar._btn.disabled = false; toast("Couldn't reach the Studio. Is it still running?"); });
  }

  /* ---------------------------------------------------------------- boot */
  ["viewer", "picker"].forEach(function (id) { var d = document.getElementById(id); d.addEventListener("click", function (e) { if (e.target === d) d.close(); }); });
  api("/api/status").then(function (st) {
    S.status = st;
    var name = st.brand && st.brand.name;
    if (name) { document.querySelectorAll('[data-brand="name"]').forEach(function (n) { n.textContent = name; }); document.title = name + " Studio"; }
    $("#reviewDot").hidden = !st.waiting_review;
  }).catch(function () {});
  if (!location.hash) history.replaceState(null, "", "#library");
  route();
  setInterval(function () { if (S.page !== "review") loadExports(); }, 15000);
})();
