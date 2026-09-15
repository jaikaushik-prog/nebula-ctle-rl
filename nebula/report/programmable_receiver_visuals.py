"""Exact named-net device sheet and measured plots for the derived receiver."""
from pathlib import Path
import hashlib,json,re
import numpy as np
from nebula.experiments.review_programmable_receiver import review,ROOT,MAIN,OUT

def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle,Circle
    from nebula import programmable_receiver as P
    data=review();deck=(MAIN/'selected_control_link/design.cir').read_text();rows=[]
    for line in deck.split('.control')[0].splitlines():
        f=line.split()
        if not f or not f[0].startswith('X'):continue
        j=next(i for i,s in enumerate(f) if s.startswith('sky130_'))
        rows.append((f[0],f[1:j],f[j].removeprefix('sky130_fd_pr__'),' '.join(f[j+1:])))
    if len(set(r[0] for r in rows))!=len(rows):raise ValueError('duplicate drawn device')
    nrows=(len(rows)+3)//4
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':9}):
        fig,axes=plt.subplots(nrows,4,figsize=(20,nrows*2.25))
        fig.subplots_adjust(top=.96,bottom=.03,left=.025,right=.985,hspace=.25,wspace=.12)
        fig.text(.025,.989,'Derived programmable receiver',fontsize=23,weight='bold',va='top')
        fig.text(.025,.974,'Exact named-net SKY130 device sheet. Equal labels connect; D/G/S/B follow the measured netlist. Experimental, not signed off.',fontsize=11)
        for ax in axes.flat:ax.set(xlim=(0,10),ylim=(0,5));ax.axis('off')
        for ax,(name,nets,model,params) in zip(axes.flat,rows):
            ax.text(.1,4.7,name,fontsize=12,weight='bold');ax.text(.1,4.2,model,fontsize=9)
            def wire(x,y):ax.plot(x,y,color='#0b2342',lw=1.2)
            if 'fet' in model:
                assert len(nets)==4
                wire([4.8,4.8,4.1],[3.9,3.2,3.2]);wire([4.8,4.8,4.1],[1.2,1.9,1.9]);wire([4.1,4.1],[1.75,3.35]);wire([3.8,3.8],[1.9,3.2]);wire([2.4,3.8],[2.55,2.55])
                for x,y,label in [(5.1,3.65,'D: '+nets[0]),(.1,2.55,'G: '+nets[1]),(5.1,1.35,'S: '+nets[2]),(5.1,2.55,'B: '+nets[3])]:ax.text(x,y,label,fontsize=8)
                if model.startswith('pfet'):ax.add_patch(Circle((3.6,2.55),.13,fc='white',ec='#0b2342'))
            else:
                wire([1.8,4.2],[2.6,2.6]);wire([5.8,8.2],[2.6,2.6])
                if 'res_' in model:ax.add_patch(Rectangle((4.2,2.25),1.6,.7,fc='white',ec='#0b2342'))
                else:
                    wire([4.7,4.7],[1.9,3.3]);wire([5.3,5.3],[1.9,3.3]);wire([4.2,4.7],[2.6,2.6]);wire([5.3,5.8],[2.6,2.6])
                    if 'var_' in model:ax.annotate('',xy=(5.8,3.4),xytext=(4.2,1.8),arrowprops={'arrowstyle':'->'})
                ax.text(1.8,3.05,nets[0],ha='center',fontsize=8);ax.text(8.2,3.05,nets[1],ha='center',fontsize=8)
                if len(nets)>2:ax.text(5,1.2,'bulk: '+nets[2],ha='center',fontsize=8)
            ax.text(.1,.3,params,fontsize=8)
        fig.text(.025,.017,'W/L in microns. W=57.97671772296124, L=0.3911493163378813, NF=4; WT=201.656, LT=0.5, NFT=8; WREF=25.2069, NFREF=1.\nCLp: outp to ground, CLn: outn to ground, each32.628fF. External apparatus: supply1.8V, common mode1.501023V, input waveform, clocks, tap2 and R/C controls1.314/0.378V.\nMeasured deck SHA-256: '+data['artifacts']['deck']['sha256'],fontsize=9)
        fig.savefig(OUT/'device_sheet.png',dpi=110,facecolor='white');fig.savefig(OUT/'device_sheet.svg',facecolor='white');plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(12,4.3));fig.subplots_adjust(left=.065,right=.985,bottom=.20,top=.84,wspace=.26)
        for i,point in enumerate(data['control_points']):
            raw=np.loadtxt(MAIN/f'held_state0/ac_{i:03d}.txt');h=P.R.parse_ac(raw,1)[:,0]
            axes[0].semilogx(raw[:,0]/1e9,20*np.log10(abs(h)),label=f'C control {point["c_fraction"]*1.8:.3f} V',lw=1.4)
        axes[0].set(xlim=(.01,10),ylim=(-6,1.5),xlabel='Frequency (GHz)',ylabel='Differential CTLE gain (dB)',title='Physical control changes the loaded response')
        axes[0].legend(fontsize=8,frameon=False);axes[0].grid(alpha=.2)
        t,y=P.G.T.read_table(MAIN/'selected_control_link/trace.txt',len(P.VECTORS))
        offsets=np.arange(-200,201)*.005;indices=np.arange(P.G.F.WARMUP,P.G.F.N_BITS)
        times=(indices[:,None]+3+offsets[None,:])*P.G.UI
        assert times.min()>=t[0] and times.max()<=t[-1]
        waves=np.interp(times,t,y[:,3]-y[:,4])*1e3
        for wave in waves:axes[1].plot(offsets,wave,color='#008fb4',alpha=.23,lw=.8)
        axes[1].set(xlim=(-1,1),xlabel='Time relative to clock edge (UI)',ylabel='Transistor summer differential (mV)',title='New receiver at the measured chosen control')
        axes[1].axhline(0,color='gray',lw=.6);axes[1].grid(alpha=.2)
        fig.suptitle('Programmable variant derived from selected setting 352',fontsize=14)
        fig.text(.065,.045,'TT / 1.8 V / 27 C. R control 1.314 V. Chosen C control 0.378 V. 64 scored bits on a constructed 7.5 dB channel.\nNominal AC and signal evidence only; signed model-domain violations remain. No PVT, periodic noise, HD3 or BER signoff.',fontsize=9)
        fig.savefig(OUT/'measured_response_eye.png',dpi=180,facecolor='white');plt.close(fig)
    result=dict(device_count=len(rows),source_review_sha256=hashlib.sha256((OUT/'review.json').read_bytes()).hexdigest(),
                artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'device_sheet.png',OUT/'device_sheet.svg',OUT/'measured_response_eye.png')})
    (OUT/'visuals.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':render()
