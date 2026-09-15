"""Collect verified report content without rebuilding or altering the PDF."""
import ast
import json
from pathlib import Path
from nebula.report import final_submission_v4 as R, final_submission_v5 as V
from nebula.deadline_evidence import diagnostics

OUT=R.ROOT/'tmp/academic-closeout'
class Collector(V.RevisedReport):
    def __init__(self):self.sections=[];self.n=0;self.width=511.2756
    def add(self,kind,**values):self.sections[-1]['blocks'].append(dict(kind=kind,**values))
    def new(self,section,subtitle):
        self.n+=1;self.sections.append(dict(number=self.n,subtitle=subtitle,blocks=[]))
    def para(self,text,*a,**k):self.add('paragraph',text=text)
    def heading(self,text):self.add('heading',text=text)
    def table(self,headings,rows,*a,**k):self.add('table',headings=headings,rows=rows)
    def figure(self,name,caption,height):
        path=(R.V4_ASSETS if name in ('desktop','learning') else R.V3_ASSETS if name=='generated_aperture' else R.ASSETS)/(name+'.png')
        if name=='selected_ctle':path=R.LIVE_ROOT/'design_schematic.png'
        self.add('figure',name=name,path=str(path),caption=caption)
    def owner_fields(self):self.add('identity')

def collect():
    manifest=json.loads(V.MANIFEST.read_text())
    if R.sha(V.PDF)!=manifest['report_sha256']:raise ValueError('Current report hash mismatch')
    evidence=R.load_final_evidence();campaign=R.load_campaign_evidence();revision=R.load_revision_evidence()
    r=Collector();h=evidence['hardware']
    env=dict(vars(R));env.update(r=r,e=evidence,h=h,n=h['nominal'],p=h['pvt'],
        agg=evidence['legacy']['final']['aggregate'],bench=evidence['legacy']['winning']['benchmark']['aggregate'],
        campaign=campaign,revision=revision,rc=R.load_receipt_evidence())
    tree=ast.parse(Path(R.__file__).read_text())
    body=next(n.body for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build')
    def method(n,name):return isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='r' and n.value.func.attr==name
    start=next(i for i,n in enumerate(body) if method(n,'new'));end=next(i for i,n in enumerate(body) if method(n,'save'))
    exec(compile(ast.Module(body=body[start:end],type_ignores=[]),'<report content only>','exec'),env)
    data=dict(sections=r.sections,diagnostics=diagnostics(),pdf_sha256=R.sha(V.PDF),source_pdf=str(V.PDF),
        source_manifest_sha256=R.sha(V.MANIFEST),sources=manifest['sources'])
    OUT.mkdir(exist_ok=True)
    (OUT/'report_content.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(f'Collected {len(r.sections)} sections; no PDF edit, simulation or training')

if __name__=='__main__':collect()
