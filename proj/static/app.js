/* Smart Traffic Control OS - front end */
const DIRS = ["North", "South", "East", "West"];
const TYPES = ["Car", "Bike", "Bus", "Truck", "Ambulance", "Fire Engine"];
const SCEN_LABEL = {normal: "Normal traffic", congestion: "Heavy congestion", ambulance: "Ambulance detected",
  accident: "Traffic accident", signal_failure: "Signal failure"};
const vehicles = [];
let lastResult = null, stale = false, simActive = false;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const setText = (id, v) => { $(id).textContent = v; };
const icon = t => ({ambulance: "🚑", "fire engine": "🚒", bus: "🚌", truck: "🚚", bike: "🏍️", car: "🚗"}[String(t).toLowerCase()] || "🚗");
const isAmb = t => String(t).toLowerCase() === "ambulance";
const selectedScenario = () => document.querySelector('input[name="scenario"]:checked').value;
const whole = s => /^\d+$/.test(String(s).trim()) ? Number(String(s).trim()) : NaN;

/* ---------------- player state ---------------- */
const player = {tl: [], i: 0, timer: null};
const currentFrame = () => (lastResult && !stale && player.tl.length) ? player.tl[player.i] : null;

/* ---------------- vehicle management ---------------- */
function nextPid() {
  const used = new Set(vehicles.map(v => v.pid.toLowerCase()));
  let n = 1;
  while (used.has("p" + String(n).padStart(2, "0"))) n++;
  return "P" + String(n).padStart(2, "0");
}
function currentRows() {
  return (lastResult && !stale) ? lastResult.vehicles
    : vehicles.map(v => ({...v, origin: v.direction, detour: false, generated: false}));
}
function renderDirCounts() {
  const rows = currentRows(), f = currentFrame();
  const html = DIRS.map(d => {
    const total = rows.filter(v => v.origin === d).length;
    const waiting = f ? f.queues[d].length : 0;
    return `<div class="dir-chip"><b>${d}</b><span>${total} vehicle${total === 1 ? "" : "s"}</span>${f ? `<small>${waiting} waiting</small>` : ""}</div>`;
  }).join("");
  $("dirCountsDash").innerHTML = html;
  $("dirCountsVeh").innerHTML = html;
}
function renderVehicles() {
  const rows = currentRows(), f = currentFrame(), body = $("vehicleRows");
  renderDirCounts();
  if (!f) {   // nothing is running: every vehicle in the list is still NEW
    setText("stateNew", rows.length);
    ["Ready", "Running", "Waiting", "Terminated"].forEach(k => setText("state" + k, 0));
  }
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No vehicles yet. Add a vehicle or load sample data.</td></tr>';
    return;
  }
  body.innerHTML = rows.map(v => {
    const st = f ? (f.states[v.pid] || "New") : "New";
    return `<tr><td>${esc(v.pid)}${v.generated ? ' <span class="auto">auto</span>' : ""}</td><td>${esc(v.type)}</td>`
      + `<td>${esc(v.direction)}${v.detour ? ` <span class="auto" title="Diverted from ${esc(v.origin)}">↪ from ${esc(v.origin)}</span>` : ""}</td>`
      + `<td>${v.arrival}</td><td>${v.service}</td><td><span class="tag st-${st.toLowerCase()}">${st}</span></td>`
      + `<td>${v.generated ? "" : `<button class="btn text-btn" data-remove="${esc(v.pid)}" ${simActive ? "disabled" : ""}>Remove</button>`}</td></tr>`;
  }).join("");
}
function markStale() {
  if (lastResult && !stale) {
    stale = true; pause();
    setText("liveStatus", "Vehicle list changed. Run again to refresh results");
    setStatus("RESULTS OUTDATED");
  }
  renderVehicles();
}
function showFormError(msg) { setText("formError", msg || ""); }
function setLocked(on) {
  simActive = on;
  ["pid", "vehicleType", "direction", "arrival", "service", "addBtn", "sampleBtn", "clearVehicles"].forEach(id => { $(id).disabled = on; });
  $("lockNote").hidden = !on;
  document.querySelectorAll("[data-remove]").forEach(b => { b.disabled = on; });
}

