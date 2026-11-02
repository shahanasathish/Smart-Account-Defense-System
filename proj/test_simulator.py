"""Run with:  python -m unittest -v test_simulator"""
import unittest
from simulator import run_simulation


def V(pid, typ, d, arr, svc):
    return {"pid": pid, "type": typ, "direction": d, "arrival": arr, "service": svc}


SAMPLE = [V("P01", "Car", "North", 0, 5), V("P02", "Bike", "East", 1, 3), V("P03", "Bus", "South", 2, 4),
          V("P04", "Ambulance", "West", 3, 2), V("P05", "Car", "North", 4, 3), V("P06", "Truck", "East", 5, 6)]


def run(vehicles, **kw):
    return run_simulation({"vehicles": vehicles, "quantum": 2, "laneCapacity": 4, **kw})


def row(r, pid):
    return next(x for x in r["vehicles"] if x["pid"] == pid)


class Invariants(unittest.TestCase):
    """Properties that must hold for EVERY scenario."""

    def check(self, r):
        for f in r["timeline"]:
            greens = [d for d, s in f["signals"].items() if s == "green"]
            self.assertLessEqual(len(greens), 1, f"two greens at T={f['t']}")
            for d in f["failed"]:
                self.assertNotEqual(f["signals"][d], "green")
            if f["pid"]:
                self.assertNotIn(f["direction"], f["blocked"])
        for v in r["vehicles"]:
            self.assertEqual(v["state"], "Terminated")
            self.assertEqual(v["waiting"], v["turnaround"] - v["service"])
            self.assertEqual(v["response"], v["start"] - v["arrival"])
        last = r["timeline"][-1]
        self.assertEqual(last["mode"], "done")
        self.assertIsNone(last["pid"])
        self.assertEqual(last["counts"]["Terminated"], len(r["vehicles"]))
        # gantt covers every busy unit exactly once, no overlap
        t = 0
        for g in r["gantt"]:
            self.assertEqual(g["start"], t)
            t = g["end"]
        self.assertEqual(t, r["metrics"]["makespan"])
        self.assertEqual(r["metrics"]["greenConflicts"], 0)

    def test_all_scenarios(self):
        for sc in ("normal", "congestion", "ambulance", "accident", "signal_failure"):
            for aff in ("North", "East", "West"):
                with self.subTest(scenario=sc, affected=aff):
                    self.check(run(SAMPLE, scenario=sc, affectedDirection=aff))


class Scheduling(unittest.TestCase):
    def test_fcfs_within_direction(self):
        r = run([V("P01", "Car", "North", 0, 1), V("P02", "Car", "North", 2, 1), V("P03", "Car", "North", 4, 1)])
        self.assertEqual([row(r, p)["start"] for p in ("P01", "P02", "P03")], [0, 2, 4])

    def test_fcfs_tiebreak_is_input_order_not_pid_text(self):
        r = run([V("P10", "Car", "North", 0, 1), V("P2", "Car", "North", 0, 1)])
        self.assertLess(row(r, "P10")["start"], row(r, "P2")["start"])

    def test_no_overtaking_in_queue_with_round_robin(self):
        r = run([V("A", "Car", "North", 0, 5), V("B", "Car", "North", 1, 1), V("C", "Car", "South", 0, 5)])
        self.assertLess(row(r, "A")["completion"], row(r, "B")["start"] + 1)

    def test_round_robin_quantum_and_skip_empty(self):
        r = run([V("P01", "Car", "North", 0, 3), V("P02", "Car", "South", 0, 2), V("P03", "Car", "West", 0, 1)])
        seq = [(g["pid"], g["start"], g["end"]) for g in r["gantt"]]
        # N(2) -> S(2) -> (East empty, skipped) W(1) -> N(1)
        self.assertEqual(seq, [("P01", 0, 2), ("P02", 2, 4), ("P03", 4, 5), ("P01", 5, 6)])

    def test_green_never_longer_than_remaining_service(self):
        r = run([V("P01", "Car", "North", 0, 1), V("P02", "Car", "South", 0, 1)], quantum=5)
        self.assertEqual([(g["pid"], g["start"], g["end"]) for g in r["gantt"]], [("P01", 0, 1), ("P02", 1, 2)])

    def test_rotation_resets_each_run(self):
        a = run(SAMPLE)
        b = run(SAMPLE)
        self.assertEqual(a["gantt"], b["gantt"])


