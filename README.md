# GarSef

GarSef project: traffic-light research replication.

Completed independent replication attempt: SUMO 1.26.0, 36 fresh training episodes,
and 500 evaluation trials. Read [REPLICATION_REPORT.md](REPLICATION_REPORT.md).
The paper is **partially reproduced**, not fully replicated.

Four baseline controllers and the network came from `ai-trafficlights_BACKUP/sumo`.
**PGQL is reconstructed from the paper**, because its original source was unavailable.
No STS project files are included. Original source/data folders were not modified.

## Results

See `replication_results/`:

- `fresh_runs.csv`: all 500 fresh trial measurements.
- `summary.csv`: means and SEMs.
- `paired_tests.csv`: paired PGQL/max-pressure comparisons.
- `capacity_fits.csv`: occupancy-based fitted capacities and bootstrap intervals.
- `replication_overview.png`: three-panel results figure.
- `manifest.json`: settings, versions, and source hashes.
- `validation.json`: 90 exact legacy matches, five warm-start checks, and three deterministic reruns.
- Training logs and newly trained policy tables. The legacy policy pickle was not used.

## Run on this machine

```powershell
cd C:\Users\advik\Downloads\tools\traffic_replication
.\.venv\Scripts\python.exe replicate.py --workers 4
.\.venv\Scripts\python.exe validate_replication.py
.\.venv\Scripts\python.exe analyze.py
```

The runner resumes saved trials and rejects changed source/settings. For a new full
run, rename `replication_results` first, preserving the previous results.

## Set up another Windows machine

Use Python 3.12, then run inside this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then use the three execution commands above. The ZIP excludes the large environment;
dependencies are downloaded during setup. The default engine is libsumo.

`run_one.py` contains the instrumented single-trial engine. `run_all.py` is the
recovered legacy four-controller script; **use `replicate.py` for this study**.
`original_backup/` preserves recovered scripts, controllers and legacy data as
provenance, not as fresh results.

The report documents network/controller discrepancies, ambiguous PGQL details,
training randomness and completed-trip selection bias. No parameters were tuned
to force agreement with the paper.
