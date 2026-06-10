/* ==========================================================================
   GrandLine product mockup — Observation Deck simulation
   All data is generated in the browser. No backend, no network calls.
   Event types, statuses, and copy mirror the real platform contracts:
   - VoyageStatus: CHARTED PLANNING PDD TDD BUILDING REVIEWING DEPLOYING
                   COMPLETED FAILED PAUSED CANCELLED
   - Den Den Mushi event types: voyage_plan_created, poneglyph_drafted, ...
   ========================================================================== */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ------------------------------------------------------------------ *
   * Static reference data (mirrors frontend StatusBadge / SeaChart)
   * ------------------------------------------------------------------ */
  var GLYPH = {
    CHARTED: "○", PLANNING: "◔", PDD: "◑", TDD: "◑", BUILDING: "◕",
    REVIEWING: "◕", DEPLOYING: "◕", COMPLETED: "●", FAILED: "✕",
    PAUSED: "❚❚", CANCELLED: "⊘"
  };
  var COLUMNS = [
    { id: "col-planning", title: "Planning", statuses: ["CHARTED", "PLANNING"] },
    { id: "col-pdd", title: "PDD", statuses: ["PDD"] },
    { id: "col-tdd", title: "TDD", statuses: ["TDD"] },
    { id: "col-building", title: "Building", statuses: ["BUILDING"] },
    { id: "col-reviewing", title: "Reviewing", statuses: ["REVIEWING"] },
    { id: "col-deploying", title: "Deploying", statuses: ["DEPLOYING"] }
  ];
  var TERMINAL = ["COMPLETED", "FAILED", "CANCELLED"];
  var ROLES = ["captain", "navigator", "doctor", "shipwright", "helmsman"];
  var ACTIVITY = {
    voyage_plan_created: "Charting the course…",
    poneglyph_drafted: "Drafting Poneglyphs…",
    health_check_written: "Writing health checks…",
    phase_build_started: "Building…",
    code_generated: "Generating code…",
    tests_passed: "Tests green ✓",
    phase_build_failed: "Build failed ✕",
    validation_passed: "Validation passed ✓",
    validation_failed: "Validation failed ✕",
    deployment_started: "Deploying…",
    deployment_completed: "Deployed ✓",
    deployment_failed: "Deploy failed ✕",
    pipeline_stage_entered: "Entering stage…",
    checkpoint_created: "Vivre Card saved",
    pipeline_completed: "Voyage complete ✓"
  };

  /* ------------------------------------------------------------------ *
   * Demo fleet — one scripted voyage + static dressing
   * ------------------------------------------------------------------ */
  var voyages = [
    { id: "vg-7f3a2c91", title: "Realtime fleet telemetry API", status: "CHARTED",
      phases: { 1: "PENDING", 2: "PENDING", 3: "PENDING", 4: "PENDING" },
      demo: true, lastEvent: null, failure: null },
    { id: "vg-1b9e4d02", title: "JWT auth hardening", status: "REVIEWING",
      phases: { 1: "BUILT", 2: "BUILT", 3: "BUILT" }, lastEvent: Date.now() - 95e3 },
    { id: "vg-5c8d1e77", title: "Sandbox image cache warm-up", status: "PAUSED",
      phases: { 1: "BUILT", 2: "BUILDING", 3: "PENDING" }, lastEvent: Date.now() - 14 * 60e3, pausedCol: "col-building" },
    { id: "vg-9a2f6b13", title: "Observation Deck theme polish", status: "COMPLETED",
      phases: { 1: "BUILT", 2: "BUILT" }, lastEvent: Date.now() - 3 * 3600e3 },
    { id: "vg-3e7c0a58", title: "Payment webhook retries", status: "FAILED",
      phases: { 1: "BUILT", 2: "FAILED" }, lastEvent: Date.now() - 7 * 3600e3,
      failure: { stage: "BUILDING", code: "max_iterations_exceeded", message: "Phase 2 exceeded 3 build iterations — escalated to fleet admiral" } }
  ];
  var demo = voyages[0];

  /* The scripted voyage. d = ms gap at 1× before the step fires.
     Mirrors real event_type strings published on grandline:events:{voyage_id}. */
  var SCRIPT = [
    { d: 600,  type: "pipeline_started",        role: "captain",    sum: "Voyage accepted — task handed to the Captain", status: "PLANNING" },
    { d: 1400, type: "pipeline_stage_entered",  role: "captain",    sum: "Entered stage PLANNING", stagePing: true },
    { d: 2600, type: "voyage_plan_created",     role: "captain",    sum: "Mission decomposed into 4 phases: schema, ingest API, aggregation worker, dashboard endpoint", ck: "plan_created" },
    { d: 1500, type: "pipeline_stage_entered",  role: "navigator",  sum: "Entered stage PDD", status: "PDD" },
    { d: 2200, type: "poneglyph_drafted",       role: "navigator",  sum: "Poneglyph drafted for phase 1 — telemetry tables + Alembic migration", phase: 1 },
    { d: 1900, type: "poneglyph_drafted",       role: "navigator",  sum: "Poneglyphs drafted for phases 2–4 — endpoints, worker, contracts", ck: "poneglyph_drafted" },
    { d: 1500, type: "pipeline_stage_entered",  role: "doctor",     sum: "Entered stage TDD", status: "TDD" },
    { d: 2600, type: "health_check_written",    role: "doctor",     sum: "12 failing health checks written (pytest) — red as expected, TDD holds", ck: "health_check_written" },
    { d: 1500, type: "pipeline_stage_entered",  role: "shipwright", sum: "Entered stage BUILDING — 2 parallel Shipwrights on independent phases", status: "BUILDING" },
    { d: 1200, type: "phase_build_started",     role: "shipwright", sum: "Phase 1 build started on branch agent/shipwright/vg-7f3a2c", phase: 1, ph: { 1: "BUILDING" } },
    { d: 2300, type: "code_generated",          role: "shipwright", sum: "Phase 1 iteration 1 — 6 files generated, running Doctor's checks in sandbox", phase: 1 },
    { d: 2100, type: "tests_passed",            role: "shipwright", sum: "Phase 1 green — 4/4 checks passing, committed to agent branch", phase: 1, ph: { 1: "BUILT" }, ck: "iteration_1" },
    { d: 1300, type: "phase_build_started",     role: "shipwright", sum: "Phases 2 + 3 build started (parallel layer)", ph: { 2: "BUILDING", 3: "BUILDING" } },
    { d: 2400, type: "code_generated",          role: "shipwright", sum: "Phase 2 iteration 1 — 2/5 checks failing, analyzing tracebacks", phase: 2, fail: true },
    { d: 2200, type: "code_generated",          role: "shipwright", sum: "Phase 2 iteration 2 — regenerated handler with idempotency key", phase: 2 },
    { d: 1800, type: "tests_passed",            role: "shipwright", sum: "Phase 3 green — worker drains queue in sandbox run", phase: 3, ph: { 3: "BUILT" } },
    { d: 1700, type: "tests_passed",            role: "shipwright", sum: "Phase 2 green on iteration 2 — Vivre Card checkpointed", phase: 2, ph: { 2: "BUILT" }, ck: "iteration_2" },
    { d: 1300, type: "phase_build_started",     role: "shipwright", sum: "Phase 4 build started — dashboard endpoint", phase: 4, ph: { 4: "BUILDING" } },
    { d: 2400, type: "tests_passed",            role: "shipwright", sum: "Phase 4 green — 12/12 health checks passing overall", phase: 4, ph: { 4: "BUILT" } },
    { d: 1500, type: "pipeline_stage_entered",  role: "doctor",     sum: "Entered stage REVIEWING", status: "REVIEWING" },
    { d: 2600, type: "validation_passed",       role: "doctor",     sum: "Full suite re-run in clean sandbox — 12/12 passing, coverage 91%", ck: "stage_REVIEWING" },
    { d: 1500, type: "pipeline_stage_entered",  role: "helmsman",   sum: "Entered stage DEPLOYING", status: "DEPLOYING" },
    { d: 1600, type: "deployment_started",      role: "helmsman",   sum: "Deploying tier=preview ref=agent/shipwright/vg-7f3a2c", ck: "deployment_started" },
    { d: 2800, type: "deployment_completed",    role: "helmsman",   sum: "Preview live — https://preview-vg7f3a.grandline.dev (auto tier, no approval needed)" },
    { d: 1700, type: "pipeline_completed",      role: "captain",    sum: "Voyage COMPLETED — staging awaits PR merge, production awaits fleet admiral approval", status: "COMPLETED" }
  ];

  /* ------------------------------------------------------------------ *
   * Simulation state
   * ------------------------------------------------------------------ */
  var sim = {
    idx: 0, timer: null, running: false, started: false, finished: false,
    paused: false, cancelled: false, speed: 1,
    events: [],          // EventEnvelope-ish: {ts, type, role, sum, phase, fail}
    counts: { captain: 0, navigator: 0, doctor: 0, shipwright: 0, helmsman: 0 },
    activeRole: null, prevRole: null,
    statusBeforePause: null,
    scrubbing: false
  };

  /* ------------------------------------------------------------------ *
   * Rendering — Sea Chart
   * ------------------------------------------------------------------ */
  function relTime(ts) {
    if (!ts) return "—";
    var s = Math.max(1, Math.round((Date.now() - ts) / 1000));
    if (s < 60) return s + "s ago";
    var m = Math.round(s / 60);
    if (m < 60) return m + "m ago";
    return Math.round(m / 60) + "h ago";
  }

  function badgeHTML(status) {
    return '<span class="badge st-' + status + '"><span class="g">' + GLYPH[status] + "</span>" + status + "</span>";
  }

  function cardHTML(v) {
    var phases = Object.keys(v.phases);
    var built = phases.filter(function (k) { return v.phases[k] === "BUILT"; }).length;
    var pct = phases.length ? Math.round((built / phases.length) * 100) : 0;
    var chips = phases.map(function (k) {
      return '<span class="phase-chip ' + v.phases[k] + '" title="phase ' + k + ": " + v.phases[k] + '">' + k + "</span>";
    }).join("");
    return (
      '<div class="sea-card" data-v="' + v.id + '">' +
      '<div class="t">' + v.title + "</div>" +
      badgeHTML(v.status) +
      '<div class="progress"><span style="width:' + pct + '%"></span></div>' +
      '<div class="phase-chips">' + chips + "</div>" +
      '<div class="meta"><span>' + relTime(v.lastEvent) + "</span>" +
      '<a href="#" class="open-details" data-v="' + v.id + '">Open details</a></div>' +
      "</div>"
    );
  }

  function columnFor(v) {
    if (v.status === "PAUSED") return v.pausedCol || "col-building";
    for (var i = 0; i < COLUMNS.length; i++) {
      if (COLUMNS[i].statuses.indexOf(v.status) !== -1) return COLUMNS[i].id;
    }
    return null;
  }

  function renderSeaChart() {
    COLUMNS.forEach(function (c) {
      var host = $("#" + c.id + " .cards");
      var items = voyages.filter(function (v) { return columnFor(v) === c.id && TERMINAL.indexOf(v.status) === -1; });
      host.innerHTML = items.map(cardHTML).join("") || "";
      $("#" + c.id + " .count").textContent = items.length;
    });
    var term = voyages.filter(function (v) { return TERMINAL.indexOf(v.status) !== -1; });
    $("#terminal-cards").innerHTML = term.map(cardHTML).join("");
    $("#terminal-count").textContent = term.length;
    $$(".open-details").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); openDrawer(a.getAttribute("data-v")); });
    });
  }

  /* ------------------------------------------------------------------ *
   * Rendering — Sidebar
   * ------------------------------------------------------------------ */
  function renderSidebar() {
    var host = $("#voyage-list");
    host.innerHTML = voyages.map(function (v) {
      return (
        '<button class="voyage-item' + (v.demo ? " active" : "") + '" data-v="' + v.id + '">' +
        '<span class="t">' + v.title + "</span>" + badgeHTML(v.status) + "</button>"
      );
    }).join("");
  }

  /* ------------------------------------------------------------------ *
   * Rendering — Crew Map
   * ------------------------------------------------------------------ */
  var NODE_POS = { captain: 90, navigator: 270, doctor: 450, shipwright: 630, helmsman: 810 };

  function setActiveRole(role, type) {
    $$(".cm-node").forEach(function (n) { n.classList.toggle("active", n.getAttribute("data-role") === role); });
    if (role && ACTIVITY[type]) {
      var label = $("#cm-activity");
      label.textContent = ACTIVITY[type];
      label.setAttribute("x", NODE_POS[role]);
      label.setAttribute("opacity", "1");
      clearTimeout(setActiveRole._t);
      setActiveRole._t = setTimeout(function () { label.setAttribute("opacity", "0"); }, 2000);
    }
  }

  function flashEdge(from, to) {
    if (!from || !to || from === to) return;
    var edge = $('.cm-edge[data-edge="' + from + "-" + to + '"]') || $('.cm-edge[data-edge="' + to + "-" + from + '"]');
    if (!edge) return;
    edge.classList.add("flash");
    var dot = $("#cm-dot");
    dot.setAttribute("opacity", "1");
    var x1 = NODE_POS[from], x2 = NODE_POS[to];
    var t0 = performance.now(), dur = 600;
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      dot.setAttribute("cx", x1 + (x2 - x1) * p);
      dot.setAttribute("cy", 110 - Math.sin(p * Math.PI) * 26);
      if (p < 1) requestAnimationFrame(step);
      else { dot.setAttribute("opacity", "0"); edge.classList.remove("flash"); }
    }
    requestAnimationFrame(step);
  }

  function renderCounts() {
    ROLES.forEach(function (r) {
      var el = $("#count-" + r);
      if (el) el.textContent = sim.counts[r];
      var b = $('.cm-count[data-role="' + r + '"]');
      var bg = $('.cm-count-bg[data-role="' + r + '"]');
      if (b) { b.textContent = sim.counts[r]; }
      if (bg) { bg.setAttribute("opacity", sim.counts[r] ? "1" : "0"); }
      if (b) { b.setAttribute("opacity", sim.counts[r] ? "1" : "0"); }
    });
    $("#cm-total").textContent = sim.events.length;
  }

  /* ------------------------------------------------------------------ *
   * Rendering — Ship's Log
   * ------------------------------------------------------------------ */
  var logFilters = { roles: {}, failOnly: false, q: "" };

  function logRowHTML(ev) {
    var t = new Date(ev.ts).toLocaleTimeString();
    return (
      '<div class="log-row' + (ev.fail ? " fail" : "") + ' new" data-role="' + ev.role + '" data-ts="' + ev.ts + '">' +
      '<span class="ts">' + t + "</span>" +
      '<span class="role-badge rb-' + ev.role + '">' + ev.role + "</span>" +
      '<span class="sum">' + ev.sum + "</span>" +
      '<span class="at">' + ev.type + (ev.phase ? " · ph " + ev.phase : "") + "</span>" +
      "</div>"
    );
  }

  function rowVisible(ev) {
    var anyRole = Object.keys(logFilters.roles).some(function (r) { return logFilters.roles[r]; });
    if (anyRole && !logFilters.roles[ev.role]) return false;
    if (logFilters.failOnly && !ev.fail && !/fail/i.test(ev.type)) return false;
    if (logFilters.q && (ev.sum + " " + ev.type).toLowerCase().indexOf(logFilters.q) === -1) return false;
    if (sim.scrubbing && ev.ts > sim.cursorTs) return false;
    return true;
  }

  function renderLog() {
    var host = $("#log-rows");
    var rows = sim.events.filter(rowVisible);
    host.innerHTML = rows.length
      ? rows.map(logRowHTML).join("")
      : '<div class="log-row"><span class="ts">—</span><span class="role-badge rb-system">system</span><span class="sum">No entries yet — press <b>⛵ Set Sail</b> to run the demo voyage.</span><span class="at"></span></div>';
    host.scrollTop = host.scrollHeight;
  }

  /* ------------------------------------------------------------------ *
   * Details drawer
   * ------------------------------------------------------------------ */
  function openDrawer(vid) {
    var v = voyages.filter(function (x) { return x.id === vid; })[0];
    if (!v) return;
    $("#drawer-title").textContent = v.title;
    $("#d-status").innerHTML = badgeHTML(v.status);
    $("#d-crew").textContent = v.demo && sim.activeRole && !sim.finished ? sim.activeRole : "idle";
    var done = Object.keys(v.phases).filter(function (k) { return v.phases[k] === "BUILT"; });
    $("#d-phases-done").textContent = done.length ? done.join(", ") : "none yet";
    $("#d-phase-table").innerHTML = Object.keys(v.phases).map(function (k) {
      return "<tr><td class='mono'>Phase " + k + "</td><td><span class='phase-chip " + v.phases[k] + "'>" + v.phases[k] + "</span></td></tr>";
    }).join("");
    var f = $("#d-failure");
    if (v.failure) {
      f.style.display = "block";
      f.innerHTML = "<b>✕ " + v.failure.stage + "</b> · <code>" + v.failure.code + "</code><br>" + v.failure.message;
    } else { f.style.display = "none"; }
    var evs = v.demo ? sim.events.slice(-12).reverse() : [];
    $("#d-events").innerHTML = evs.length
      ? evs.map(function (e) { return "<div class='dial-event'><b>" + e.role + "</b> · " + e.type + "</div>"; }).join("")
      : "<div class='dial-event'>No buffered events for this voyage.</div>";
    $("#d-first").textContent = sim.events.length && v.demo ? new Date(sim.events[0].ts).toLocaleString() : "—";
    $("#d-last").textContent = v.demo && sim.events.length ? new Date(sim.events[sim.events.length - 1].ts).toLocaleString() : (v.lastEvent ? new Date(v.lastEvent).toLocaleString() : "—");
    $("#d-buffered").textContent = v.demo ? sim.events.length : 0;
    $("#drawer").classList.add("open");
  }

  /* ------------------------------------------------------------------ *
   * Toasts
   * ------------------------------------------------------------------ */
  function toast(title, sub) {
    var el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = "<b>" + title + "</b>" + (sub ? '<div class="sub">' + sub + "</div>" : "");
    $("#toasts").appendChild(el);
    setTimeout(function () { el.style.opacity = "0"; el.style.transition = "opacity .4s"; }, 3400);
    setTimeout(function () { el.remove(); }, 3900);
  }

  /* ------------------------------------------------------------------ *
   * Simulation engine
   * ------------------------------------------------------------------ */
  function emit(step) {
    var ev = { ts: Date.now(), type: step.type, role: step.role, sum: step.sum, phase: step.phase || null, fail: !!step.fail };
    sim.events.push(ev);
    sim.counts[step.role]++;

    if (step.status) {
      demo.status = step.status;
      if (step.status === "BUILDING") demo.pausedCol = "col-building";
    }
    if (step.ph) Object.keys(step.ph).forEach(function (k) { demo.phases[k] = step.ph[k]; });
    demo.lastEvent = ev.ts;

    flashEdge(sim.prevRole, step.role);
    sim.prevRole = sim.activeRole = step.role;
    setActiveRole(step.role, step.type);
    renderCounts();
    renderSeaChart();
    renderSidebar();
    renderLog();
    updatePlayback();

    if (step.ck) toast("Vivre Card checkpoint", "reason=" + step.ck + " · crew=" + step.role);
    if (step.type === "pipeline_completed") {
      finishDemo();
    }
  }

  function scheduleNext() {
    if (sim.idx >= SCRIPT.length || sim.paused || sim.cancelled) return;
    var step = SCRIPT[sim.idx];
    sim.timer = setTimeout(function () {
      sim.idx++;
      emit(step);
      scheduleNext();
    }, step.d / sim.speed);
  }

  function startDemo() {
    if (sim.running && !sim.finished) return;
    // reset
    clearTimeout(sim.timer);
    sim.idx = 0; sim.events = []; sim.running = true; sim.started = true;
    sim.finished = false; sim.paused = false; sim.cancelled = false;
    sim.activeRole = null; sim.prevRole = null; sim.scrubbing = false;
    ROLES.forEach(function (r) { sim.counts[r] = 0; });
    demo.status = "CHARTED";
    demo.phases = { 1: "PENDING", 2: "PENDING", 3: "PENDING", 4: "PENDING" };
    demo.failure = null; demo.lastEvent = null;
    setConn("live");
    $("#sail-btn").textContent = "⛵ Voyage running…";
    $("#sail-btn").disabled = true;
    setInterventionState();
    renderAll();
    scheduleNext();
  }

  function finishDemo() {
    sim.finished = true; sim.running = false;
    clearTimeout(sim.timer);
    setConn("ended");
    $("#sail-btn").textContent = "↻ Replay voyage";
    $("#sail-btn").disabled = false;
    setActiveRole(null);
    setInterventionState();
    toast("Voyage COMPLETED ●", "preview deployed · staging + production gated");
  }

  function setConn(state) {
    var chip = $("#conn-chip");
    chip.className = "conn " + (state === "live" ? "live" : state === "ended" ? "ended" : "paused");
    $("#conn-label").textContent = state === "live" ? "Live" : state === "ended" ? "Voyage ended" : "Paused";
    $("#conn-transport").textContent = state === "live" ? "· ws" : state === "ended" ? "· read-only" : "· ws";
  }

  /* ------------------------------------------------------------------ *
   * Interventions (fleet admiral controls)
   * ------------------------------------------------------------------ */
  function setInterventionState() {
    var active = sim.running && !sim.finished && !sim.cancelled;
    $("#iv-pause").style.display = active && !sim.paused ? "" : "none";
    $("#iv-resume").style.display = active && sim.paused ? "" : "none";
    $("#iv-pause").disabled = !active;
    $("#iv-resume").disabled = !active;
    $("#iv-inject").disabled = !active;
    $("#iv-cancel").disabled = !active;
  }

  function intervene(type, sum, role) {
    var ev = { ts: Date.now(), type: type, role: role || "captain", sum: sum, phase: null, fail: false };
    sim.events.push(ev);
    renderLog(); updatePlayback(); renderCounts();
  }

  $("#iv-pause").addEventListener("click", function () {
    if (!sim.running || sim.paused) return;
    sim.paused = true;
    clearTimeout(sim.timer);
    sim.statusBeforePause = demo.status;
    demo.status = "PAUSED";
    setConn("paused");
    intervene("crew_action_recorded", "PIPELINE_PAUSED — voyage paused by fleet admiral; Vivre Card checkpoint created (reason=pause)");
    toast("Voyage paused ❚❚", "Vivre Card checkpoint · reason=pause");
    setInterventionState(); renderSeaChart(); renderSidebar();
  });

  $("#iv-resume").addEventListener("click", function () {
    if (!sim.paused) return;
    sim.paused = false;
    demo.status = sim.statusBeforePause || "BUILDING";
    setConn("live");
    intervene("crew_action_recorded", "PIPELINE_RESUMED — restored from Vivre Card; stage guards skip already-satisfied phases");
    toast("Voyage resumed ▶", "restored from checkpoint — no work lost");
    setInterventionState(); renderSeaChart(); renderSidebar();
    scheduleNext();
  });

  $("#iv-inject").addEventListener("click", function () { $("#inject-modal").classList.add("open"); });
  $("#inject-cancel").addEventListener("click", function () { $("#inject-modal").classList.remove("open"); });
  $("#inject-send").addEventListener("click", function () {
    var txt = $("#inject-text").value.trim();
    if (txt.length < 10) { $("#inject-text").focus(); return; }
    $("#inject-modal").classList.remove("open");
    intervene("crew_action_recorded", "CONTEXT_INJECTED — “" + txt.slice(0, 120) + "” appended to the active agent's context window");
    toast("Context injected ✎", "delivered to " + (sim.activeRole || "crew") + " via Den Den Mushi");
    $("#inject-text").value = "";
  });

  $("#iv-cancel").addEventListener("click", function () { $("#cancel-modal").classList.add("open"); });
  $("#cancel-keep").addEventListener("click", function () { $("#cancel-modal").classList.remove("open"); });
  $("#cancel-confirm").addEventListener("click", function () {
    $("#cancel-modal").classList.remove("open");
    sim.cancelled = true; sim.running = false; sim.finished = true;
    clearTimeout(sim.timer);
    demo.status = "CANCELLED";
    setConn("ended");
    intervene("crew_action_recorded", "PIPELINE_CANCELLED — graceful shutdown; final Vivre Card preserved for post-mortem");
    toast("Voyage cancelled ⊘", "state preserved — nothing lost");
    $("#sail-btn").textContent = "↻ Replay voyage";
    $("#sail-btn").disabled = false;
    setActiveRole(null);
    setInterventionState(); renderSeaChart(); renderSidebar();
  });

  /* ------------------------------------------------------------------ *
   * Playback scrubber
   * ------------------------------------------------------------------ */
  function updatePlayback() {
    var r = $("#scrubber");
    if (!sim.events.length) { r.disabled = true; return; }
    r.disabled = false;
    r.min = sim.events[0].ts;
    r.max = sim.events[sim.events.length - 1].ts;
    if (!sim.scrubbing) r.value = r.max;
    $("#pt-start").textContent = new Date(+r.min).toLocaleTimeString();
    $("#pt-end").textContent = sim.scrubbing ? "scrubbing" : new Date(+r.max).toLocaleTimeString();
    $("#pt-end").style.color = sim.scrubbing ? "var(--amber)" : "";
  }

  $("#scrubber").addEventListener("input", function () {
    sim.scrubbing = true;
    sim.cursorTs = +this.value;
    $("#return-live").style.display = "";
    renderLog(); updatePlayback();
  });
  $("#return-live").addEventListener("click", function () {
    sim.scrubbing = false;
    this.style.display = "none";
    renderLog(); updatePlayback();
  });

  /* Speed control */
  $("#speed-btn").addEventListener("click", function () {
    sim.speed = sim.speed === 1 ? 2 : sim.speed === 2 ? 4 : 1;
    this.textContent = sim.speed + "×";
  });

  $("#sail-btn").addEventListener("click", startDemo);

  /* ------------------------------------------------------------------ *
   * Tabs, palette, shortcuts, chart dialog
   * ------------------------------------------------------------------ */
  function showView(name) {
    $$(".deck-tab").forEach(function (t) { t.classList.toggle("active", t.getAttribute("data-view") === name); });
    $$(".deck-view").forEach(function (v) { v.classList.toggle("active", v.id === "view-" + name); });
  }
  $$(".deck-tab").forEach(function (t) {
    t.addEventListener("click", function () { showView(t.getAttribute("data-view")); });
  });

  /* Ship's Log filters */
  $$(".filter-chip[data-role]").forEach(function (c) {
    c.addEventListener("click", function () {
      var r = c.getAttribute("data-role");
      logFilters.roles[r] = !logFilters.roles[r];
      c.classList.toggle("on", logFilters.roles[r]);
      renderLog();
    });
  });
  $("#fail-only").addEventListener("click", function () {
    logFilters.failOnly = !logFilters.failOnly;
    this.classList.toggle("on", logFilters.failOnly);
    renderLog();
  });
  $("#log-search").addEventListener("input", function () {
    logFilters.q = this.value.toLowerCase();
    renderLog();
  });
  $("#clear-filters").addEventListener("click", function () {
    logFilters.roles = {}; logFilters.failOnly = false; logFilters.q = "";
    $("#log-search").value = "";
    $$(".filter-chip").forEach(function (c) { c.classList.remove("on"); });
    renderLog();
  });

  /* Chart-a-course dialog */
  $("#chart-open").addEventListener("click", function () { $("#chart-modal").classList.add("open"); });
  $("#chart-cancel").addEventListener("click", function () { $("#chart-modal").classList.remove("open"); });
  $("#chart-create").addEventListener("click", function () {
    var title = $("#chart-title").value.trim() || "Untitled voyage";
    var sail = $("#chart-sail").checked;
    voyages.push({ id: "vg-" + Math.random().toString(16).slice(2, 10), title: title, status: "CHARTED",
      phases: { 1: "PENDING" }, lastEvent: Date.now() });
    $("#chart-modal").classList.remove("open");
    $("#chart-title").value = ""; $("#chart-task").value = "";
    renderSeaChart(); renderSidebar();
    toast("Course charted ○", sail ? "POST /voyages → /start · status=CHARTED" : "POST /voyages · status=CHARTED");
  });

  /* Drawer */
  $("#drawer-close").addEventListener("click", function () { $("#drawer").classList.remove("open"); });
  $$(".drawer-tab").forEach(function (t) {
    t.addEventListener("click", function () {
      $$(".drawer-tab").forEach(function (x) { x.classList.remove("active"); });
      t.classList.add("active");
      $$(".drawer-pane").forEach(function (p) { p.style.display = p.id === "pane-" + t.getAttribute("data-pane") ? "block" : "none"; });
    });
  });

  /* Command palette + keyboard shortcuts (mirrors P14 editable-focus guard) */
  var PALETTE_CMDS = [
    { label: "Go to Sea Chart", kbd: "g s", run: function () { showView("sea"); } },
    { label: "Go to Crew Map", kbd: "g c", run: function () { showView("map"); } },
    { label: "Go to Ship's Log", kbd: "g l", run: function () { showView("log"); } },
    { label: "Set sail / replay demo voyage", kbd: "", run: startDemo },
    { label: "Return to live", kbd: "", run: function () { sim.scrubbing = false; $("#return-live").style.display = "none"; renderLog(); updatePlayback(); } },
    { label: "Keyboard shortcuts", kbd: "?", run: function () { $("#help-modal").classList.add("open"); } }
  ];
  function renderPalette(q) {
    var list = $("#palette-list");
    list.innerHTML = PALETTE_CMDS
      .filter(function (c) { return c.label.toLowerCase().indexOf((q || "").toLowerCase()) !== -1; })
      .map(function (c, i) {
        return '<button class="palette-item' + (i === 0 ? " sel" : "") + '" data-i="' + PALETTE_CMDS.indexOf(c) + '">' +
          "<span>" + c.label + "</span>" + (c.kbd ? '<span class="kbd">' + c.kbd + "</span>" : "") + "</button>";
      }).join("");
    $$(".palette-item").forEach(function (b) {
      b.addEventListener("click", function () {
        closePalette();
        PALETTE_CMDS[+b.getAttribute("data-i")].run();
      });
    });
  }
  function openPalette() { $("#palette").classList.add("open"); $("#palette-input").value = ""; renderPalette(""); $("#palette-input").focus(); }
  function closePalette() { $("#palette").classList.remove("open"); }
  $("#palette-input").addEventListener("input", function () { renderPalette(this.value); });
  $("#palette").addEventListener("click", function (e) { if (e.target === this) closePalette(); });
  $("#palette-open").addEventListener("click", openPalette);
  $("#help-close").addEventListener("click", function () { $("#help-modal").classList.remove("open"); });

  var chord = null;
  document.addEventListener("keydown", function (e) {
    var el = document.activeElement;
    var editing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      $("#palette").classList.contains("open") ? closePalette() : openPalette();
      return;
    }
    if (e.key === "Escape") {
      closePalette();
      $$(".modal-backdrop").forEach(function (m) { m.classList.remove("open"); });
      $("#drawer").classList.remove("open");
      return;
    }
    if (editing) return; // P14 editable-focus guard
    if (e.key === "?") { $("#help-modal").classList.add("open"); return; }
    if (e.key === "/") { e.preventDefault(); showView("log"); $("#log-search").focus(); return; }
    if (e.key === "f") { $("#deck-body").classList.toggle("focus"); return; }
    if (e.key === "g") { chord = "g"; setTimeout(function () { chord = null; }, 900); return; }
    if (chord === "g") {
      if (e.key === "s") showView("sea");
      if (e.key === "c") showView("map");
      if (e.key === "l") showView("log");
      chord = null;
    }
  });

  /* ------------------------------------------------------------------ *
   * Dial System failover simulation
   * ------------------------------------------------------------------ */
  var dialDown = false;
  function dialEvent(cls, text) {
    var host = $("#dial-events");
    var el = document.createElement("div");
    el.className = "dial-event " + (cls || "");
    el.textContent = text;
    host.prepend(el);
    while (host.children.length > 8) host.lastChild.remove();
  }
  $("#dial-sim").addEventListener("click", function () {
    if (!dialDown) {
      dialDown = true;
      this.textContent = "↻ Restore anthropic";
      $$('.provider-chip[data-p="anthropic"]').forEach(function (c) { c.classList.add("down"); });
      $$("[data-active-provider]").forEach(function (cell) {
        cell.innerHTML = '<span class="provider-chip"><span class="pd"></span>openai</span> <span class="mono" style="color:var(--ocean-500)">gpt-4o</span>';
      });
      dialEvent("warn", "rate_limit detected · provider=anthropic · window=60s tokens>100k");
      setTimeout(function () { dialEvent("", "checkpoint_created · reason=failover · crew=captain (Vivre Card saved)"); }, 450);
      setTimeout(function () { dialEvent("ok", "provider_switched · captain → openai · resumed mid-voyage, no work lost"); }, 950);
    } else {
      dialDown = false;
      this.textContent = "⚡ Simulate anthropic rate-limit";
      $$('.provider-chip[data-p="anthropic"]').forEach(function (c) { c.classList.remove("down"); });
      $$("[data-active-provider]").forEach(function (cell) {
        cell.innerHTML = '<span class="provider-chip"><span class="pd"></span>anthropic</span> <span class="mono" style="color:var(--ocean-500)">claude-sonnet-4</span>';
      });
      dialEvent("ok", "provider restored · captain → anthropic (primary)");
    }
  });

  /* ------------------------------------------------------------------ *
   * Pipeline section: cycle the active stage highlight
   * ------------------------------------------------------------------ */
  (function cycleStages() {
    var stages = $$("#pipeline-flow .stage");
    if (!stages.length) return;
    var i = 0;
    setInterval(function () {
      stages.forEach(function (s, j) { s.classList.toggle("active", j === i); });
      i = (i + 1) % stages.length;
    }, 1600);
  })();

  /* ------------------------------------------------------------------ *
   * Boot
   * ------------------------------------------------------------------ */
  function renderAll() {
    renderSeaChart(); renderSidebar(); renderLog(); renderCounts(); updatePlayback(); setInterventionState();
  }
  renderAll();
  setInterval(function () { if (!sim.running) renderSeaChart(); }, 15000); // refresh relative timestamps

  /* Auto-start the demo when the deck scrolls into view */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && !seen && !sim.started) {
          seen = true;
          setTimeout(startDemo, 700);
          io.disconnect();
        }
      });
    }, { threshold: 0.35 });
    io.observe($("#deck"));
  }
})();