$("vehicleRows").addEventListener("click", e => {
  const b = e.target.closest("[data-remove]");
  if (!b || simActive) return;
  const i = vehicles.findIndex(v => v.pid === b.dataset.remove);
  if (i >= 0) { vehicles.splice(i, 1); showFormError(""); markStale(); }
});
$("vehicleForm").addEventListener("submit", e => {
  e.preventDefault();
  if (simActive) { showFormError("Vehicle data is locked while a simulation is running."); return; }
  const pid = $("pid").value.trim() || nextPid();
  const type = $("vehicleType").value, direction = $("direction").value;
  const arrival = whole($("arrival").value), service = whole($("service").value);
  let err = "";
  if (!/^[A-Za-z0-9_-]{1,12}$/.test(pid)) err = "Process ID: use 1-12 letters, digits, - or _.";
  else if (vehicles.some(v => v.pid.toLowerCase() === pid.toLowerCase())) err = `Process ID ${pid} already exists. Choose another or leave it blank for an automatic ID.`;
  else if (!TYPES.includes(type)) err = "Choose a valid vehicle type.";
  else if (!DIRS.includes(direction)) err = "Direction must be North, South, East or West.";
  else if (Number.isNaN(arrival)) err = "Arrival time must be a whole number that is 0 or more.";
  else if (Number.isNaN(service) || service < 1) err = "Service time must be a whole number of at least 1.";
  else if (arrival > 1000 || service > 100) err = "Arrival time must be at most 1000 and service time at most 100.";
  else if (vehicles.length >= 200) err = "At most 200 vehicles are supported.";
  if (err) { showFormError(err); return; }
  showFormError("");
  vehicles.push({pid, type, direction, arrival, service});
  $("pid").value = "";
  markStale();
});
$("sampleBtn").addEventListener("click", () => {
  if (simActive) return;
  vehicles.splice(0, vehicles.length,
    {pid: "P01", type: "Car", direction: "North", arrival: 0, service: 5},
    {pid: "P02", type: "Bike", direction: "East", arrival: 1, service: 3},
    {pid: "P03", type: "Bus", direction: "South", arrival: 2, service: 4},
    {pid: "P04", type: "Ambulance", direction: "West", arrival: 3, service: 2},
    {pid: "P05", type: "Car", direction: "North", arrival: 4, service: 3},
    {pid: "P06", type: "Truck", direction: "East", arrival: 5, service: 6});
  showFormError(""); markStale();
});
$("clearVehicles").addEventListener("click", () => {
  if (simActive || !vehicles.length) return;
  if (!confirm(`Remove all ${vehicles.length} vehicles? This cannot be undone.`)) return;
  vehicles.splice(0); showFormError(""); markStale();
});

/* ---------------- status helpers ---------------- */
function setStatus(t) { setText("statusText", t); }
function refreshStatus() {
  if (!lastResult || stale) return;
  const last = player.tl.length - 1;
  setStatus(player.timer ? "RUNNING" : player.i >= last ? "COMPLETED" : "PAUSED");
}

/* ---------------- resources ---------------- */
function renderResources(f) {
  const cap = Math.max(1, Number($("laneCapacity").value) || 4);
  const res = f ? f.resources : DIRS.map(d => ({direction: d, capacity: cap, allocated: 0, available: cap, demand: 0, status: "OK"}));
  $("resourceRows").innerHTML = res.map(x => {
    const cls = x.status === "OK" ? "ok" : x.status === "CAPACITY EXCEEDED" ? "bad" : "warn";
    return `<tr><td><b>${x.direction}</b></td><td>${x.capacity}</td><td>${x.allocated}</td><td>${x.available}</td><td>${x.demand}</td><td><span class="tag st-${cls}">${x.status}</span></td></tr>`;
  }).join("");
  const over = res.filter(x => x.status === "CAPACITY EXCEEDED");
  const w = $("resourceWarn");
  w.hidden = !over.length;
  if (over.length) w.textContent = "⚠ Capacity exceeded: " + over.map(x => `${x.direction} (demand ${x.demand} > capacity ${x.capacity})`).join(", ") + ". Extra vehicles wait for a free lane slot.";
}
$("laneCapacity").addEventListener("input", () => { if (!currentFrame()) renderResources(null); });

