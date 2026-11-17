"""Heuristic layout prompts, not a visual or semantic acceptance test."""
import argparse,json,math
from pathlib import Path

def inspect_scene(s,width,min_text=9):
 ratio=width/s['width'];warnings=[];labels=[]
 warnings.extend(s.get('projectionDiagnostics',[]))
 ids=set();layers={a['name'] for a in s['layers']}
 for a in s['shapes']:
  ident=a['id'];kind=a['kind']
  if ident in ids:warnings.append({'id':ident,'issue':'duplicate-id'})
  ids.add(ident)
  if a['layer'] not in layers:warnings.append({'id':ident,'issue':'unknown-layer'})
  if kind=='poly':
   ps=a['points'];xs=[p[0] for p in ps];ys=[p[1] for p in ps];bb=(min(xs),min(ys),max(xs),max(ys))
   length=sum(math.dist(p,q) for p,q in zip(ps,ps[1:]))
   if length<1e-6:warnings.append({'id':ident,'issue':'degenerate-line'})
   if a.get('endArrow') and length*ratio<.12:warnings.append({'id':ident,'issue':'short-arrow-at-document-size'})
   if not a.get('noLine') and a.get('weight',1)*ratio<.35:warnings.append({'id':ident,'issue':'thin-final-line','effective_pt':round(a.get('weight',1)*ratio,2)})
  elif kind in ['rect','ellipse','text']:bb=(a['x'],a['y'],a['x']+a['w'],a['y']+a['h'])
  else:bb=None
  if bb and (bb[0]<-.01 or bb[1]<-.01 or bb[2]>s['width']+.01 or bb[3]>s['height']+.01):warnings.append({'id':ident,'issue':'outside-canvas','bounds':bb})
  if a.get('text'):
   size=a.get('size',18)*ratio
   if size<min_text:warnings.append({'id':ident,'issue':'small-final-text','effective_pt':round(size,2)})
   has_script=(a.get('notation') and ('_{' in a['text'] or '^{' in a['text'])) or a.get('runs')
   if has_script and size*.72<min_text*.72:warnings.append({'id':ident,'issue':'small-final-subscript','effective_pt':round(size*.72,2)})
   if bb:labels.append((ident,bb))
 for k,(i,a) in enumerate(labels):
  for j,b in labels[k+1:]:
   dx=min(a[2],b[2])-max(a[0],b[0]);dy=min(a[3],b[3])-max(a[1],b[1])
   if dx>.03 and dy>.03:warnings.append({'id':i,'other':j,'issue':'text-box-intersection','overlap_inches':[round(dx,3),round(dy,3)]})
 return {'scene':s['name'],'target_width_inches':width,'warnings':warnings,'visual_acceptance':'requires inspection at document size'}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('scene');ap.add_argument('--target-width',type=float,required=True);ap.add_argument('--min-text',type=float,default=9);ap.add_argument('--output');a=ap.parse_args()
 if not math.isfinite(a.target_width) or a.target_width<=0:ap.error('target width must be positive')
 p=json.loads(Path(a.scene).read_text(encoding='utf-8-sig'));r=[inspect_scene(s,a.target_width,a.min_text) for s in p['scenes']];t=json.dumps(r,ensure_ascii=False,indent=2)
 if a.output:Path(a.output).write_text(t,encoding='utf-8')
 print(t)
if __name__=='__main__':main()
