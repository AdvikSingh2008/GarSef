# Traffic-light paper replication

**Status: fresh 500-trial replication attempt completed. PGQL is a reconstruction, not recovered original code.**

## Main finding

The reported results are only partially reproduced. The non-learning controllers closely match the paper at N=200, but the newly trained Q-learning and reconstructed PGQL do not. Reconstructed PGQL improves on max-pressure at N=1300 (unadjusted paired p=0.0039), but the paper’s significant N=1700 improvement and low-load penalty are not reproduced. This conclusion concerns one independently seeded reconstruction, not an exact replay of the missing original PGQL code.

Validation: 90/90 available historical non-learning trial MWT values matched fresh simulations exactly. Five cold-start checks matched max-pressure across all recorded traffic metrics, and three fresh deterministic reruns matched their saved trial records exactly.

## At N = 200 offered vehicles

Each value is mean ± SEM across seeds 0–9, in seconds per completed vehicle. Paper values are transcribed from the supplied manuscript.

| Controller | Paper | Fresh simulation | Difference |
|---|---:|---:|---:|
| Fixed-time | 26.27 ± 0.84 | 26.27 ± 0.84 | +0.00 |
| Actuated | 21.50 ± 1.33 | 21.49 ± 1.33 | -0.01 |
| Max-pressure | 8.34 ± 0.21 | 8.30 ± 0.21 | -0.04 |
| Q-learning | 7.92 ± 0.19 | 10.29 ± 0.26 | +2.37 |
| PGQL (reconstructed) | 11.67 ± 0.25 | 7.88 ± 0.16 | -3.79 |

## PGQL versus max-pressure

Two-sided paired Wilcoxon signed-rank tests across the same ten demand seeds. P values are unadjusted, as in the manuscript; ten comparisons are made. These trials use one trained policy per learner and do not measure variation across independent training runs.

| Offered N | PGQL median wait | MP median wait | Fresh p | Paper p | Fresh conclusion |
|---|---:|---:|---:|---:|---|
| 50 | 6.56 | 6.54 | 0.8457 | 0.002 | not significant |
| 100 | 6.91 | 7.19 | 0.6250 | 0.002 | not significant |
| 200 | 7.88 | 8.45 | 0.1641 | 0.002 | not significant |
| 300 | 9.63 | 9.74 | 1.0000 | 0.002 | not significant |
| 450 | 14.11 | 14.18 | 0.9219 | 0.002 | not significant |
| 600 | 23.22 | 24.68 | 0.3750 | 0.232 | not significant |
| 800 | 70.62 | 70.55 | 0.0371 | 0.160 | PGQL better |
| 1000 | 134.31 | 167.89 | 0.1602 | 0.492 | not significant |
| 1300 | 94.26 | 100.62 | 0.0039 | 0.002 | PGQL better |
| 1700 | 72.73 | 80.61 | 0.3223 | 0.014 | not significant |

## Occupancy-based capacity fits

Model: W(n) = a / (1 - n / Ncrit) + b. Only load-level means with ≥95% completed/offered trips are fitted. Ordinary unweighted least squares; bounds carried over from the backup fit routine. Bootstrap resamples load-level mean pairs 1,000 times, skipping samples with fewer than three distinct x values or failed fits. This is not a bootstrap over training policies. Wide intervals and active bounds limit interpretation.

| Controller | Paper Ncrit | Fresh Ncrit [95% bootstrap interval] | Pre-saturation points | Successful resamples |
|---|---:|---:|---:|---:|
| Fixed-time | 134 | 149.2 [27.2, 154.5] | 6 | 981 |
| Actuated | 158 | 163.0 [57.3, 177.1] | 6 | 971 |
| Max-pressure | 188 | 191.2 [70.4, 197.9] | 7 | 998 |
| Q-learning | 189 | 191.4 [35.6, 195.3] | 7 | 998 |
| PGQL (reconstructed) | 193 | 188.1 [58.0, 193.8] | 7 | 994 |