/* ---------------- Gantt chart ---------------- */
const U = 40; // px per time unit
function renderGantt(r) {
  const end = r.metrics.makespan;
  const blocks = r.gantt.map(g => {
    const dur = g.end - g.start;
    let label = g.pid, tip;
    if (g.kind === "idle") { label = "IDLE"; tip = `Idle\nNo vehicle crossing\nDuration: ${g.start}–${g.end} (${dur} unit${dur > 1 ? "s" : ""})`; }
    else if (g.kind === "clearance") { label = "RED"; tip = `All-red clearance before ${g.direction} turns green\nDuration: ${g.start}–${g.end} (${dur} unit${dur > 1 ? "s" : ""})`; }
    else {
      tip = `${g.pid} (${g.type})\nDirection: ${g.direction}\nDuration: ${g.start}–${g.end} (${dur} unit${dur > 1 ? "s" : ""})`
        + (g.kind === "ambulance" ? "\nEmergency priority" + (g.manual ? " (manual override, signal failed)" : "") : "\nNormal vehicle (FCFS)");
    }
    if (g.preempts) tip += `\n⚡ Emergency preemption of ${g.preempts}`;
    if (g.interrupted) tip += "\n⏸ Interrupted by an emergency vehicle, resumes later";
    const bolt = g.preempts ? '<i class="bolt">⚡</i>' : "";
    return `<div class="gb ${g.kind}${g.interrupted ? " interrupted" : ""}${g.preempts ? " preempts" : ""}" style="left:${g.start * U}px;width:${dur * U - 2}px" title="${esc(tip)}">${bolt}<span>${esc(label)}</span><small>${g.start}–${g.end}</small></div>`;
  }).join("");
  const step = end > 80 ? 10 : end > 40 ? 5 : end > 20 ? 2 : 1;
  let ticks = "";
  for (let t = 0; t <= end; t++) ticks += `<div class="tick" style="left:${t * U}px">${t % step === 0 || t === end ? `<span>${t}</span>` : ""}</div>`;
  $("gantt").innerHTML = `<div class="gantt-scroll"><div class="gantt-inner" style="width:${end * U + 24}px">`
    + `<div class="gantt-track">${blocks}<div class="playhead" id="playhead"></div></div><div class="gantt-scale">${ticks}</div></div></div>`;
}

