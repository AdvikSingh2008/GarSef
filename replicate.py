"""Reproduce the paper's experimental grid, with explicitly reconstructed PGQL.

Run using .venv/Scripts/python.exe replicate.py. No legacy results are reused.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from run_one import run_trial, traci

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'replication_results'
LOADS = [50, 100, 200, 300, 450, 600, 800, 1000, 1300, 1700]
CONTROLLERS = ['fixed', 'actuated', 'max_pressure', 'qlearning', 'pgql']


def train(controller):
    episodes = 20 if controller == 'qlearning' else 16
    qpath = OUT / (controller + '_fresh.pkl')
    done = OUT / (controller + '_training.json')
    if done.exists() and qpath.exists():
        return json.loads(done.read_text())
    # A partial training sequence must restart to remain reproducible.
    if qpath.exists():
        qpath.unlink()
    rows = []
    for ep in range(episodes):
        eps = 0.30 + (0.05 - 0.30) * ep / (episodes - 1)
        row = run_trial(controller, [150, 250, 400, 600, 800][ep % 5],
                        1000 + ep, str(qpath), train=True, eps=eps)
        row.update(episode=ep, epsilon=eps)
        rows.append(row)
    done.write_text(json.dumps(rows, indent=2))
    return rows


def evaluate(task):
    controller, n, seed = task
    qpath = str(OUT / (controller + '_fresh.pkl')) if controller in ('qlearning','pgql') else None
    result = run_trial(controller, n, seed, qpath, eps=0.02 if qpath else None)
    path = OUT / 'trials' / f'{controller}_{n}_{seed}.json'
    path.write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    (OUT / 'trials').mkdir(exist_ok=True)
    manifest = {
        'simulator': traci.getVersion(),
        'packages': {p: importlib.metadata.version(p) for p in
                     ['eclipse-sumo','sumo-data','libsumo','traci','sumolib','numpy','scipy','matplotlib']},
        'seeds': list(range(10)), 'loads': LOADS, 'controllers': CONTROLLERS,
        'training_seeds': '1000 + episode, independently for each learner',
        'training_loads': [150,250,400,600,800],
        'training_episodes': {'qlearning':20,'pgql':16},
        'training_epsilon': 'linear 0.30 to 0.05 inclusive (paper specification)',
        'evaluation_epsilon': 0.02,
        'occupancy_window': 'integer simulation times 200 through 1400 inclusive; zeros after early completion',
        'pgql': 'Reconstructed from manuscript; action 2 chooses the non-expert green',
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ROOT/'run_one.py', ROOT/'replicate.py', ROOT/'net/grid3x3.net.xml',
                                    *sorted((ROOT/'controllers').glob('*.py'))]},
    }
    mf = OUT/'manifest.json'
    if mf.exists() and json.loads(mf.read_text()) != manifest:
        raise RuntimeError('Experiment settings/source changed. Use a new output directory instead of mixing trials.')
    mf.write_text(json.dumps(manifest, indent=2))
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(train,c) for c in ['qlearning','pgql']]):
            rows = future.result()
            print(f"Training complete: {rows[0]['controller']} ({len(rows)} episodes), {time.monotonic()-start:.0f}s",flush=True)
        tasks = [(c,n,s) for c in CONTROLLERS for n in LOADS for s in range(10)
                 if not (OUT/'trials'/f'{c}_{n}_{s}.json').exists()]
        print(f'Starting {len(tasks)} evaluation trials',flush=True)
        for i,future in enumerate(as_completed([pool.submit(evaluate,t) for t in tasks]),1):
            row = future.result()
            if i % 20 == 0 or i == len(tasks):
                print(f"{i}/{len(tasks)} new trials complete; {time.monotonic()-start:.0f}s elapsed; latest {row['controller']} N={row['n']} MWT={row['mwt']:.2f}",flush=True)
    rows = [json.loads(p.read_text()) for p in sorted((OUT/'trials').glob('*.json'))]
    rows.sort(key=lambda r:(CONTROLLERS.index(r['controller']),r['n'],r['seed']))
    assert len(rows) == 500
    with (OUT/'fresh_runs.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(f'COMPLETE: 500 fresh trials saved to {OUT}',flush=True)


if __name__ == '__main__':
    main()
