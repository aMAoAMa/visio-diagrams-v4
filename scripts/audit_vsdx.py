"""Audit renderer-produced VSDX against source 2-D scene, without Visio or lxml.

Checks native geometry, actual Layers, exact source IDs, text and per-character
sub/superscript positions and connector endpoint targets. Does not assess layout.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = {'v': 'http://schemas.microsoft.com/office/visio/2012/main'}
def cell(node, name, default=''):
    found = node.find(f"v:Cell[@N='{name}']", NS)
    return found.get('V', default) if found is not None else default
def expected_text(item):
    text = item.get('text', ''); positions = []
    if item.get('notation'):
        out = ''; cursor = 0
        for m in re.finditer(r'([_^])\{([^}]+)\}', text):
            fragment = text[cursor:m.start()]; out += fragment; positions += [0]*len(fragment)
            out += m[2]; positions += [2 if m[1]=='_' else 1]*len(m[2]); cursor = m.end()
        out += text[cursor:]; positions += [0]*len(text[cursor:]); return out, positions
    positions = [0]*len(text)
    # Explicit run indices are UTF-16 units, as used by the COM Characters API.
    indices=[]; count=0
    for char in text: indices.append(count); count += len(char.encode('utf-16-le'))//2
    for run in item.get('runs', []):
        for i, ix in enumerate(indices):
            if run['start'] <= ix < run['end']: positions[i] = 2 if run['position']=='subscript' else 1
    return text, positions
def native_text(shape):
    rows={r.get('IX','0'):cell(r,'Pos','0') for r in shape.findall("v:Section[@N='Character']/v:Row",NS)}
    text_node=shape.find('v:Text',NS)
    if text_node is None: return '', []
    out=text_node.text or ''; positions=[0]*len(out); current='0'
    for child in text_node:
        if child.tag == '{'+NS['v']+'}cp': current=child.get('IX','0')
        tail=child.tail or ''; out+=tail; positions += [int(rows.get(current,'0'))]*len(tail)
    # Visio adds a final paragraph newline; preserve all authored characters.
    if out.endswith('\n'): out=out[:-1]; positions=positions[:-1]
    return out, positions
def audit(path, scene):
    errors=[]
    with ZipFile(path) as z:
        pages=ET.fromstring(z.read('visio/pages/pages.xml')); page=pages.find('v:Page',NS)
        # This renderer emits exactly one page; don't silently audit the wrong page.
        if len(pages.findall('v:Page',NS)) != 1: raise ValueError('Expected one-page renderer output')
        root=ET.fromstring(z.read('visio/pages/page1.xml'))
        rows=page.findall("v:PageSheet/v:Section[@N='Layer']/v:Row",NS)
        # Visio retains deleted layer slots with Status=1 and an empty Name.
        layers={r.get('IX'):cell(r,'Name') for r in rows if cell(r,'Status','0')!='1'}
        if set(layers.values())!={a['name'] for a in scene['layers']}|{'__page-export__'}: errors.append('layer-definition-set-mismatch')
        shapes=root.findall('.//v:Shape',NS); by_source={}; counts=Counter()
        for shape in shapes:
            source=shape.findtext('v:Data2',default='',namespaces=NS); counts[source]+=1
            if source: by_source[source]=shape
            elif shape.findtext('v:Data1',default='',namespaces=NS)!='__page-export__': errors.append('unexpected-unidentified-shape')
            if shape.get('Type')=='Foreign' or shape.find('v:ForeignData',NS) is not None: errors.append('foreign-object')
            memberships=cell(shape,'LayerMember').split(';')
            if not memberships or any(k not in layers for k in memberships): errors.append('unlayered-or-invalid-layer:'+source)
        expected={a['id']:a for a in scene['shapes']}
        if set(expected)!=set(by_source): errors.append('source-id-set-mismatch')
        if any(counts[k]!=1 for k in expected): errors.append('duplicate-or-missing-source-id')
        for ident,item in expected.items():
            shape=by_source.get(ident)
            if shape is None: continue
            membership=[layers.get(k) for k in cell(shape,'LayerMember').split(';')]
            if membership!=[item['layer']]: errors.append('wrong-layer:'+ident)
            if item['kind'] in ('poly','rect','ellipse') and shape.find("v:Section[@N='Geometry']",NS) is None: errors.append('missing-native-geometry:'+ident)
            if 'text' in item:
                want,wpos=expected_text(item); got,gpos=native_text(shape)
                if got!=want: errors.append('text-mismatch:'+ident)
                if gpos!=wpos: errors.append('native-character-position-mismatch:'+ident)
                if shape.find("v:Section[@N='Character']/v:Row/v:Cell[@N='AsianFont']",NS) is None: errors.append('missing-east-asian-font:'+ident)
                rows=shape.findall("v:Section[@N='Character']/v:Row",NS)
                if 'italic' in item and any(bool(int(cell(row, 'Style', '0')) & 2) != item['italic'] for row in rows):
                    errors.append('native-italic-mismatch:'+ident)
                base=next((r for r in rows if r.get('IX','0')=='0'),None)
                if base is not None:
                    aliases={'Microsoft YaHei':'微软雅黑','SimSun':'宋体','SimHei':'黑体','Microsoft JhengHei':'微軟正黑體'}
                    for key,field,default in [('Font','font','Arial'),('AsianFont','fontEastAsia','Microsoft YaHei')]:
                        want=item.get(field,scene.get(field,default)); got=cell(base,key)
                        if got not in (want,aliases.get(want,want)): errors.append('font-mismatch:'+ident+':'+key)
            if item['kind']=='connector':
                if any(k not in by_source for k in (item['from'],item['to'])):
                    errors.append('connector-source-target-missing:'+ident); continue
                cons=root.findall(f"v:Connects/v:Connect[@FromSheet='{shape.get('ID')}']",NS)
                targets={c.get('ToSheet') for c in cons}
                wanted={by_source[k].get('ID') for k in (item['from'],item['to'])}
                if targets!=wanted: errors.append('connector-target-mismatch:'+ident)
                for fromcell,target in [('BeginX',item['from']),('EndX',item['to'])]:
                    if not any(c.get('FromCell')==fromcell and c.get('ToSheet')==by_source[target].get('ID') for c in cons): errors.append('connector-endpoint-mismatch:'+ident+':'+fromcell)
        return dict(file=str(path),scene=scene['name'],native_shapes=len(shapes),layers=len(layers),source_shapes=len(by_source),errors=errors,passed=not errors)
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--scene',required=True); p.add_argument('--directory',required=True); p.add_argument('--output'); a=p.parse_args()
    data=json.loads(Path(a.scene).read_text(encoding='utf-8-sig')); reports=[audit(Path(a.directory)/(s['name']+'.vsdx'),s) for s in data['scenes']]
    text=json.dumps(reports,ensure_ascii=False,indent=2)
    if a.output: Path(a.output).write_text(text,encoding='utf8')
    print(text)
    if not all(r['passed'] for r in reports): raise SystemExit(1)
if __name__=='__main__': main()
