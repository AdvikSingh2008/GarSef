"""Full study: train Q-learning, sweep all controllers across N values, plot.

Runs 4 controllers x 10 car-counts x 10 random seeds = 400 simulations,
then plots MWT vs N and fits the capacity formula  W(N) = a / (1 - N/N_crit) + b.

Outputs (all in results/):
    raw_runs.csv     -- one row per individual simulation
    summary.csv      -- mean and SEM per (controller, N)
    fit_params.csv   -- fitted capacity formula per controller
    mwt_vs_n.png     -- the headline plot

Resumable: if you stop and re-run, already-completed (controller, N, seed) trios
are skipped. Delete results/raw_runs.csv (and qtable.pkl) to start fresh.

Just run:
    python run_all.py
"""
import os
import sys
import csv
import time
import math
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from run_one import run_trial, CONTROLLERS

# ------------- knobs you might want to tweak -------------
SEEDS_PER_POINT = 10
NS              = [50, 100, 200, 300, 450, 600, 800, 1000, 1300, 1700]
CONTROLLERS_TO_RUN = ["fixed", "actuated", "max_pressure", "qlearning"]
TRAIN_EPISODES  = 20
# ---------------------------------------------------------

RESULTS_DIR = os.path.join(HERE, "results")
RAW_CSV     = os.path.join(RESULTS_DIR, "raw_runs.csv")
SUMMARY_CSV = os.path.join(RESULTS_DIR, "summary.csv")
QTABLE_PATH = os.path.join(RESULTS_DIR, "qtable.pkl")
PLOT_PATH   = os.path.join(RESULTS_DIR, "mwt_vs_n.png")
FIT_CSV     = os.path.join(RESULTS_DIR, "fit_params.csv")

FIELDS = ["controller", "n", "seed", "placed", "completed",
          "mwt", "mean_time_loss"]


def existing_keys():
    if not os.path.exists(RAW_CSV):
        return set()
    return {(r["controller"], int(r["n"]), int(r["seed"]))
            for r in csv.DictReader(open(RAW_CSV))}


def append_row(row):
    new = not os.path.exists(RAW_CSV)
    with open(RAW_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row[k] for k in FIELDS})


def train_qlearning(episodes=TRAIN_EPISODES):
    print(f"\n=== Training Q-learning ({episodes} episodes) ===")
    if os.path.exists(QTABLE_PATH):
        os.unlink(QTABLE_PATH)
    train_loads = [150, 250, 400, 600, 800]
    t0 = time.time()
    for ep in range(episodes):
        eps = max(0.05, 0.30 * (1 - ep / max(1, episodes - 1)))
        n = train_loads[ep % len(train_loads)]
        seed = 1000 + ep
        r = run_trial("qlearning", n=n, seed=seed,
                      qtable_path=QTABLE_PATH, train=True, eps=eps)
        print(f"  ep {ep+1:02d}/{episodes}  n={n}  eps={eps:.3f}  "
              f"mwt={r['mwt']:6.2f}  ({time.time()-t0:.0f}s)")
    print(f"Q-table saved to {QTABLE_PATH}")


def sweep():
    total = len(CONTROLLERS_TO_RUN) * len(NS) * SEEDS_PER_POINT
    done = existing_keys()
    print(f"\n=== Sweep: {len(CONTROLLERS_TO_RUN)} controllers x {len(NS)} N x "
          f"{SEEDS_PER_POINT} seeds = {total} runs "
          f"({len(done)} already done, {total - len(done)} to go) ===")

    new = 0
    t0 = time.time()
    for c in CONTROLLERS_TO_RUN:
        qpath = QTABLE_PATH if c == "qlearning" else None
        for n in NS:
            for s in range(SEEDS_PER_POINT):
                if (c, n, s) in done:
                    continue
                r = run_trial(c, n, s, qtable_path=qpath,
                              eps=0.02 if c == "qlearning" else None)
                append_row(r)
                new += 1
                count = len(done) + new
                print(f"  [{count:4d}/{total}] {c:14s} "
                      f"n={n:5d} s={s:2d}  mwt={r['mwt']:7.2f}  "
                      f"({time.time()-t0:.0f}s)")