/* ---------------- results ---------------- */
const fmtEmergency = m => m.emergencyResponse === null ? "N/A" : `${m.emergencyResponse} time unit${m.emergencyResponse === 1 ? "" : "s"}`;
function renderReports(r) {
  const m = r.metrics;
  $("reportRows").innerHTML = [
    ["Average waiting time", "Compare traffic efficiency", m.averageWaiting + " time units"],
    ["Maximum queue length", "Identify congestion", m.maxQueue + " vehicles"],
    ["Throughput", "Measure completed vehicles", m.throughput + " vehicles / unit"],
    ["Emergency response time", "Evaluate ambulance priority", fmtEmergency(m)
      + (Object.keys(m.emergencyResponseById).length ? " (" + Object.entries(m.emergencyResponseById).map(([k, v]) => `${k}: ${v}`).join(", ") + ")" : "")],
    ["Signal utilization", "Evaluate signal usage", m.signalUtilization + "%"],
    ["Total vehicles completed", "Track completion", m.completed + " / " + m.totalVehicles],
  ].map(x => `<tr><td>${esc(x[0])}</td><td>${esc(x[1])}</td><td><b>${esc(x[2])}</b></td></tr>`).join("");
  const c = r.config;
  $("summary").innerHTML = [
    ["Algorithm", r.algorithm], ["Scenario", r.scenarioLabel + (c.scenarioStart !== null ? ` (from T=${c.scenarioStart}${c.scenarioEnd !== null ? " to T=" + c.scenarioEnd : ""}${c.affectedDirection ? ", " + c.affectedDirection : ""})` : "")],
    ["Time quantum", c.quantum], ["Lane capacity / direction", c.laneCapacity],
    ["Simulation clock", `T=0 to T=${m.makespan}`], ["Started", r.startedAt], ["Finished", r.finishedAt],
    ["Emergency preemptions", m.preemptions], ["Capacity warnings", m.capacityWarnings],
    ["Conflicting greens", m.greenConflicts],
  ].map(x => `<div><span>${esc(x[0])}</span><b>${esc(x[1])}</b></div>`).join("");
  $("eventLog").innerHTML = r.events.map(e => `<div class="event k-${e.kind}"><time>T=${e.time}</time>${esc(e.message)}</div>`).join("");
  const rk = new Set(["request", "allocate", "release", "warning", "divert"]);
  $("resourceLog").innerHTML = r.events.filter(e => rk.has(e.kind)).map(e => `<div class="event k-${e.kind}"><time>T=${e.time}</time>${esc(e.message)}</div>`).join("")
    || '<p class="empty">No resource events.</p>';
}
function renderResult(r) {
  lastResult = r; stale = false;
  const m = r.metrics;
  setText("avgWait", m.averageWaiting); setText("maxQueue", m.maxQueue); setText("throughput", m.throughput);
  setText("signalUtil", m.signalUtilization + "%"); setText("completedCount", `${m.completed}/${m.totalVehicles}`);
  setText("emergencyResponse", m.emergencyResponse === null ? "N/A" : m.emergencyResponse);
  $("scheduleRows").innerHTML = r.vehicles.map(v => `<tr><td>${esc(v.pid)}</td><td>${v.start ?? "—"}</td><td>${v.completion ?? "—"}</td><td>${v.waiting}</td><td>${v.turnaround ?? "—"}</td><td>${v.response ?? "—"}</td></tr>`).join("");
  renderGantt(r); renderReports(r);
  setupPlayer(r);
}

/* ---------------- run / reset ---------------- */
function setMsg(t) { setText("runMsg", t || ""); }
function readSettings() {
  const quantum = whole($("quantum").value), cap = whole($("laneCapacity").value);
  const start = whole($("scenarioStart").value), dur = whole($("scenarioDuration").value);
  if (Number.isNaN(quantum) || quantum < 1) throw new Error("Time quantum must be a whole number of at least 1.");
  if (Number.isNaN(cap) || cap < 1) throw new Error("Lane capacity must be a whole number of at least 1.");
  if (Number.isNaN(start)) throw new Error("Scenario start time must be a whole number that is 0 or more.");
  if (Number.isNaN(dur) || dur < 1) throw new Error("Scenario duration must be a whole number of at least 1.");
  return {quantum, laneCapacity: cap, scenarioStart: start, scenarioDuration: dur, releaseOnFinish: $("releaseOnFinish").checked};
}
$("runBtn").addEventListener("click", async () => {
  setMsg("");
  if (!vehicles.length) { setMsg("Add vehicles or click Load sample vehicles first."); return; }
  let payload;
  try { payload = {vehicles, scenario: selectedScenario(), affectedDirection: $("affectedDirection").value, ...readSettings()}; }
  catch (err) { setMsg(err.message); return; }
  $("runBtn").disabled = true; $("runBtn").textContent = "Running…";
  try {
    const res = await fetch("/api/simulate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Simulation failed.");
    renderResult(data);
  } catch (err) { setMsg(err.message); }
  finally { $("runBtn").disabled = false; $("runBtn").textContent = "▶ Run simulation"; }
});
$("resetBtn").addEventListener("click", () => {
  lastResult = null; stale = false; setMsg("");
  resetPlayer();
  ["avgWait", "maxQueue", "throughput", "signalUtil", "completedCount", "emergencyResponse"].forEach(id => setText(id, "—"));
  $("scheduleRows").innerHTML = '<tr><td colspan="6" class="empty">No results yet.</td></tr>';
  $("gantt").innerHTML = '<p class="empty">Run the simulation to see process execution.</p>';
  $("reportRows").innerHTML = '<tr><td colspan="3" class="empty">Run a simulation to generate a report.</td></tr>';
  $("resourceLog").innerHTML = '<p class="empty">Resource events will appear here.</p>';
  $("eventLog").innerHTML = '<p class="empty">Events will appear here.</p>';
  $("summary").innerHTML = '<p class="empty">Run a simulation to generate a report.</p>';
  renderResources(null); renderVehicles(); updateScenarioLabel();
});

