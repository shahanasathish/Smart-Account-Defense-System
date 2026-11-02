"""Smart Traffic Control OS simulator (discrete time, 1 tick = 1 time unit).

Scheduling policy
-----------------
1. Ambulance        -> PREEMPTIVE priority. FCFS among ambulances.
                       If a normal vehicle is crossing, it is interrupted at the next
                       time-unit boundary and keeps its remaining service time.
                       If the ambulance comes from a different direction than the
                       one that is green, one all-red CLEARANCE unit is inserted so
                       two conflicting directions are never green together.
2. Normal vehicles  -> FCFS inside each directional queue (nobody overtakes an
                       earlier vehicle of the same direction).
3. Traffic signals  -> Round Robin N -> S -> E -> W, one green direction at a time,
                       up to `quantum` units each, empty/disabled directions skipped.
                       A green is released early when its vehicle finishes (never
                       gives more time than the remaining service time).
SJF / SRTF are NOT used.

Resource model (per direction): REQUEST a lane slot on arrival -> ALLOCATE when a slot
is free -> RELEASE after crossing. Vehicles that cannot get a slot wait (capacity
exceeded warning). Ambulances use an emergency override.
"""
import re
from datetime import datetime

DIRECTIONS = ["North", "South", "East", "West"]
SCENARIOS = {"normal", "congestion", "ambulance", "accident", "signal_failure"}
SCENARIO_LABELS = {
    "normal": "Normal traffic", "congestion": "Heavy congestion",
    "ambulance": "Ambulance detected", "accident": "Traffic accident",
    "signal_failure": "Signal failure",
}
VEHICLE_TYPES = ["Car", "Bike", "Bus", "Truck", "Ambulance", "Fire Engine"]
ALGORITHM = "Ambulance: preemptive priority (FCFS among ambulances) > Normal vehicles: FCFS per direction > Signals: Round Robin"

MAX_VEHICLES, MAX_ARRIVAL, MAX_SERVICE = 200, 1000, 100
MAX_QUANTUM, MAX_CAPACITY, MAX_DURATION = 100, 50, 100
PID_RE = re.compile(r"^[A-Za-z0-9_-]{1,12}$")


def _is_ambulance(job):
    return job["type"].lower() == "ambulance"


