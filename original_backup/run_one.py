"""Run ONE simulation and print mean wait time per car.

Examples:
    python run_one.py --controller fixed --n 200
    python run_one.py --controller max_pressure --n 500
    python run_one.py --controller qlearning --n 300 --seed 7

Choices for --controller: fixed, actuated, max_pressure, qlearning
"""
import os
import sys
import argparse
import random
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Make sure SUMO command-line binaries are findable in subprocess calls
os.environ["PATH"] = (os.path.expanduser("~/.local/bin")
                      + os.pathsep + os.environ.get("PATH", ""))

import traci
import sumolib
from controllers import CONTROLLERS

NET_PATH = os.path.join(HERE, "net", "grid3x3.net.xml")
LOAD_WINDOW = 1200       # cars depart uniformly across this window (seconds)
SIM_END = 1800           # simulation hard stop (seconds)


def generate_routes(n, seed, out_path):
    """Make a SUMO route file with `n` random-OD cars over LOAD_WINDOW.
    Origins are round-robined across the 24 grid edges to spread depart load.
    """
    net = sumolib.net.readNet(NET_PATH)
    edges = [e for e in net.getEdges() if not e.getID().startswith(":")]
    rng = random.Random(seed)
    rng.shuffle(edges)

    trips = []
    for i in range(n):
        o = edges[i % len(edges)]
        d = rng.choice(edges)
        for _ in range(10):
            if d.getID() != o.getID():
                break
            d = rng.choice(edges)
        trips.append((rng.uniform(0, LOAD_WINDOW), i, o.getID(), d.getID()))
    trips.sort()

    with tempfile.NamedTemporaryFile("w", suffix=".trips.xml", delete=False) as f:
        trips_path = f.name
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<routes>\n')
        for depart, i, o, d in trips:
            f.write(f'  <trip id="v{i}" depart="{depart:.2f}" '
                    f'from="{o}" to="{d}"/>\n')
        f.write('</routes>\n')

    subprocess.run([
        "duarouter", "-n", NET_PATH, "-r", trips_path, "-o", out_path,
        "--ignore-errors", "true", "--repair", "true",
        "--seed", str(seed), "--no-warnings", "true",
    ], capture_output=True, text=True)
    os.unlink(trips_path)

    # duarouter doesn't preserve depart-time order; SUMO requires sorted vehicles
    tree = ET.parse(out_path)
    root = tree.getroot()
    vehicles = sorted(root.findall("vehicle"),
                      key=lambda v: float(v.get("depart")))
    for v in root.findall("vehicle"):
        root.remove(v)
    for v in vehicles:
        root.append(v)
    tree.write(out_path, xml_declaration=True, encoding="UTF-8")
    return len(vehicles)


def run_trial(controller_name, n, seed,
              qtable_path=None, train=False, eps=None):
    """Run one simulation and return a dict of metrics."""
    workdir = tempfile.mkdtemp(prefix=f"sumo_{controller_name}_n{n}_s{seed}_")
    route_path = os.path.join(workdir, "run.rou.xml")
    cfg_path = os.path.join(workdir, "run.sumocfg")
    tripinfo_path = os.path.join(workdir, "tripinfo.xml")

    placed = generate_routes(n, seed, route_path)

    with open(cfg_path, "w") as f:
        f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <input>
    <net-file value="{NET_PATH}"/>
    <route-files value="{route_path}"/>
  </input>
  <time><begin value="0"/><end value="{SIM_END}"/></time>
  <processing>
    <time-to-teleport value="-1"/>
    <ignore-route-errors value="true"/>
  </processing>
  <report>
    <no-step-log value="true"/>
    <no-warnings value="true"/>
    <duration-log.disable value="true"/>
  </report>
</configuration>
''')

    sumo_cmd = ["sumo", "-c", cfg_path, "--seed", str(seed),
                "--tripinfo-output", tripinfo_path,
                "--no-step-log", "true", "--no-warnings", "true",
                "--max-depart-delay", "120"]

    extra = {}
    if qtable_path: extra["qtable_path"] = qtable_path
    if train:       extra["train"] = True
    if eps is not None: extra["eps"] = eps

    traci.start(sumo_cmd)
    try:
        ctrl = CONTROLLERS[controller_name](**extra)
        ctrl.setup(traci)
        t = 0
        while traci.simulation.getMinExpectedNumber() > 0 and t < SIM_END:
            ctrl.step(t)
            traci.simulationStep()
            t += 1
        ctrl.teardown()
    finally:
        try: traci.close()
        except Exception: pass

    waits, time_loss = [], []
    if os.path.exists(tripinfo_path):
        for ti in ET.parse(tripinfo_path).getroot().findall("tripinfo"):
            waits.append(float(ti.get("waitingTime", 0)))
            time_loss.append(float(ti.get("timeLoss", 0)))

    for p in (route_path, cfg_path, tripinfo_path):
        try: os.unlink(p)
        except OSError: pass
    try: os.rmdir(workdir)
    except OSError: pass

    completed = len(waits)
    return {
        "controller": controller_name, "n": n, "seed": seed,
        "placed": placed, "completed": completed,
        "mwt": sum(waits)/completed if completed else float("nan"),
        "mean_time_loss": sum(time_loss)/completed if completed else float("nan"),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Run one SUMO simulation and report mean wait time per car.")
    ap.add_argument("--controller", required=True, choices=list(CONTROLLERS),
                    help="Which controller to use.")
    ap.add_argument("--n", type=int, required=True,
                    help="Number of cars to spawn over the 1200 s load window.")
    ap.add_argument("--seed", type=int, default=0,
                    help="Random seed for the trip generator.")
    ap.add_argument("--qtable", default=os.path.join(HERE, "results", "qtable.pkl"),
                    help="Path to Q-learning table (only used if controller=qlearning).")
    args = ap.parse_args()

    qpath = args.qtable if args.controller == "qlearning" else None
    if args.controller == "qlearning" and not os.path.exists(qpath):
        print(f"WARNING: no Q-table found at {qpath} -- using untrained policy.\n"
              f"Run `python run_all.py` first to train.\n")

    res = run_trial(args.controller, args.n, args.seed, qtable_path=qpath)
    print()
    print(f"  Controller:   {res['controller']}")
    print(f"  Cars (N):     {res['n']}")
    print(f"  Seed:         {res['seed']}")
    print(f"  Completed:    {res['completed']}/{res['placed']}")
    print(f"  MEAN WAIT TIME PER CAR:  {res['mwt']:.2f} s")
    print(f"  Mean time loss:          {res['mean_time_loss']:.2f} s")
