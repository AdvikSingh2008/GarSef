"""Analyze only freshly generated replication trials; compare to supplied paper."""
import csv
import json
import os
from pathlib import Path
import warnings
import numpy as np
from scipy.optimize import curve_fit, OptimizeWarning
from scipy.stats import wilcoxon
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parent / '.mpl-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'replication_results'
NAMES={'fixed':'Fixed-time','actuated':'Actuated','max_pressure':'Max-pressure',
       'qlearning':'Q-learning','pgql':'PGQL (reconstructed)'}
COLORS=['#64748b','#d97706','#059669','#2563eb','#9333ea']
PAPER_200={'fixed':(26.27,.84),'actuated':(21.50,1.33),'max_pressure':(8.34,.21),
           'qlearning':(7.92,.19),'pgql':(11.67,.25)}
PAPER_CAP={'fixed':134,'actuated':158,'max_pressure':188,'qlearning':189,'pgql':193}
PAPER_P=[.002,.002,.002,.002,.002,.232,.160,.492,.002,.014]


def model(x,critical,a,b):
    return a/(1-x/critical)+b


def fit(x,y):
    if len(np.unique(x)) < 3:
        raise ValueError('Fewer than three distinct pre-saturation points')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', OptimizeWarning)
        return curve_fit(model,x,y,p0=[max(x)*1.5,5,0],
                         bounds=([max(x)*1.01,.1,-20],[max(x)*50,500,30]),
                         maxfev=20000)[0]


def write_csv(name, rows):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)