## What was used and changed

- Source: `ai-trafficlights_BACKUP/sumo`; existing files were copied, not edited. STS is excluded. Fresh results never reuse the backup CSV or Q-table.
- The recovered fixed-time, actuated, max-pressure and Q-learning implementations are retained. Max-pressure phase selection was extracted into a method without changing its choice, allowing PGQL to share the same timing/execution.
- SUMO/libsumo/duarouter 1.26.0. The supplied network was originally generated with SUMO 1.26.0. libsumo runs the simulation in-process; no GUI is needed.
- 20 Q-learning training episodes and 16 PGQL episodes, repeated loads [150,250,400,600,800], seeds 1000+episode; fresh tables. Epsilon decreases linearly from 0.30 to 0.05 inclusive, following the paper. The backup used a different clipped schedule.
- Evaluation uses seeds 0–9, the ten manuscript loads, and epsilon 0.02. Python controller randomness is explicitly seeded; the recovered runner left it unseeded.
- Reconstructed PGQL: Q(s)=[0,1,0], state adds whether max-pressure recommends a different phase; actions are hold, follow max-pressure, and choose the green other than the max-pressure recommendation. Ties choose the first maximal action. The manuscript does not fully specify action-2 semantics, tie-breaking, training seed schedule, or initial random-state handling.
- Occupancy is measured at integer times 200–1400 inclusive, with zeros after early network clearance. Both completed/offered and completed/actually-departed fractions are saved. The recovered `placed` field is the number of routed vehicles, not the number that entered the network.
- No hyperparameters were selected to make the reported values match.

## Reproducibility and interpretation limitations

1. The original PGQL implementation and original training tables/seeds are missing. This is an independent reconstruction of that controller, so a mismatch cannot by itself falsify the original implementation.
2. The recovered network has nine signal IDs but four corner signals have a single permanent-green phase. Only five signals alternate. This contradicts the manuscript statement that all nine use the same two-green plan.
3. The recovered adaptive controllers leave SUMO’s static phase progression active. Explicit phase changes coexist with automatic phase changes; the code does not enforce a permanent hold until the next controller action. This behavior was retained, not silently repaired.
4. Warm-start equivalence applies to the untrained greedy policy with exploration disabled. Epsilon-greedy exploration and learned overrides mean a stability or worst-case-performance guarantee does not follow merely from initializing the Q-table.
5. Changing the horizontal axis to occupancy does not remove completed-vehicle selection bias: unfinished vehicles remain excluded from MWT. The completion plot is essential when interpreting the post-saturation decrease.
6. The manuscript’s stated ~13% capacity gain conflicts with its Table 1: 188/134−1 is about 40%, and 193/134−1 is about 44%. Those claims cannot all match the same fit.
7. SEM bars are not 95% confidence intervals, and overlapping SEM bars alone are not a statistical equivalence test.

## Files and rerunning

- `replication_results/fresh_runs.csv`: all 500 fresh measurements.
- `summary.csv`, `paired_tests.csv`, `capacity_fits.csv`: derived analyses in the same results folder.
- `manifest.json`: parameters, exact package versions and source SHA-256 hashes.
- `qlearning_training.json`, `pgql_training.json`: training episode results; fresh policy files are retained alongside them.
- `replication_overview.png`: three-panel plot.
- `validation.json`: deterministic rerun and cold-start equivalence checks, when generated by `validate_replication.py`.

```powershell
cd C:\Users\advik\Downloads\tools\traffic_replication
.\.venv\Scripts\python.exe replicate.py --workers 4
.\.venv\Scripts\python.exe validate_replication.py
.\.venv\Scripts\python.exe analyze.py
```

The runner resumes completed trials and rejects changed source/settings to avoid mixing experiments. For a completely new run, rename the `replication_results` directory first.