class Emergency(unittest.TestCase):
    def test_ambulance_preempts_and_normal_resumes(self):
        r = run([V("P01", "Car", "North", 0, 6), V("AMB", "Ambulance", "North", 1, 2)])
        self.assertEqual(row(r, "AMB")["start"], 1)           # same direction: no clearance needed
        self.assertEqual(row(r, "AMB")["response"], 0)
        p1 = row(r, "P01")
        self.assertEqual(p1["completion"], 8)
        self.assertEqual(p1["waiting"], 2)                     # waiting from full history
        self.assertEqual(r["metrics"]["preemptions"], 1)
        blocks = [(g["pid"], g["start"], g["end"]) for g in r["gantt"]]
        self.assertEqual(blocks[:3], [("P01", 0, 1), ("AMB", 1, 3), ("P01", 3, 8)])

    def test_clearance_between_conflicting_directions(self):
        r = run([V("P01", "Car", "North", 0, 6), V("AMB", "Ambulance", "West", 1, 2)])
        kinds = [g["kind"] for g in r["gantt"][:3]]
        self.assertEqual(kinds, ["normal", "clearance", "ambulance"])
        self.assertEqual(row(r, "AMB")["response"], 1)          # NOT always zero
        self.assertEqual(r["metrics"]["emergencyResponse"], 1)
        clear = r["timeline"][1]
        self.assertTrue(all(s != "green" for s in clear["signals"].values()))

    def test_ambulances_fcfs(self):
        r = run([V("A2", "Ambulance", "South", 1, 2), V("A1", "Ambulance", "West", 0, 3), V("N", "Car", "North", 0, 1)])
        self.assertLess(row(r, "A1")["completion"], row(r, "A2")["start"] + 1)
        self.assertLess(row(r, "A1")["start"], row(r, "A2")["start"])
        self.assertLess(row(r, "A2")["completion"], row(r, "N")["start"] + 1)

    def test_vehicle_not_running_while_waiting(self):
        r = run([V("P01", "Car", "North", 0, 3), V("P02", "Car", "South", 0, 3)])
        f0 = r["timeline"][0]
        self.assertEqual(f0["states"]["P01"], "Running")
        self.assertEqual(f0["states"]["P02"], "Waiting")
        self.assertEqual(r["timeline"][-1]["states"]["P01"], "Terminated")


class Scenarios(unittest.TestCase):
    def test_accident_blocks_and_diverts_then_restores(self):
        r = run(SAMPLE, scenario="accident", affectedDirection="East", scenarioStart=1, scenarioDuration=6)
        for f in r["timeline"]:
            if 1 <= f["t"] < 7 and f["pid"]:
                self.assertNotEqual(f["direction"], "East")
        self.assertTrue(row(r, "P02")["detour"])
        msgs = " ".join(e["message"] for e in r["events"])
        self.assertIn("SCENARIO START", msgs)
        self.assertIn("SCENARIO END", msgs)
        # after the window East is usable again for new arrivals
        late = run([V("X", "Car", "North", 0, 1), V("Y", "Car", "East", 9, 1)], scenario="accident",
                   affectedDirection="East", scenarioStart=1, scenarioDuration=3)
        self.assertFalse(row(late, "Y")["detour"])
        self.assertEqual(row(late, "Y")["direction"], "East")

    def test_signal_failure_never_green(self):
        r = run(SAMPLE, scenario="signal_failure", affectedDirection="East", scenarioStart=0, scenarioDuration=8)
        for f in r["timeline"]:
            if 0 <= f["t"] < 8:
                self.assertNotEqual(f["signals"]["East"], "green")
        self.assertGreaterEqual(row(r, "P02")["start"], 8)     # East vehicles wait for the repair

    def test_congestion_adds_vehicles_and_queue(self):
        base = run(SAMPLE)
        c = run(SAMPLE, scenario="congestion", scenarioStart=1, scenarioDuration=5)
        self.assertEqual(len(c["vehicles"]), len(SAMPLE) + 10)
        self.assertGreater(c["metrics"]["maxQueue"], base["metrics"]["maxQueue"])

    def test_ambulance_scenario_injects_ambulance(self):
        r = run([V("P01", "Car", "North", 0, 6)], scenario="ambulance", affectedDirection="West", scenarioStart=2)
        amb = row(r, "AMB-01")
        self.assertEqual(amb["type"], "Ambulance")
        self.assertGreaterEqual(amb["response"], 0)


class Resources(unittest.TestCase):
    def test_capacity_exceeded_warning_and_release(self):
        cars = [V(f"P{i}", "Car", "North", 0, 1) for i in range(1, 6)]
        r = run(cars, laneCapacity=2)
        self.assertGreater(r["metrics"]["capacityWarnings"], 0)
        self.assertTrue(any(f["resources"][0]["status"] == "CAPACITY EXCEEDED" for f in r["timeline"]))
        self.assertEqual(r["timeline"][-1]["resources"][0]["allocated"], 0)
        self.assertEqual(r["timeline"][0]["resources"][0]["allocated"], 2)
        kinds = {e["kind"] for e in r["events"]}
        self.assertTrue({"request", "allocate", "release", "warning"} <= kinds)


class Validation(unittest.TestCase):
    def bad(self, **change):
        v = {**V("P01", "Car", "North", 0, 3), **change}
        with self.assertRaises(ValueError):
            run([v])

    def test_rejects_bad_input(self):
        self.bad(service=0)
        self.bad(service=-2)
        self.bad(service=2.5)
        self.bad(service="abc")
        self.bad(arrival=-1)
        self.bad(arrival=1.5)
        self.bad(direction="Up")
        self.bad(type="Spaceship")
        self.bad(pid="bad id!")

    def test_duplicate_ids(self):
        with self.assertRaises(ValueError):
            run([V("P01", "Car", "North", 0, 1), V("p01", "Car", "South", 0, 1)])

    def test_auto_ids_and_empty(self):
        r = run([V("", "Car", "North", 0, 1), V("", "Car", "South", 0, 1)])
        self.assertEqual([x["pid"] for x in r["vehicles"]], ["P01", "P02"])
        with self.assertRaises(ValueError):
            run([])


if __name__ == "__main__":
    unittest.main()