def main():
    rows=list(csv.DictReader((OUT/'fresh_runs.csv').open()))
    assert len(rows)==500
    groups={}
    for r in rows:
        c=r['controller']; n=int(r['n'])
        groups.setdefault((c,n),[]).append(r)
        assert 0 <= int(r['completed']) <= int(r['departed']) <= int(r['placed']) <= n
        assert np.isfinite(float(r['mwt']))
    agg=[]
    for (c,n),rs in groups.items():
        assert sorted(int(r['seed']) for r in rs)==list(range(10))
        y=np.array([float(r['mwt']) for r in rs])
        agg.append(dict(controller=c,n=n,mwt_mean=y.mean(),mwt_sem=y.std(ddof=1)/np.sqrt(10),
                        mean_in_system=np.mean([float(r['mean_in_system']) for r in rs]),
                        completed_offered=np.mean([int(r['completed'])/n for r in rs]),
                        completed_departed=np.mean([int(r['completed'])/int(r['departed']) for r in rs]),
                        departed_offered=np.mean([int(r['departed'])/n for r in rs])))
    write_csv('summary.csv',agg)
    comparisons=[]
    for n,paper_p in zip(sorted({n for c,n in groups}),PAPER_P):
        values=lambda c:np.array([float(r['mwt']) for r in sorted(groups[c,n],key=lambda r:int(r['seed']))])
        pg=values('pgql');mp=values('max_pressure');diff=pg-mp
        # All nonzero paired differences: exact two-sided Wilcoxon, matching ten seeds.
        p=wilcoxon(diff,alternative='two-sided',method='auto').pvalue if np.any(diff) else 1.
        comparisons.append(dict(n=n,pgql_median=np.median(pg),mp_median=np.median(mp),
                                paired_difference_median=np.median(diff),p_value=p,paper_p=paper_p,
                                conclusion=('PGQL worse' if np.median(diff)>0 else 'PGQL better') if p<.05 else 'not significant'))
    write_csv('paired_tests.csv',comparisons)
    print('Paired tests:',json.dumps(comparisons,indent=2),flush=True)
    fits=[]
    rng=np.random.default_rng(20260920)
    for c in NAMES:
        selected=[r for r in agg if r['controller']==c and r['completed_offered']>=.95]
        x=np.array([r['mean_in_system'] for r in selected]);y=np.array([r['mwt_mean'] for r in selected])
        params=fit(x,y)
        boots=[]
        for i in range(1000):
            ix=rng.integers(0,len(x),len(x))
            try:
                boots.append(fit(x[ix],y[ix])[0])
            except (ValueError,RuntimeError):
                pass
        lo,hi=np.percentile(boots,[2.5,97.5])
        fits.append(dict(controller=c,n_crit=params[0],a=params[1],b=params[2],
                         ci_low=lo,ci_high=hi,pre_saturation_points=len(x),
                         bootstrap_successes=len(boots),paper_n_crit=PAPER_CAP[c]))
        print(f'Capacity fit {c}: {params[0]:.2f} [{lo:.2f}, {hi:.2f}]',flush=True)
    write_csv('capacity_fits.csv',fits)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(1,3,figsize=(17,5),layout='constrained')
    for (c,label),color in zip(NAMES.items(),COLORS):
        d=sorted([r for r in agg if r['controller']==c],key=lambda r:r['n'])
        n=np.array([r['n'] for r in d]);x=np.array([r['mean_in_system'] for r in d])
        y=np.array([r['mwt_mean'] for r in d]);err=np.array([r['mwt_sem'] for r in d])
        cf=np.array([r['completed_offered'] for r in d]);pre=cf>=.95
        for ax,xx in zip(axs[:2],[n,x]):
            ax.errorbar(xx,y,yerr=err,label=label,color=color,fmt='o-',capsize=2,ms=4,lw=1.3)
            ax.scatter(xx[~pre],y[~pre],facecolors='white',edgecolors=color,s=30,zorder=4)
        axs[2].plot(n,cf*100,'o-',color=color,label=label,ms=4)
    axs[0].set(xlabel='Offered vehicles over 1,200 s',ylabel='Completed-vehicle mean wait (s)',title='Waiting time vs. demand')
    axs[1].set(xlabel='Mean vehicles present, t = 200–1,400 s',ylabel='Completed-vehicle mean wait (s)',title='Occupancy view (same completed-only metric)')
    axs[2].set(xlabel='Offered vehicles over 1,200 s',ylabel='Trips completed / offered (%)',title='Completion rate',ylim=(0,105))
    axs[2].axhline(95,color='#777777',linestyle=':',lw=1)
    for ax in axs:ax.grid(alpha=.18)
    axs[0].legend(fontsize=8)
    fig.suptitle('Fresh replication · SUMO 1.26 · 500 trials · mean ± SEM across 10 seeds\nPGQL reconstructed from manuscript; hollow markers indicate <95% completion',fontsize=13)
    fig.savefig(OUT/'replication_overview.png',dpi=160)
    plt.close(fig)
    validation=json.loads((OUT/'validation.json').read_text()) if (OUT/'validation.json').exists() else []
    legacy=next((r for r in validation if 'comparisons' in r),None)
    lines=['# Traffic-light paper replication','',
           '**Status: fresh 500-trial replication attempt completed. PGQL is a reconstruction, not recovered original code.**','',
           '## Main finding','',
           'The reported results are only partially reproduced. The non-learning controllers closely match the paper at N=200, but the newly trained Q-learning and reconstructed PGQL do not. Reconstructed PGQL improves on max-pressure at N=1300 (unadjusted paired p=0.0039), but the paper’s significant N=1700 improvement and low-load penalty are not reproduced. This conclusion concerns one independently seeded reconstruction, not an exact replay of the missing original PGQL code.','',
           (f"Validation: {legacy['exact_matches']}/{legacy['comparisons']} available historical non-learning trial MWT values matched fresh simulations exactly. Five cold-start checks matched max-pressure across all recorded traffic metrics, and three fresh deterministic reruns matched their saved trial records exactly." if legacy else 'Validation is recorded separately in `replication_results/validation.json`.'),'',
           '## At N = 200 offered vehicles','',
           'Each value is mean ± SEM across seeds 0–9, in seconds per completed vehicle. Paper values are transcribed from the supplied manuscript.','',
           '| Controller | Paper | Fresh simulation | Difference |','|---|---:|---:|---:|']
    for c in NAMES:
        r=next(r for r in agg if r['controller']==c and r['n']==200)
        p,se=PAPER_200[c]
        lines.append(f"| {NAMES[c]} | {p:.2f} ± {se:.2f} | {r['mwt_mean']:.2f} ± {r['mwt_sem']:.2f} | {r['mwt_mean']-p:+.2f} |")
    lines+=['','## PGQL versus max-pressure','',
            'Two-sided paired Wilcoxon signed-rank tests across the same ten demand seeds. P values are unadjusted, as in the manuscript; ten comparisons are made. These trials use one trained policy per learner and do not measure variation across independent training runs.','',
            '| Offered N | PGQL median wait | MP median wait | Fresh p | Paper p | Fresh conclusion |',
            '|---|---:|---:|---:|---:|---|']
    for r in comparisons:
        lines.append(f"| {r['n']} | {r['pgql_median']:.2f} | {r['mp_median']:.2f} | {r['p_value']:.4f} | {r['paper_p']:.3f} | {r['conclusion']} |")
    lines+=['','## Occupancy-based capacity fits','',
            'Model: W(n) = a / (1 - n / Ncrit) + b. Only load-level means with ≥95% completed/offered trips are fitted. Ordinary unweighted least squares; bounds carried over from the backup fit routine. Bootstrap resamples load-level mean pairs 1,000 times, skipping samples with fewer than three distinct x values or failed fits. This is not a bootstrap over training policies. Wide intervals and active bounds limit interpretation.','',
            '| Controller | Paper Ncrit | Fresh Ncrit [95% bootstrap interval] | Pre-saturation points | Successful resamples |',
            '|---|---:|---:|---:|---:|']
    for r in fits:
        lines.append(f"| {NAMES[r['controller']]} | {r['paper_n_crit']} | {r['n_crit']:.1f} [{r['ci_low']:.1f}, {r['ci_high']:.1f}] | {r['pre_saturation_points']} | {r['bootstrap_successes']} |")
    lines+=['','## What was used and changed','',
            '- Source: `ai-trafficlights_BACKUP/sumo`; existing files were copied, not edited. STS is excluded. Fresh results never reuse the backup CSV or Q-table.',
            '- The recovered fixed-time, actuated, max-pressure and Q-learning implementations are retained. Max-pressure phase selection was extracted into a method without changing its choice, allowing PGQL to share the same timing/execution.',
            '- SUMO/libsumo/duarouter 1.26.0. The supplied network was originally generated with SUMO 1.26.0. libsumo runs the simulation in-process; no GUI is needed.',
            '- 20 Q-learning training episodes and 16 PGQL episodes, repeated loads [150,250,400,600,800], seeds 1000+episode; fresh tables. Epsilon decreases linearly from 0.30 to 0.05 inclusive, following the paper. The backup used a different clipped schedule.',
            '- Evaluation uses seeds 0–9, the ten manuscript loads, and epsilon 0.02. Python controller randomness is explicitly seeded; the recovered runner left it unseeded.',
            '- Reconstructed PGQL: Q(s)=[0,1,0], state adds whether max-pressure recommends a different phase; actions are hold, follow max-pressure, and choose the green other than the max-pressure recommendation. Ties choose the first maximal action. The manuscript does not fully specify action-2 semantics, tie-breaking, training seed schedule, or initial random-state handling.',
            '- Occupancy is measured at integer times 200–1400 inclusive, with zeros after early network clearance. Both completed/offered and completed/actually-departed fractions are saved. The recovered `placed` field is the number of routed vehicles, not the number that entered the network.',
            '- No hyperparameters were selected to make the reported values match.','',
            '## Reproducibility and interpretation limitations','',
            '1. The original PGQL implementation and original training tables/seeds are missing. This is an independent reconstruction of that controller, so a mismatch cannot by itself falsify the original implementation.',
            '2. The recovered network has nine signal IDs but four corner signals have a single permanent-green phase. Only five signals alternate. This contradicts the manuscript statement that all nine use the same two-green plan.',
            '3. The recovered adaptive controllers leave SUMO’s static phase progression active. Explicit phase changes coexist with automatic phase changes; the code does not enforce a permanent hold until the next controller action. This behavior was retained, not silently repaired.',
            '4. Warm-start equivalence applies to the untrained greedy policy with exploration disabled. Epsilon-greedy exploration and learned overrides mean a stability or worst-case-performance guarantee does not follow merely from initializing the Q-table.',
            '5. Changing the horizontal axis to occupancy does not remove completed-vehicle selection bias: unfinished vehicles remain excluded from MWT. The completion plot is essential when interpreting the post-saturation decrease.',
            '6. The manuscript’s stated ~13% capacity gain conflicts with its Table 1: 188/134−1 is about 40%, and 193/134−1 is about 44%. Those claims cannot all match the same fit.',
            '7. SEM bars are not 95% confidence intervals, and overlapping SEM bars alone are not a statistical equivalence test.','',
            '## Files and rerunning','',
            '- `replication_results/fresh_runs.csv`: all 500 fresh measurements.',
            '- `summary.csv`, `paired_tests.csv`, `capacity_fits.csv`: derived analyses in the same results folder.',
            '- `manifest.json`: parameters, exact package versions and source SHA-256 hashes.',
            '- `qlearning_training.json`, `pgql_training.json`: training episode results; fresh policy files are retained alongside them.',
            '- `replication_overview.png`: three-panel plot.',
            '- `validation.json`: deterministic rerun and cold-start equivalence checks, when generated by `validate_replication.py`.','',
            '```powershell',r'cd C:\Users\advik\Downloads\tools\traffic_replication',
            r'.\.venv\Scripts\python.exe replicate.py --workers 4',
            r'.\.venv\Scripts\python.exe validate_replication.py',
            r'.\.venv\Scripts\python.exe analyze.py','```','',
            'The runner resumes completed trials and rejects changed source/settings to avoid mixing experiments. For a completely new run, rename the `replication_results` directory first.']
    (ROOT/'REPLICATION_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Report and plot written.',flush=True)


if __name__=='__main__':main()