def _whole(value, label, lo, hi):
    """Strict whole-number parser (rejects 2.5, 'abc', True, None, out of range)."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a whole number.")
    if isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"-?\d+", text):
            raise ValueError(f"{label} must be a whole number.")
        value = int(text)
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{label} must be a whole number.")
        value = int(value)
    elif not isinstance(value, int):
        raise ValueError(f"{label} must be a whole number.")
    if value < lo or value > hi:
        raise ValueError(f"{label} must be between {lo} and {hi}.")
    return value


def _direction(value, label):
    d = str(value).strip().title()
    if d not in DIRECTIONS:
        raise ValueError(f"{label} must be North, South, East or West.")
    return d


def _make_job(pid, kind, direction, arrival, burst, seq, generated=False):
    return {
        "pid": pid, "type": kind, "direction": direction, "origin": direction,
        "arrival": arrival, "burst": burst, "remaining": burst, "seq": seq,
        "state": "New", "start": None, "completion": None, "waiting": 0, "response": None,
        "arrived": False, "allocated": False, "requested_in": None, "denied_in": None,
        "detour": False, "generated": generated,
    }


def _validate(data):
    scenario = str(data.get("scenario", "normal")).strip().lower()
    if scenario not in SCENARIOS:
        raise ValueError("Unknown traffic scenario.")
    cfg = {
        "scenario": scenario,
        "quantum": _whole(data.get("quantum", 2), "Signal time quantum", 1, MAX_QUANTUM),
        "capacity": _whole(data.get("laneCapacity", 4), "Lane capacity", 1, MAX_CAPACITY),
        "release_on_finish": bool(data.get("releaseOnFinish", True)),
        "affected": _direction(data.get("affectedDirection", "East"), "Affected direction"),
        "start": _whole(data.get("scenarioStart", 2), "Scenario start time", 0, MAX_ARRIVAL),
        "duration": _whole(data.get("scenarioDuration", 6), "Scenario duration", 1, MAX_DURATION),
    }
    raw = data.get("vehicles", [])
    if not isinstance(raw, list) or not raw:
        raise ValueError("Add at least one vehicle before running the simulation.")
    if len(raw) > MAX_VEHICLES:
        raise ValueError(f"At most {MAX_VEHICLES} vehicles are supported.")

    explicit = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each vehicle must be an object.")
        pid = str(item.get("pid") or "").strip()
        if pid:
            if not PID_RE.match(pid):
                raise ValueError(f"Process ID '{pid}' may only use letters, digits, - and _ (max 12 characters).")
            if pid.lower() in explicit:
                raise ValueError(f"Duplicate process ID: {pid}.")
            explicit.add(pid.lower())

    jobs, used, auto = [], set(explicit), 0
    for seq, item in enumerate(raw):
        pid = str(item.get("pid") or "").strip()
        if not pid:
            while True:
                auto += 1
                pid = f"P{auto:02d}"
                if pid.lower() not in used:
                    break
            used.add(pid.lower())
        kind = next((t for t in VEHICLE_TYPES if t.lower() == str(item.get("type", "Car")).strip().lower()), None)
        if kind is None:
            raise ValueError(f"Invalid vehicle type for {pid}.")
        direction = _direction(item.get("direction", "North"), f"Direction of {pid}")
        arrival = _whole(item.get("arrival"), f"Arrival time of {pid}", 0, MAX_ARRIVAL)
        burst = _whole(item.get("service"), f"Service time of {pid}", 1, MAX_SERVICE)
        jobs.append(_make_job(pid, kind, direction, arrival, burst, seq))
    cfg["_used"] = used
    return cfg, jobs


def run_simulation(data):
    started = datetime.now().astimezone()
    cfg, jobs = _validate(data)
    scenario, quantum, capacity = cfg["scenario"], cfg["quantum"], cfg["capacity"]
    release_on_finish, affected = cfg["release_on_finish"], cfg["affected"]
    s_start, s_end = cfg["start"], cfg["start"] + cfg["duration"]
    used = cfg["_used"]
    windowed = scenario in ("congestion", "accident", "signal_failure")

    def unique_pid(base):
        pid, n = base, 1
        while pid.lower() in used:
            n += 1
            pid = f"{base}-{n}"
        used.add(pid.lower())
        return pid

    seq = len(jobs)
    injected_amb = None
    if scenario == "congestion":          # more arrivals -> longer queues
        for k in range(cfg["duration"]):
            for j in range(2):
                idx = 2 * k + j
                jobs.append(_make_job(unique_pid(f"C{idx + 1:02d}"), "Car", DIRECTIONS[idx % 4],
                                      s_start + k, 1 + idx % 2, seq, generated=True))
                seq += 1
    elif scenario == "ambulance":         # an ambulance is detected on the affected approach
        injected_amb = _make_job(unique_pid("AMB-01"), "Ambulance", affected, s_start, 2, seq, generated=True)
        jobs.append(injected_amb)

    jobs.sort(key=lambda j: (j["arrival"], j["seq"]))
    max_time = (max(j["arrival"] for j in jobs) + sum(j["burst"] for j in jobs)
                + (s_end if windowed else 0) + len(jobs) + 20)

    events, frames, preemptions = [], [], []
    holding = {d: [] for d in DIRECTIONS}
    time = 0
    active_direction, quantum_left, cursor = None, 0, -1
    prev_job, prev_mode, prev_green = None, "idle", None
    capacity_warnings = 0
    scen_started = scen_ended = False

    def log(kind, msg, t=None):
        events.append({"time": time if t is None else t, "kind": kind, "message": msg})

    def alive(j):
        return j["arrived"] and j["remaining"] > 0

    def all_done():
        return all(j["remaining"] == 0 for j in jobs)

    def divert(j, blocked_set):
        old = j["direction"]
        options = [d for d in DIRECTIONS if d not in blocked_set]
        load = lambda d: sum(1 for x in jobs if alive(x) and x["direction"] == d)
        new = min(options, key=lambda d: (load(d), (DIRECTIONS.index(d) - DIRECTIONS.index(old)) % 4))
        if j["allocated"]:
            holding[old].remove(j)
            j["allocated"] = False
            log("release", f'RELEASE: {j["pid"]} gives up its {old} lane slot (road blocked).')
        j["direction"], j["detour"] = new, True
        log("divert", f'DIVERT: {j["pid"]} ({j["type"]}) rerouted from blocked {old} to {new}.')

    def choose_normal(normal, disabled):
        nonlocal active_direction, quantum_left, cursor
        if active_direction in disabled:
            log("signal", f"Round Robin: {active_direction} is disabled, green revoked.")
            active_direction, quantum_left = None, 0
        if active_direction is not None and quantum_left > 0:
            same = [j for j in normal if j["direction"] == active_direction]
            if same:
                return min(same, key=lambda j: (j["arrival"], j["seq"]))
            log("signal", f"Round Robin: {active_direction} queue is empty, green released early.")
            active_direction, quantum_left = None, 0
        for offset in range(1, len(DIRECTIONS) + 1):
            idx = (cursor + offset) % len(DIRECTIONS)
            d = DIRECTIONS[idx]
            if d in disabled:
                continue
            cands = [j for j in normal if j["direction"] == d]
            if cands:
                cursor, active_direction, quantum_left = idx, d, quantum
                log("signal", f"Round Robin: signal turns GREEN for {d} (up to {quantum} time units). All other signals RED.")
                return min(cands, key=lambda j: (j["arrival"], j["seq"]))
        return None

    log("info", f"Simulation started. Policy: {ALGORITHM}.")
    if scenario != "normal":
        log("scenario", f"Selected scenario: {SCENARIO_LABELS[scenario]}.")

    while time < max_time and not all_done():
        # ---- scenario window markers -------------------------------------------------
        if windowed and time == s_start and not scen_started:
            scen_started = True
            msgs = {
                "congestion": f"SCENARIO START: heavy congestion, {cfg['duration'] * 2} extra vehicles arrive between T={s_start} and T={s_end}.",
                "accident": f"SCENARIO START: accident on the {affected} approach until T={s_end}. {affected} is BLOCKED and traffic is diverted.",
                "signal_failure": f"SCENARIO START: {affected} signal FAILED until T={s_end}. It cannot show green; the other signals keep rotating (alternate control).",
            }
            log("scenario", msgs[scenario])
        if windowed and time == s_end and scen_started and not scen_ended:
            scen_ended = True
            log("scenario", f"SCENARIO END: {SCENARIO_LABELS[scenario]} cleared. Normal operation restored.")
        if scenario == "ambulance" and time == s_start:
            log("scenario", f"SCENARIO START: ambulance detected on {affected}. Route clearance requested.")

        in_window = windowed and s_start <= time < s_end
        blocked_now = {affected} if scenario == "accident" and in_window else set()
        failed_now = {affected} if scenario == "signal_failure" and in_window else set()
        disabled = blocked_now | failed_now

        # ---- arrivals (new -> ready) ----------------------------------------------------
        for j in jobs:
            if j["arrival"] == time and not j["arrived"]:
                j["arrived"], j["state"] = True, "Ready"
                tag = " (auto-generated)" if j["generated"] else ""
                log("arrival", f'{j["pid"]} ({j["type"]}) arrived from {j["direction"]}{tag}.')
                if _is_ambulance(j):
                    log("emergency", f'EMERGENCY DETECTED: {j["pid"]} on {j["direction"]}. It gets priority over every normal vehicle.')

        # ---- accident: nobody may enter the blocked direction -------------------------------
        if blocked_now:
            for j in jobs:
                if alive(j) and j["direction"] in blocked_now:
                    divert(j, blocked_now)

        # ---- resource request -> allocation ---------------------------------------------------
        for j in jobs:
            if alive(j) and j["requested_in"] != j["direction"]:
                j["requested_in"] = j["direction"]
                log("request", f'REQUEST: {j["pid"]} requests a {j["direction"]} lane slot.')
        for d in DIRECTIONS:
            pending = sorted((j for j in jobs if alive(j) and j["direction"] == d and not j["allocated"]),
                             key=lambda j: (not _is_ambulance(j), j["arrival"], j["seq"]))
            for j in pending:
                if len(holding[d]) < capacity:
                    holding[d].append(j)
                    j["allocated"] = True
                    log("allocate", f'ALLOCATE: {j["pid"]} granted a {d} lane slot ({len(holding[d])}/{capacity}).')
                elif _is_ambulance(j):
                    holding[d].append(j)
                    j["allocated"] = True
                    capacity_warnings += 1
                    log("warning", f'CAPACITY EXCEEDED: {d} lane is full ({capacity}). {j["pid"]} (ambulance) is granted a slot by emergency override.')
                elif j["denied_in"] != d:
                    j["denied_in"] = d
                    capacity_warnings += 1
                    log("warning", f'CAPACITY EXCEEDED: {d} lane is full ({capacity}). {j["pid"]} waits for a free slot.')

        # ---- scheduling decision ----------------------------------------------------------------
        ready = [j for j in jobs if alive(j) and j["allocated"]]
        ambs = [j for j in ready if _is_ambulance(j)]
        normal = [j for j in ready if not _is_ambulance(j) and j["direction"] not in disabled]
        job, mode, manual, amb, next_dir = None, "idle", False, None, None
        if ambs:
            amb = min(ambs, key=lambda j: (j["arrival"], j["seq"]))      # FCFS among ambulances
            if prev_green is not None and prev_green != amb["direction"]:
                mode, next_dir = "clearance", amb["direction"]           # all-red gap, no conflicting greens
                log("emergency", f'EMERGENCY CLEARANCE: all signals RED for 1 unit so {prev_green} and {amb["direction"]} are never green together.')
            else:
                job, mode = amb, "emergency"
                manual = amb["direction"] in failed_now
                if amb["start"] is None:
                    how = "MANUAL OVERRIDE (signal failed)" if manual else "GREEN"
                    log("emergency", f'ROUTE CLEARANCE: {amb["pid"]} (Ambulance) served now, {amb["direction"]} {how}, all other directions RED.')
            if (mode in ("emergency", "clearance") and prev_mode == "normal"
                    and prev_job is not None and prev_job["remaining"] > 0):
                preemptions.append({"time": time, "ambulance": amb["pid"], "preempted": prev_job["pid"],
                                    "remaining": prev_job["remaining"]})
                log("emergency", f'EMERGENCY PREEMPTION: {amb["pid"]} preempts {prev_job["pid"]} '
                                 f'({prev_job["remaining"]} unit(s) of service kept, it resumes after the emergency).')
        elif normal:
            job = choose_normal(normal, disabled)
            mode = "normal" if job else "idle"
        else:
            if active_direction is not None:
                active_direction, quantum_left = None, 0

        if mode == "idle" and prev_mode != "idle":
            log("idle", "Intersection is idle (no vehicle can cross right now).")

        # ---- signals (never more than one green) ---------------------------------------------------
        signals = {d: "red" for d in DIRECTIONS}
        green_dir = None
        if job is not None:
            if manual:
                signals[job["direction"]] = "amber"
            else:
                signals[job["direction"]] = "green"
                green_dir = job["direction"]
        for d in failed_now:
            if d != green_dir:
                signals[d] = "amber"          # flashing / out of service, never green
        assert sum(1 for s in signals.values() if s == "green") <= 1, "two directions green"
        assert not any(signals[d] == "green" for d in failed_now), "failed signal turned green"

        # ---- per-tick snapshot (state BEFORE this unit is served) ------------------------------------
        states = {}
        for j in jobs:
            if j["arrival"] > time:
                states[j["pid"]] = "New"
            elif j["remaining"] == 0:
                states[j["pid"]] = "Terminated"
            elif j is job:
                states[j["pid"]] = "Running"
            elif j["allocated"] and green_dir is not None and j["direction"] == green_dir:
                states[j["pid"]] = "Ready"
            else:
                states[j["pid"]] = "Waiting"
        counts = {s: sum(1 for v in states.values() if v == s)
                  for s in ("New", "Ready", "Running", "Waiting", "Terminated")}
        queues = {d: [] for d in DIRECTIONS}
        for j in sorted((x for x in jobs if alive(x) and x is not job),
                        key=lambda x: (not _is_ambulance(x), x["arrival"], x["seq"])):
            queues[j["direction"]].append({"pid": j["pid"], "type": j["type"], "pending": not j["allocated"]})
        resources = []
        for d in DIRECTIONS:
            demand = sum(1 for j in jobs if alive(j) and j["direction"] == d)
            allocated = len(holding[d])
            if d in blocked_now:
                status = "BLOCKED"
            elif d in failed_now:
                status = "SIGNAL FAILED"
            elif demand > allocated or allocated > capacity:
                status = "CAPACITY EXCEEDED"
            else:
                status = "OK"
            resources.append({"direction": d, "capacity": capacity, "allocated": allocated,
                              "available": max(0, capacity - allocated), "demand": demand, "status": status})
        if scenario == "normal":
            phase = "none"
        elif scenario == "ambulance":
            phase = "pending" if time < s_start else ("ended" if injected_amb["remaining"] == 0 else "active")
        else:
            phase = "pending" if time < s_start else ("active" if time < s_end else "ended")
        preempted_now = None
        if mode in ("emergency", "clearance") and prev_mode == "normal" and prev_job and prev_job["remaining"] > 0:
            preempted_now = {"pid": prev_job["pid"], "remaining": prev_job["remaining"], "by": amb["pid"]}
        frames.append({
            "t": time, "mode": mode, "manual": manual,
            "pid": job["pid"] if job else None, "type": job["type"] if job else None,
            "direction": job["direction"] if job else None, "nextDirection": next_dir,
            "remainingBefore": job["remaining"] if job else None,
            "quantum_left": quantum_left if mode == "normal" else None,
            "signals": signals, "blocked": sorted(blocked_now), "failed": sorted(failed_now),
            "queues": queues, "states": states, "counts": counts, "resources": resources,
            "scenarioPhase": phase, "preempted": preempted_now,
        })

        # ---- serve one time unit -------------------------------------------------------------------------
        for j in jobs:
            if alive(j) and j is not job:
                j["waiting"] += 1             # waiting accumulates over the whole history (preemption safe)
        if job is not None:
            if job["start"] is None:
                job["start"] = time
                job["response"] = time - job["arrival"]
            job["remaining"] -= 1
            job["state"] = "Running"
        time += 1
        if job is not None:
            if job["remaining"] == 0:
                job["completion"], job["state"] = time, "Terminated"
                holding[job["direction"]].remove(job)
                job["allocated"] = False
                log("complete", f'{job["pid"]} completed service and is TERMINATED.', time)
                log("release", f'RELEASE: {job["pid"]} released its {job["direction"]} lane slot '
                               f'({len(holding[job["direction"]])}/{capacity} in use).', time)
                if job is injected_amb:
                    log("scenario", "SCENARIO END: ambulance cleared the intersection. Normal operation restored.", time)
                if mode == "normal" and release_on_finish and active_direction is not None:
                    log("signal", f"Round Robin: {active_direction} vehicle finished, green released, next eligible direction is served.", time)
                    active_direction, quantum_left = None, 0
            else:
                job["state"] = "Ready"
            if mode == "normal" and active_direction is not None:
                quantum_left -= 1
                if quantum_left <= 0:
                    log("signal", f"Round Robin: time slice over for {active_direction}, rotating signal.", time)
                    active_direction, quantum_left = None, 0
        prev_job, prev_mode = job, mode
        prev_green = job["direction"] if job is not None else None

    if not all_done():
        raise ValueError("Simulation did not finish. Check vehicle inputs.")

    # ---- final frame: everything terminated, nothing crossing -------------------------------------------------
    makespan = time
    frames.append({
        "t": time, "mode": "done", "manual": False, "pid": None, "type": None, "direction": None,
        "nextDirection": None, "remainingBefore": None, "quantum_left": None,
        "signals": {d: "red" for d in DIRECTIONS}, "blocked": [], "failed": [],
        "queues": {d: [] for d in DIRECTIONS},
        "states": {j["pid"]: "Terminated" for j in jobs},
        "counts": {"New": 0, "Ready": 0, "Running": 0, "Waiting": 0, "Terminated": len(jobs)},
        "resources": [{"direction": d, "capacity": capacity, "allocated": 0, "available": capacity,
                       "demand": 0, "status": "OK"} for d in DIRECTIONS],
        "scenarioPhase": "none" if scenario == "normal" else "ended", "preempted": None,
    })
    if windowed and scen_started and not scen_ended:
        log("scenario", f"SCENARIO END: {SCENARIO_LABELS[scenario]} window closed. Normal operation restored.", time)
    elif windowed and not scen_started:
        log("scenario", f"{SCENARIO_LABELS[scenario]} never became active (all vehicles finished before T={s_start}).", time)
    log("info", f"Simulation finished at time {makespan}. All vehicles TERMINATED.", time)

    # ---- Gantt chart built from the frames ----------------------------------------------------------------------
    kind_of = {"emergency": "ambulance", "normal": "normal", "idle": "idle", "clearance": "clearance"}
    gantt = []
    for f in frames[:-1]:
        pid = f["pid"] or ("CLEAR" if f["mode"] == "clearance" else "IDLE")
        kind = kind_of[f["mode"]]
        if gantt and gantt[-1]["pid"] == pid and gantt[-1]["kind"] == kind and gantt[-1]["end"] == f["t"] and not f["preempted"]:
            gantt[-1]["end"] = f["t"] + 1
        else:
            block = {"pid": pid, "kind": kind, "start": f["t"], "end": f["t"] + 1, "type": f["type"],
                     "direction": f["direction"] or f["nextDirection"], "preempts": None,
                     "interrupted": False, "manual": f["manual"]}
            if f["preempted"]:
                block["preempts"] = f["preempted"]["pid"]
                for g in reversed(gantt):
                    if g["pid"] == f["preempted"]["pid"]:
                        g["interrupted"] = True
                        break
            gantt.append(block)

    # ---- result rows and metrics --------------------------------------------------------------------------------------
    rows = []
    for j in jobs:
        turnaround = j["completion"] - j["arrival"]
        assert j["waiting"] == turnaround - j["burst"], "waiting time must equal turnaround - service"
        rows.append({
            "pid": j["pid"], "type": j["type"], "direction": j["direction"], "origin": j["origin"],
            "arrival": j["arrival"], "service": j["burst"], "state": "Terminated",
            "start": j["start"], "completion": j["completion"], "waiting": j["waiting"],
            "turnaround": turnaround, "response": j["response"],
            "detour": j["detour"], "generated": j["generated"],
        })
    n = len(rows)
    avg_wait = round(sum(r["waiting"] for r in rows) / n, 2)
    busy = sum(1 for f in frames[:-1] if f["pid"])
    throughput = round(n / makespan, 3) if makespan else 0
    signal_util = round(busy / makespan * 100, 2) if makespan else 0
    amb_rows = [r for r in rows if r["type"].lower() == "ambulance"]
    emergency = round(sum(r["response"] for r in amb_rows) / len(amb_rows), 2) if amb_rows else None
    max_queue = max(sum(len(q) for q in f["queues"].values()) for f in frames)
    green_conflicts = sum(1 for f in frames if sum(1 for s in f["signals"].values() if s == "green") > 1)
    direction_stats = {}
    for d in DIRECTIONS:
        direction_stats[d] = {
            "vehicles": sum(1 for r in rows if r["origin"] == d),
            "served": sum(1 for r in rows if r["direction"] == d),
            "maxQueue": max(len(f["queues"][d]) for f in frames),
        }
    finished = datetime.now().astimezone()
    return {
        "algorithm": ALGORITHM, "scenario": scenario, "scenarioLabel": SCENARIO_LABELS[scenario],
        "quantum": quantum,
        "config": {"quantum": quantum, "laneCapacity": capacity, "releaseOnFinish": release_on_finish,
                   "affectedDirection": affected if scenario in ("accident", "signal_failure", "ambulance") else None,
                   "scenarioStart": s_start if scenario != "normal" else None,
                   "scenarioEnd": s_end if windowed else None},
        "startedAt": started.isoformat(timespec="seconds"),
        "finishedAt": finished.isoformat(timespec="seconds"),
        "gantt": gantt, "timeline": frames, "vehicles": rows, "events": events,
        "states": frames[-1]["counts"], "preemptions": preemptions,
        "metrics": {
            "averageWaiting": avg_wait, "maxQueue": max_queue, "throughput": throughput,
            "signalUtilization": signal_util, "emergencyResponse": emergency,
            "emergencyResponseById": {r["pid"]: r["response"] for r in amb_rows},
            "completed": n, "totalVehicles": n, "makespan": makespan,
            "preemptions": len(preemptions), "capacityWarnings": capacity_warnings,
            "greenConflicts": green_conflicts, "directionStats": direction_stats,
        },
        "resources": frames[-1]["resources"],
        "signal": {"activeDirection": None, "failedDirection": affected if scenario == "signal_failure" else None,
                   "blockedDirection": affected if scenario == "accident" else None,
                   "alternateControl": scenario == "signal_failure"},
        "notes": [
            "Ambulance: preemptive priority, FCFS among ambulances.",
            "Normal vehicles: FCFS inside each directional queue.",
            "Traffic signals: Round Robin N, S, E, W with the configured time quantum.",
            "SJF is not used anywhere.",
        ],
    }