def aggregate_and_plot():
    print("\n=== Aggregating, plotting, fitting capacity formula ===")
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.optimize import curve_fit

    rows = list(csv.DictReader(open(RAW_CSV)))
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["controller"], int(r["n"]))].append(r)

    agg = collections.defaultdict(lambda: {"n": [], "mwt_mean": [],
                                           "mwt_sem": [], "completed_frac": []})
    for (c, n), grp in sorted(by.items()):
        mwts = [float(g["mwt"]) for g in grp if not math.isnan(float(g["mwt"]))]
        cf = [float(g["completed"])/float(g["placed"])
              for g in grp if float(g["placed"]) > 0]
        if not mwts:
            continue
        m = sum(mwts)/len(mwts)
        sd = (math.sqrt(sum((x-m)**2 for x in mwts)/(len(mwts)-1))
              if len(mwts) > 1 else 0.0)
        agg[c]["n"].append(n)
        agg[c]["mwt_mean"].append(m)
        agg[c]["mwt_sem"].append(sd/math.sqrt(len(mwts)))
        agg[c]["completed_frac"].append(sum(cf)/len(cf))

    with open(SUMMARY_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["controller", "n", "mwt_mean", "mwt_sem", "completed_frac"])
        for c, d in agg.items():
            for n, m, s, cf in zip(d["n"], d["mwt_mean"],
                                   d["mwt_sem"], d["completed_frac"]):
                w.writerow([c, n, f"{m:.3f}", f"{s:.3f}", f"{cf:.3f}"])

    def queue_model(n, n_crit, a, b):
        return a / (1.0 - n/n_crit) + b

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=130)
    ax1, ax2 = axes
    cols = {"fixed": "#888888", "actuated": "#1f77b4",
            "max_pressure": "#2ca02c", "qlearning": "#d62728"}
    nice = {"fixed": "Fixed-time", "actuated": "Actuated (gap-out)",
            "max_pressure": "Max-Pressure", "qlearning": "Q-Learning (RL)"}
    fits = []
    for c, d in sorted(agg.items()):
        ns = np.array(d["n"]); mwt = np.array(d["mwt_mean"])
        sem = np.array(d["mwt_sem"]); cf = np.array(d["completed_frac"])
        col = cols.get(c, "k")
        pre = cf >= 0.95
        ax1.errorbar(ns[pre], mwt[pre], yerr=sem[pre], fmt="o-",
                     color=col, label=nice.get(c, c), capsize=3, lw=1.6, ms=6)
        if (~pre).any():
            ax1.errorbar(ns[~pre], mwt[~pre], yerr=sem[~pre], fmt="o:",
                         mfc="white", color=col, capsize=3, lw=1, ms=6)
        ax2.plot(ns, 100*cf, "o-", color=col,
                 label=nice.get(c, c), lw=1.6, ms=5)

        if pre.sum() >= 3:
            try:
                p0 = [ns[pre].max()*1.5, 5.0, 0.0]
                bounds = ([ns[pre].max()*1.01, 0.1, -20],
                          [ns[pre].max()*50, 500, 30])
                popt, _ = curve_fit(queue_model, ns[pre], mwt[pre],
                                    p0=p0, bounds=bounds, maxfev=20000)
                n_grid = np.linspace(ns.min(), popt[0]*0.985, 300)
                ax1.plot(n_grid, queue_model(n_grid, *popt), "--",
                         color=col, alpha=0.5, lw=1)
                fits.append([c, f"{popt[0]:.0f}",
                             f"{popt[1]:.2f}", f"{popt[2]:.2f}"])
                print(f"  {c:14s}  N_crit={popt[0]:7.0f}  "
                      f"a={popt[1]:6.2f}  b={popt[2]:6.2f}")
            except Exception as e:
                print(f"  fit failed for {c}: {e}")
                fits.append([c, "fit_failed", "", ""])

    with open(FIT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["controller", "N_crit", "a", "b"])
        for r in fits:
            w.writerow(r)

    ax1.set_xlabel("N  (cars offered over 1200 s window)")
    ax1.set_ylabel("Mean Wait Time per car  (s)")
    ax1.set_title("MWT vs. demand\n"
                  "solid = pre-saturation, hollow + dotted = post-saturation")
    ax1.set_ylim(0, 200)
    ax1.grid(alpha=0.3)
    ax1.legend(loc="upper left", fontsize=9)

    ax2.set_xlabel("N  (cars offered)")
    ax2.set_ylabel("% of cars completing trip")
    ax2.set_title("Throughput collapse at saturation")
    ax2.axhline(95, color="k", ls=":", lw=0.8, alpha=0.5)
    ax2.set_ylim(0, 105)
    ax2.grid(alpha=0.3)
    ax2.legend(loc="lower left", fontsize=9)

    fig.suptitle(f"3x3 SUMO grid: 4-controller comparison "
                 f"(mean +/- SEM, {SEEDS_PER_POINT} seeds)",
                 y=1.02, fontsize=12)
    fig.tight_layout()
    fig.savefig(PLOT_PATH, bbox_inches="tight")
    print(f"\nWrote {PLOT_PATH}")
    print(f"Wrote {SUMMARY_CSV}")
    print(f"Wrote {FIT_CSV}")


if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if "qlearning" in CONTROLLERS_TO_RUN and not os.path.exists(QTABLE_PATH):
        train_qlearning()
    sweep()
    aggregate_and_plot()
