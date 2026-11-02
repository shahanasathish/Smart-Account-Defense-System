# Smart Traffic Control OS Simulator

A Flask-based educational single-intersection simulation that demonstrates process scheduling, queues, resource allocation and traffic-signal management.

## Scheduling policy

Time is discrete (1 tick = 1 time unit) and **only one direction is ever green at a time**.

1. **Ambulance: preemptive priority.**
   - Detected the moment it arrives and served before any normal vehicle.
   - A crossing normal vehicle is interrupted at the next time-unit boundary, keeps its remaining service time and resumes after the emergency.
   - If the ambulance comes from a different direction than the current green, one **all-red clearance** unit is inserted first, so conflicting directions are never green together.
   - Several ambulances are served FCFS by arrival order.
2. **Normal vehicles: FCFS inside each directional queue.** A later vehicle never overtakes an earlier one in the same direction.
3. **Traffic signals: Round Robin** North -> South -> East -> West using the configured time quantum.
   - Empty or disabled directions are skipped.
   - A green is never longer than the remaining service time: when the vehicle finishes, the green is released and the next eligible direction is served (checkbox "Release green when the vehicle finishes"; untick it to let the leftover quantum go to the next vehicle in the same lane).
   - The emergency does not use up the interrupted direction's time slice.
   - The rotation starts fresh on every run.
4. **SJF is not used.**

## Results and metrics

- Start = first execution time, Completion = end of the last execution, Turnaround = completion - arrival, Response = first execution - arrival.
- Waiting is accumulated over the whole execution history (so preemption is counted). It is checked against `turnaround - service` on every run.
- Emergency response = average of (ambulance first service - ambulance arrival). It is non-zero whenever an ambulance had to wait, for example for the all-red clearance or behind another ambulance.
- Signal utilization = time units with a vehicle crossing / total simulated time units.
- Throughput = completed vehicles / total simulated time units.

## Process lifecycle

`New -> Ready / Waiting -> Running -> Terminated`. A vehicle in the green lane that is queued is **Ready**; one facing a red or blocked signal (or waiting for a lane slot) is **Waiting**; only the vehicle crossing is **Running**. States update on every playback frame, and the final frame shows every vehicle **Terminated** with nothing crossing.

## Resource management

Each direction has `capacity` lane slots. A vehicle **requests** a slot when it arrives, is **allocated** one if free, and **releases** it after crossing. If demand is higher than the slots available, a *capacity exceeded* warning is raised and the extra vehicles wait for a free slot (ambulances use an emergency override).

## Scenarios (with start time and duration)

| Scenario | Effect |
| --- | --- |
| Normal traffic | Normal arrivals and signal rotation |
| Heavy congestion | 2 extra cars per time unit are added during the window, so queues grow |
| Ambulance detected | An ambulance (`AMB-01`) is injected on the affected direction at the start time |
| Traffic accident | The affected direction is blocked during the window. Vehicles there are diverted to the least-busy open direction. New arrivals after the window use their normal direction |
| Signal failure | The affected signal never turns green during the window (the other signals keep rotating). An ambulance there is served under manual override |

Every scenario writes START / END entries to the activity log, and normal operation is restored when it ends.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. Run the tests with `python -m unittest -v test_simulator`.

## Input validation

Process ID: unique (case-insensitive) and auto-generated if blank. Vehicle type and direction must come from the lists. Arrival time is a whole number >= 0, service time a whole number >= 1. Validation runs in the browser and again on the server. Vehicle data is locked while a simulation is running, and "Clear vehicles" asks for confirmation.

## CSV export

One file containing: scenario and algorithm details, quantum and capacity, simulation clock and wall-clock start/end, summary metrics, the scheduling results table, the Gantt blocks and the full activity log. It is built from the same data object the page displays, so the numbers always match.

## Project structure

```text
smart-traffic-control/
├── app.py
├── simulator.py
├── test_simulator.py
├── requirements.txt
├── README.md
├── templates/index.html
└── static/{app.js,style.css}
```

## Modelling note

This is a discrete-time educational simulation, not a real traffic controller. It does not connect to sensors, real vehicles or physical signals. Real-world emergency response and signal timing require certified traffic-engineering systems and safety controls.
