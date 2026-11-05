// The work-items page's script: views, filters, search, focus, copy, and the URL.
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement, PREF = "aidd-viewer:single-key-shortcuts", TOP = ["needs-you", "board", "tree"];
  const box = $("[data-testid=search-input]"), say = (t, id = "copy-status") => { $(`[data-testid=${id}]`).textContent = t; };
  const DEF = {view: "needs-you", team: "", columns: "steps", rows: "one", intent: "", open: [], item: "", q: ""};
  const known = {
    view: (v) => [...TOP, "item", "search", "keys"].includes(v),
    team: (v) => $$("[data-set]").some((b) => b.dataset.set === "team=" + v),
    columns: (v) => /^(steps|groups)$/.test(v), rows: (v) => /^(one|team)$/.test(v),
    intent: (v) => $$("[data-testid=intent-filter] option").some((o) => o.value === v),
  };
  let st = {...DEF}, stack = [], selId = "", keysOn = true;
  try { keysOn = localStorage.getItem(PREF) !== "off"; } catch (e) {}
  root.classList.add("js");
  const fold = (s) => s.normalize("NFKD").replace(/\p{M}/gu, "").replace(/[đĐ]/g, "d").toLowerCase();
  const shown = (e) => e.getClientRects().length > 0;
  const visible = (s) => $$(s).filter(shown);
  const idOf = (r) => r.dataset.need || r.dataset.card || r.dataset.leaf || r.dataset.result;

  const p = new URLSearchParams(location.search);
  for (const k in DEF) {
    const v = k === "open" ? p.getAll(k).filter((o) => $$("[data-toggle]").some((b) => b.dataset.toggle === o)) : k === "team" ? (p.get(k) || "").toLowerCase() : p.get(k);
    if (v && (!known[k] || known[k](v))) st[k] = v;
  }
  if (!p.has("view") && st.item) st.view = "item";
  if (st.view === "item" && !$(`section[data-item="${CSS.escape(st.item)}"]`)) st.view = "needs-you";

  const rows = () => visible({"needs-you": "[data-need]", board: "[data-card]", tree: "[data-leaf]", search: "li[data-result]"}[st.view] || "x-");
  function mark(r, q) {
    const t = $("[data-title]", r), orig = t.dataset.orig || (t.dataset.orig = t.textContent), cps = [...orig], at = [];
    let f = "";
    cps.forEach((c, k) => { const g = fold(c); for (let j = 0; j < g.length; j++) at.push(k); f += g; });
    const i = f.indexOf(q), a = at[i], b = at[i + q.length - 1] + 1, m = document.createElement("mark");
    m.textContent = cps.slice(a, b).join("");
    t.replaceChildren(...(i < 0 ? [orig] : [cps.slice(0, a).join(""), m, cps.slice(b).join("")]));
  }
  function search() {
    const q = fold(st.q.trim()); let n = 0;
    box.value = st.q;
    $$("li[data-result]").forEach((r) => {
      r.dataset.fold ||= fold(r.dataset.result + " " + $("[data-title]", r).textContent);
      r.hidden = !(q && r.dataset.fold.includes(q));
      if (!r.hidden) { n++; mark(r, q); }
    });
    say(n ? `${n} result${n === 1 ? "" : "s"} for ${st.q.trim()}` : q ? "No open item matches." : "", "search-status");
  }
  function apply() {
    const v = st.view;
    $$("section.view").forEach((s) => s.classList.toggle("shown", s.dataset.view === v && (v !== "item" || s.dataset.item === st.item)));
    $$(".tabs a").forEach((a) => (a.dataset.go === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    $$("[data-set]").forEach((b) => { const [k, v] = b.dataset.set.split("="); b.setAttribute("aria-pressed", st[k] === v); });
    $$("[data-need],[data-card],[data-lane]").forEach((e) => {
      e.hidden = (st.team !== "" && !(e.dataset.teams || "").toLowerCase().split(" ").includes(st.team)) || (st.intent !== "" && e.dataset.intent !== undefined && e.dataset.intent !== st.intent);
    });
    $$("[data-counts]").forEach((c) => (c.textContent = $$(c.dataset.counts).length));
    $$("[data-board]").forEach((b) => (b.hidden = b.dataset.board !== `${st.columns}-${st.rows}`));
    const intent = $("[data-testid=intent-filter]"); if (intent) intent.value = st.intent;
    $$("[data-toggle]").forEach((b) => {
      const on = st.open.includes(b.dataset.toggle);
      b.setAttribute("aria-expanded", on); document.getElementById(b.getAttribute("aria-controls")).hidden = !on;
    });
    $("[data-testid=keys-single-off]").setAttribute("aria-checked", keysOn);
    search();
    const qs = new URLSearchParams();
    ["view", ...($("section.shown").dataset.url || "").split(" ")].forEach((k) => { if (String(st[k]) !== String(DEF[k])) [].concat(st[k]).forEach((x) => qs.append(k, x)); });
    const query = qs.toString() ? "?" + qs : "", name = location.pathname.split("/").pop() + query;
    history.replaceState(null, "", location.pathname + query);
    $$("[data-field=view-link]").forEach((c) => (c.textContent = name));
    $$("[data-testid=view-link-copy]").forEach((b) => (b.dataset.copy = name));
    select(rows().find((r) => idOf(r) === selId) || rows()[0]);
  }
  function select(r) {
    $$("[aria-current=true]").forEach((e) => e.removeAttribute("aria-current"));
    if (!r) return;
    r.setAttribute("aria-current", "true"); selId = idOf(r);
    r.scrollIntoView({block: "nearest"});
  }
  const heading = () => (st.view === "search" ? box : $("[data-field=title],h1", $("section.shown")));
  function go(change, opener, top) {
    stack = top ? [] : [...stack, {st: {...st, open: [...st.open]}, opener}];
    st = {...st, ...change}; apply(); heading().focus();
  }
  function back() {
    const e = stack.pop();
    st = e ? e.st : {...st, view: "needs-you"}; apply();
    (e && e.opener && e.opener.isConnected && shown(e.opener) ? e.opener : heading()).focus();
  }
  const copy = (b) => navigator.clipboard.writeText(b.dataset.copy).then(() => say("Copied the words for " + b.dataset.for), () => say("Copy failed: select the words"));
  const open = (r) => r && $("[data-go=item]", r)?.click();
  const flip = (b) => { const on = b.getAttribute("aria-expanded") !== "true"; b.setAttribute("aria-expanded", on); return on; };

  document.addEventListener("click", (e) => {
    const t = e.target.closest("button,a,select");
    if (!t) return;
    const d = t.dataset, id = d.testid || "";
    if (t.matches("a[data-go]")) e.preventDefault();
    if (d.copy !== undefined) return copy(t);
    if (d.go === "back") return back();
    if (d.go) return go(d.go === "item" ? {view: "item", item: d.item} : {view: d.go}, t, TOP.includes(d.go));
    if (d.set) { const [k, v] = d.set.split("="); st[k] = v; }
    else if (d.toggle) st.open = st.open.includes(d.toggle) ? st.open.filter((x) => x !== d.toggle) : [...st.open, d.toggle];
    else if (id === "keys-single-off") {
      keysOn = !keysOn;
      try { localStorage.setItem(PREF, keysOn ? "on" : "off"); } catch (x) {}
    } else if (t.classList.contains("btn-fold")) return t.closest(".banner").classList.toggle("banner-expanded", flip(t));
    else if (t.classList.contains("opts-btn")) return t.closest(".board-head").classList.toggle("opts-open", flip(t));
    else return;
    apply();
  });
  document.addEventListener("change", (e) => { if (e.target.dataset.testid === "intent-filter") { st.intent = e.target.value; apply(); } });
  box.addEventListener("input", () => { st.q = box.value; apply(); });
  document.addEventListener("keydown", (e) => {
    const k = e.key, r = rows(), i = r.findIndex((x) => x.getAttribute("aria-current") === "true");
    if (k === "Escape") { if (["search", "keys", "item"].includes(st.view)) { e.preventDefault(); back(); } return; }
    if (k === "Enter" && e.target === box) { e.preventDefault(); return open(visible("li[data-result]")[0]); }
    if (k === "Enter" && !e.target.closest("button,a,select,input")) return open(r[i]);
    if (e.target.matches("input,select,textarea") || !keysOn || st.view === "keys" || e.ctrlKey || e.metaKey || e.altKey) return;
    if (k === "/") { e.preventDefault(); go({view: "search"}, null, false); }
    else if (k === "?") go({view: "keys"}, null, false);
    else if (/^[123]$/.test(k)) go({view: TOP[+k - 1]}, null, true);
    else if (k === "j" || k === "k") select(r[Math.max(0, Math.min(r.length - 1, i + (k === "j" ? 1 : -1)))]);
    else if (k === "c") { const s = st.view === "item" ? $("section.shown") : r[i], b = s && $("[data-copy]", s); if (b) copy(b); }
  });
  apply();
  root.dataset.ready = "1";
})();
