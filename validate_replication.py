"""Simulation-level checks for reproducibility and reconstructed warm start."""
import csv
import json
from pathlib import Path
from run_one import run_trial

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'replication_results'
METRICS=['placed','completed','mwt','mean_time_loss','mean_in_system','departed']


def main():
    checks=[]
    for n,seed in [(50,2),(200,0),(800,4),(1300,3),(1700,9)]:
        mp=run_trial('max_pressure',n,seed)
        pg=run_trial('pgql',n,seed,eps=0)
        assert all(mp[k]==pg[k] for k in METRICS),(mp,pg)
        checks.append({'check':'untrained PGQL epsilon=0 equals MP',
                       'n':n,'seed':seed,'metrics':{k:mp[k] for k in METRICS},'passed':True})
    for c,n,seed in [('fixed',200,0),('qlearning',800,2),('pgql',1300,4)]:
        stored=json.loads((OUT/'trials'/f'{c}_{n}_{seed}.json').read_text())
        qpath=str(OUT/(c+'_fresh.pkl')) if c!='fixed' else None
        fresh=run_trial(c,n,seed,qpath,eps=.02 if qpath else None)
        assert stored==fresh,(stored,fresh)
        checks.append({'check':'exact deterministic rerun','controller':c,'n':n,'seed':seed,'passed':True})
    original=list(csv.DictReader((ROOT/'original_backup/raw_runs.csv').open()))
    differences=[]
    for r in original:
        if r['controller'] not in ['fixed','actuated','max_pressure']:continue
        new=json.loads((OUT/'trials'/f"{r['controller']}_{r['n']}_{r['seed']}.json").read_text())
        differences.append(abs(float(r['mwt'])-new['mwt']))
    checks.append({'check':'recovered legacy deterministic results comparison',
                   'comparisons':len(differences),'exact_matches':sum(d==0 for d in differences),
                   'maximum_absolute_mwt_difference':max(differences,default=0)})
    (OUT/'validation.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
