"""Replot saved controls only; FINAL and exposed diagnostics stay separate."""
import json
from pathlib import Path
from statistics import mean
from nebula.submission_evidence import ROOT, sha

def plot_saved_controls(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    final_path=ROOT/'nebula/experiments/shielded_policy_final_results.json'
    post_path=ROOT/'nebula/product_audits/entry113_attribution_20260907/summary.json'
    final=json.loads(final_path.read_text());post=json.loads(post_path.read_text())
    assert post['status']=='POST_REVIEW_EXPOSED_DIAGNOSTIC'
    assert post['training_steps']==post['simulations_run']==0
    groups=[('fixed','Fixed start'),('hill','Hill + shield'),('random_local','Random + shield'),('bc','Imitation + shield'),('ppo','PPO + shield')]
    rows=[]
    for key,label in groups:
        values=[r for r in post['results'] if r['arm']==key and r['budget']==8]
        rows.append((label,mean(r['quality'] for r in values),mean(r['compliant'] for r in values)))
    raw=final['controls']['entry89_unshielded'];shield=final['controls']['entry89_shielded']
    frozen=[('Raw PPO',mean(r['mean_quality'] for r in raw),mean(r['compliance_rate'] for r in raw)),
            ('PPO + shield',mean(r['mean_quality'] for r in shield),mean(r['compliance_rate'] for r in shield))]
    fig,axes=plt.subplots(1,2,figsize=(10,3.25),gridspec_kw={'width_ratios':[1.6,1]},layout='constrained')
    for ax,data,title in [(axes[0],rows,'Post-review exposed / eight-visit cap'),(axes[1],frozen,'Frozen FINAL / eight-visit cap')]:
        y=list(range(len(data)));q=[r[1] for r in data]
        ax.barh(y,q,color='#008aa1',height=.6);ax.set_yticks(y,[r[0] for r in data]);ax.invert_yaxis()
        for i,(_,quality,comp) in enumerate(data):ax.text(quality+.012,i,f'{quality:.3f} | {100*comp:.1f}%',va='center',fontsize=9)
        ax.set_xlim(0,1.04);ax.set_xlabel('Mean quality q | label: q and compliance');ax.set_title(title,fontsize=10)
        for spine in ['top','right']:ax.spines[spine].set_visible(False)
        ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(output,dpi=200);plt.close(fig)
    return dict(sources={str(p.relative_to(ROOT)):sha(p) for p in [final_path,post_path]},
                exposed=rows,frozen=frozen,simulations_launched=0,training_steps=0)