/* ---------------- scenario label ---------------- */
function updateScenarioLabel() {
  const s = selectedScenario();
  setText("scenarioStatus", "Selected: " + SCEN_LABEL[s]);
  if (!currentFrame()) setText("liveScenario", SCEN_LABEL[s]);
}
document.querySelectorAll('input[name="scenario"]').forEach(r => r.addEventListener("change", updateScenarioLabel));

/* ---------------- CSV export (same data object that the page shows) ---------------- */
function csvCell(x) {
  if (x === null || x === undefined) return "";
  if (typeof x === "number") return String(x);          // numbers stay numeric in Excel
  let s = String(x);
  if (typeof x === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;   // neutralise spreadsheet formulas
  return `"${s.replaceAll('"', '""')}"`;
}
function buildCsv(r) {
  const m = r.metrics, c = r.config, lines = [];
  const add = (...cells) => lines.push(cells.map(csvCell).join(","));
  add("Smart Traffic Control OS - Simulation Report"); add();
  add("SIMULATION DETAILS");
  add("Scenario", r.scenarioLabel);
  if (c.scenarioStart !== null) add("Scenario start (time unit)", c.scenarioStart);
  if (c.scenarioEnd !== null) add("Scenario end (time unit)", c.scenarioEnd);
  if (c.affectedDirection) add("Affected direction", c.affectedDirection);
  add("Scheduling algorithm", r.algorithm);
  add("Ambulances", "Preemptive priority, FCFS among ambulances");
  add("Normal vehicles", "FCFS within each directional queue");
  add("Signals", "Round Robin N > S > E > W");
  add("Time quantum", c.quantum); add("Lane capacity per direction", c.laneCapacity);
  add("Release green when vehicle finishes", c.releaseOnFinish ? "Yes" : "No");
  add("Simulation clock start", 0); add("Simulation clock end", m.makespan);
  add("Simulation started (wall clock)", r.startedAt); add("Simulation finished (wall clock)", r.finishedAt);
  add();
  add("SUMMARY METRICS");
  add("Average waiting time (time units)", m.averageWaiting); add("Maximum queue length (vehicles)", m.maxQueue);
  add("Throughput (vehicles / unit)", m.throughput); add("Signal utilization (%)", m.signalUtilization);
  add("Emergency response time", fmtEmergency(m)); add("Total vehicles completed", `${m.completed} / ${m.totalVehicles}`);
  add("Emergency preemptions", m.preemptions); add("Capacity warnings", m.capacityWarnings);
  add();
  add("SCHEDULING RESULTS");
  add("PID", "Vehicle", "Direction", "Original direction", "Arrival", "Service", "Start", "Completion", "Waiting", "Turnaround", "Response", "State");
  r.vehicles.forEach(v => add(v.pid, v.type, v.direction, v.origin, v.arrival, v.service, v.start, v.completion, v.waiting, v.turnaround, v.response, v.state));
  add();
  add("GANTT CHART");
  add("Process", "Block type", "Direction", "Start", "End", "Duration", "Note");
  r.gantt.forEach(g => add(g.pid, g.kind, g.direction, g.start, g.end, g.end - g.start,
    [g.preempts ? "preempts " + g.preempts : "", g.interrupted ? "interrupted by emergency" : ""].filter(Boolean).join("; ")));
  add();
  add("ACTIVITY LOG");
  add("Time", "Type", "Message");
  r.events.forEach(e => add(e.time, e.kind, e.message));
  return lines.join("\r\n");
}
$("exportBtn").addEventListener("click", () => {
  if (!lastResult) { setMsg("Run a simulation before exporting."); return; }
  const blob = new Blob(["\ufeff" + buildCsv(lastResult)], {type: "text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "traffic-simulation-report.csv"; a.click();
  URL.revokeObjectURL(a.href);
});

/* ---------------- playback ---------------- */
function renderQueue(dir, list) {
  const el = $("queue" + dir), show = list.slice(0, 3);
  el.innerHTML = show.map(v => `<span class="chip ${isAmb(v.type) ? "amb" : ""}${v.pending ? " pend" : ""}" title="${esc(v.pid)} (${esc(v.type)})${v.pending ? " - waiting for a lane slot" : ""}">${icon(v.type)}<b>${esc(v.pid)}</b></span>`).join("")
    + (list.length > 3 ? `<span class="chip more">+${list.length - 3}</span>` : "");
}
function setLight(d, state) {
  const el = $("light" + d), lamps = el.querySelectorAll("i");
  lamps.forEach(x => { x.className = ""; });
  if (state === "green") lamps[2].className = "green";
  else if (state === "amber") lamps[1].className = "amber";
  else if (state === "red") lamps[0].className = "red";
  el.classList.toggle("on", state === "green");
}
function drawFrame(i) {
  const tl = player.tl; if (!tl.length) return;
  i = Math.max(0, Math.min(tl.length - 1, i)); player.i = i;
  const f = tl[i], r = lastResult, last = tl.length - 1, done = f.mode === "done";
  $("scrub").value = i; setText("clock", "T = " + f.t);
  const emergency = f.mode === "emergency", idle = f.mode === "idle", clear = f.mode === "clearance";
  const green = DIRS.find(d => f.signals[d] === "green") || null;
  DIRS.forEach(d => {
    setLight(d, f.signals[d]);
    renderQueue(d, f.queues[d]);
    const lane = $("lane" + d), blocked = f.blocked.includes(d), failed = f.failed.includes(d);
    lane.textContent = d.toUpperCase() + (blocked ? " 🚧 BLOCKED" : failed ? " ⚠ SIGNAL OUT" : "");
    lane.classList.toggle("blocked", blocked); lane.classList.toggle("failed", failed);
  });
  document.querySelectorAll("#rrRing [data-d]").forEach(s => s.classList.toggle("on", f.mode === "normal" && s.dataset.d === f.direction));
  const box = $("centerBox"); box.classList.toggle("emergency", emergency || clear); box.classList.toggle("idle", idle || done);
  setText("centerIcon", f.pid ? icon(f.type) : done ? "✅" : "🚦");
  setText("centerStatus", f.pid ? f.pid : done ? "DONE" : clear ? "ALL RED" : "IDLE");
  setText("centerSub", f.pid ? (emergency ? "EMERGENCY" : f.direction.toUpperCase()) : done ? "ALL TERMINATED" : clear ? "CLEARANCE" : "NO TRAFFIC");
  setText("activeSignal", done ? "All signals red" : clear ? `All red: clearing for ${f.nextDirection}` : idle ? "All signals red"
    : f.manual ? `Manual override: ${f.direction}` : `${emergency ? "🚑 Emergency: " : "Green: "}${f.direction}`);
  const waiting = DIRS.reduce((n, d) => n + f.queues[d].length, 0);
  $("nowBar").className = "now-bar " + (emergency || clear ? "emergency" : done ? "normal" : idle ? "idle" : "normal");
  const pre = f.preempted ? `⚡ Emergency preemption: ${f.preempted.by} interrupts ${f.preempted.pid} (${f.preempted.remaining} unit(s) left). ` : "";
  $("nowBar").textContent = done ? `T=${f.t}: all ${r.metrics.totalVehicles} vehicles are Terminated. Simulation complete.`
    : clear ? `T=${f.t}: ${pre}All signals RED for one unit so two directions are never green together; ${f.nextDirection} goes next. ${waiting} waiting.`
    : idle ? `T=${f.t}: no vehicle can cross right now. ${waiting} waiting.`
    : emergency ? `T=${f.t}: ${pre}Ambulance ${f.pid} ${f.manual ? `crosses ${f.direction} under manual override (signal failed)` : `has priority, ${f.direction} is green`}. ${waiting} waiting.`
    : `T=${f.t}: Round Robin green for ${f.direction}, FCFS serves ${f.pid} (slice left: ${f.quantum_left}). ${waiting} waiting.`;
  // dashboard live indicators
  Object.entries(f.counts).forEach(([k, v]) => setText("state" + k, v));
  setText("liveGreen", done ? "None (all red)" : clear ? "None (all-red clearance)" : f.manual ? `${f.direction} (manual override)` : green || "None (all red)");
  setText("liveRunning", f.pid ? `${f.pid} (${f.type}, ${f.direction})` : "None");
  const phase = {none: "", pending: " (not started)", active: " (ACTIVE)", ended: " (ended, normal operation)"}[f.scenarioPhase] || "";
  setText("liveScenario", r.scenarioLabel + phase);
  setText("liveStatus", done ? `Completed at T=${r.metrics.makespan}: ${r.metrics.completed}/${r.metrics.totalVehicles} Terminated`
    : `${player.timer ? "Running" : "Paused"} at T=${f.t} of ${r.metrics.makespan}`);
  renderResources(f); renderVehicles();
  const ph = $("playhead"); if (ph) ph.style.left = (f.t * U) + "px";
  setLocked(i < last);
  refreshStatus();
}
function pause() { clearInterval(player.timer); player.timer = null; $("playBtn").textContent = "▶"; refreshStatus(); }
function play() {
  if (!player.tl.length) return;
  if (player.i >= player.tl.length - 1) drawFrame(0);
  $("playBtn").textContent = "⏸";
  clearInterval(player.timer);
  player.timer = setInterval(() => {
    if (player.i >= player.tl.length - 1) { pause(); drawFrame(player.i); return; }
    drawFrame(player.i + 1);
  }, Number($("speed").value));
  refreshStatus();
}
function setupPlayer(r) {
  pause(); player.tl = r.timeline || [];
  $("scrub").max = Math.max(0, player.tl.length - 1); $("scrub").disabled = !player.tl.length;
  drawFrame(0); play();
}
function resetPlayer() {
  pause(); player.tl = []; player.i = 0;
  $("scrub").value = 0; $("scrub").max = 0; $("scrub").disabled = true;
  setText("clock", "T = 0"); setText("centerIcon", "🚦"); setText("centerStatus", "READY"); setText("centerSub", "INTERSECTION");
  $("centerBox").classList.remove("emergency", "idle");
  DIRS.forEach(d => {
    $("queue" + d).innerHTML = ""; setLight(d, "");
    const lane = $("lane" + d); lane.textContent = d.toUpperCase(); lane.classList.remove("blocked", "failed");
  });
  document.querySelectorAll("#rrRing [data-d]").forEach(s => s.classList.remove("on"));
  $("nowBar").className = "now-bar"; $("nowBar").textContent = "Run a simulation, then press play to watch the signals rotate.";
  setText("activeSignal", "No active signal");
  setText("liveGreen", "—"); setText("liveRunning", "—"); setText("liveStatus", "Not started");
  setStatus("SIMULATOR READY"); setLocked(false);
  setText("stateNew", vehicles.length);
  ["Ready", "Running", "Waiting", "Terminated"].forEach(s => setText("state" + s, 0));
}
$("playBtn").addEventListener("click", () => player.timer ? pause() : play());
$("prevBtn").addEventListener("click", () => { pause(); drawFrame(player.i - 1); });
$("nextBtn").addEventListener("click", () => { pause(); drawFrame(player.i + 1); });
$("scrub").addEventListener("input", e => { pause(); drawFrame(Number(e.target.value)); });
$("speed").addEventListener("change", () => { if (player.timer) play(); });

/* ---------------- initial render ---------------- */
resetPlayer(); renderResources(null); renderVehicles(); updateScenarioLabel();
