"""Reserve/replace four-paragraph figure slots with byte-preserving OOXML edits."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid
from xml.parsers import expat
from xml.sax.saxutils import escape,quoteattr
from zipfile import ZipFile,ZIP_DEFLATED

from lxml import etree as E
from docx import Document
from docx.shared import Inches,Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
R='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
NS={'w':W,'m':M}
def sha(blob):return hashlib.sha256(blob).hexdigest()
def text(node):return ''.join(node.xpath('.//w:t/text() | .//m:t/text()',namespaces=NS))
def blank(node):
    return node.tag==f'{{{W}}}p' and not text(node) and not node.xpath('.//w:drawing | .//w:pict | .//w:object | .//w:br | .//w:fldChar | .//w:instrText | .//m:oMath | .//w:bookmarkStart | .//w:bookmarkEnd',namespaces=NS)
def body_spans(blob):
    parser=expat.ParserCreate();stack=[];spans=[];start=None
    def begin(name,attrs):
        nonlocal start
        stack.append(name)
        if len(stack)==3 and stack[-2].split(':')[-1]=='body':start=parser.CurrentByteIndex
    def end(name):
        if len(stack)==3 and stack[-2].split(':')[-1]=='body':
            ix=parser.CurrentByteIndex
            if blob[ix:ix+2]==b'</':ix=blob.index(b'>',ix)+1
            spans.append((start,ix))
        stack.pop()
    parser.StartElementHandler=begin;parser.EndElementHandler=end;parser.Parse(blob,True)
    return spans
def slot_xml(caption):
    # Namespace is local so documents need not use the conventional w prefix.
    start=f'<w:p xmlns:w="{W}">'
    blank_p=start+'<w:pPr><w:keepNext/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:p>'
    cap=start+'<w:pPr><w:jc w:val="center"/><w:keepLines/></w:pPr><w:r><w:t>'+escape(caption)+'</w:t></w:r></w:p>'
    return (blank_p*4+cap).encode('utf-8')
def append_child(blob,root_name,child):
    root=E.fromstring(blob);prefix=(root.prefix+':') if root.prefix else ''
    tag=prefix+root_name
    child=child.replace(b'<CHILD ',('<'+prefix).encode(),1)
    closing=('</'+tag+'>').encode()
    if closing in blob:return blob.replace(closing,child+closing,1)
    # An empty root may be self-closing; preserve its existing declaration.
    pos=blob.rfind(b'/>')
    if pos<0:raise ValueError('Unsupported package XML root')
    return blob[:pos]+b'>'+child+closing+blob[pos+2:]
def picture_xml(blob,width,rid,docid,caption,alt):
    doc=Document();p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    fmt=p.paragraph_format;fmt.keep_with_next=True;fmt.keep_together=True
    fmt.space_before=Pt(5);fmt.space_after=Pt(3);fmt.line_spacing=1.0
    run=p.add_run();run.font.size=Pt(1);run.add_picture(BytesIO(blob),width=Inches(width))
    for n in p._p.xpath('.//a:blip'):n.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed',rid)
    for n in p._p.xpath('.//wp:docPr'):
        n.set('id',str(docid));n.set('name',caption);n.set('descr',alt or caption)
    return E.tostring(p._p,encoding='utf-8')
def available_width(root):
    widths=[];complex_layout=False
    for sect in root.xpath('.//w:sectPr',namespaces=NS):
        size=sect.find('w:pgSz',NS);margins=sect.find('w:pgMar',NS)
        if size is None or margins is None:continue
        usable=(int(size.get(f'{{{W}}}w'))-int(margins.get(f'{{{W}}}left','0'))-int(margins.get(f'{{{W}}}right','0')))/1440
        cols=sect.find('w:cols',NS)
        if cols is not None:
            n=int(cols.get(f'{{{W}}}num','1'))
            actual=cols.findall('w:col',NS)
            if n>1 or len(actual)>1:
                complex_layout=True
                usable=min(int(c.get(f'{{{W}}}w'))/1440 for c in actual) if actual else (usable-(n-1)*int(cols.get(f'{{{W}}}space','720'))/1440)/n
        widths.append(usable)
    if not widths or min(widths)<=0:raise ValueError('Cannot determine document usable width')
    return min(widths),complex_layout or len(widths)>1

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['reserve','insert'],required=True)
    ap.add_argument('--docx',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True)
    out=ap.add_mutually_exclusive_group();out.add_argument('--output',type=Path);out.add_argument('--in-place',action='store_true')
    ap.add_argument('--backup',type=Path);ap.add_argument('--dry-run',action='store_true')
    args=ap.parse_args()
    source=args.docx.resolve();plan_path=args.plan.resolve()
    figures=json.loads(plan_path.read_text(encoding='utf-8-sig'))['figures']
    if not figures:raise ValueError('Empty figure plan')
    captions=[f['caption'] for f in figures]
    if any(not isinstance(c,str) or not c.strip() for c in captions) or len(set(captions))!=len(captions):raise ValueError('Missing/duplicate captions')
    if not args.dry_run and not (args.output or args.in_place):raise ValueError('Choose --output or --in-place')
    destination=(source if args.in_place else args.output.resolve() if args.output else None)
    backup=args.backup.resolve() if args.backup else None
    if args.in_place and not args.dry_run and backup is None:raise ValueError('--in-place requires a unique --backup')
    if destination==source and not args.in_place:raise ValueError('Use --in-place to replace the source')
    if backup and (backup==source or backup==destination or backup.exists()):raise ValueError('Backup must be a new, separate file')
    if destination and destination!=source and destination.exists():raise FileExistsError(destination)
    original=source.read_bytes();digest=sha(original);token=uuid.uuid4().hex
    with ZipFile(BytesIO(original)) as zin:
        xml=zin.read('word/document.xml');root=E.fromstring(xml);body=root.find('w:body',NS)
        ranges=body_spans(xml)
        if body is None or len(body)!=len(ranges):raise ValueError('Unsupported document body')
        usable,complex_layout=available_width(root)
        occupied=set();patches=[];media=[];entries=[]
        rel=zin.read('word/_rels/document.xml.rels');ct=zin.read('[Content_Types].xml')
        max_docid=max([int(n.get('id','0')) for n in root.xpath('//*[local-name()="docPr"]')]+[0])
        for number,item in enumerate(figures,1):
            caption=item['caption'];matches=[i for i,n in enumerate(body) if n.tag==f'{{{W}}}p' and text(n)==caption]
            if len(matches)>1:raise ValueError(f'Ambiguous caption: {caption}')
            if args.mode=='reserve':
                if matches:
                    ix=matches[0]
                    if ix<4 or not all(blank(n) for n in list(body)[ix-4:ix]):raise ValueError(f'Existing caption is not an empty four-paragraph slot: {caption}')
                    entries.append(dict(caption=caption,status='already_reserved'));continue
                anchor=item.get('anchor')
                anchors=[i for i,n in enumerate(body) if n.tag==f'{{{W}}}p' and text(n)==anchor]
                if len(anchors)!=1:raise ValueError(f'Anchor must match one complete paragraph: {caption}')
                a=b=ranges[anchors[0]][1];old=b'';new=slot_xml(caption)
            else:
                if len(matches)!=1:raise ValueError(f'Caption not found: {caption}')
                ix=matches[0]
                if ix<4 or not all(blank(n) for n in list(body)[ix-4:ix]):raise ValueError(f'Not an empty four-paragraph slot: {caption}')
                a=ranges[ix-4][0];b=ranges[ix-1][1];old=xml[a:b]
                image=Path(item['image']);image=(plan_path.parent/image).resolve() if not image.is_absolute() else image.resolve()
                blob=image.read_bytes()
                with Image.open(BytesIO(blob)) as im:
                    if im.format!='PNG':raise ValueError('Expected PNG export')
                    pixels=im.size
                if complex_layout and 'width_inches' not in item:raise ValueError('Explicit width required for multi-section/column document')
                width=float(item.get('width_inches',min(6.35,usable)))
                if not math.isfinite(width) or width<=0 or width>usable+.001:raise ValueError('Figure width exceeds available text/column width')
                rid=f'rIdVisio{token}_{number}';member=f'word/media/visio_{token}_{number}.png'
                new=picture_xml(blob,width,rid,max_docid+number,caption,item.get('alt'))
                child=('<CHILD Relationship Id='+quoteattr(rid)+' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target='+quoteattr(member.removeprefix('word/'))+'/>').encode()
                rel=append_child(rel,'Relationships',child)
                media.append((member,blob))
                item_info=dict(image=str(image),image_sha256=sha(blob),pixels=pixels,width_inches=width)
            if (a,b) in occupied:raise ValueError('Overlapping figure locations; use distinct anchors')
            if any(a<bb and b>aa for aa,bb in occupied):raise ValueError('Overlapping figure ranges')
            occupied.add((a,b));patches.append((a,b,old,new))
            entries.append(dict(caption=caption,status=args.mode,**(item_info if args.mode=='insert' else {})))
        report=dict(source=str(source),mode=args.mode,changed=bool(patches),before_sha256=digest,figures=entries)
        if args.dry_run or not patches:
            report['dry_run']=args.dry_run;print(json.dumps(report,ensure_ascii=False,indent=2));return
        amended=xml
        for a,b,old,new in sorted(patches,key=lambda p:p[0],reverse=True):amended=amended[:a]+new+amended[b:]
        recovered=amended
        for a,b,old,new in patches:
            if recovered.count(new)!=1:raise ValueError('Ambiguous generated block')
            recovered=recovered.replace(new,old,1)
        if recovered!=xml:raise AssertionError('Original XML preservation failed')
        newroot=E.fromstring(amended)
        oldmath=[E.tostring(n,method='c14n') for n in root.xpath('.//m:oMath',namespaces=NS)]
        if oldmath!=[E.tostring(n,method='c14n') for n in newroot.xpath('.//m:oMath',namespaces=NS)]:raise AssertionError('Original math changed')
        replacements={'word/document.xml':amended}
        if args.mode=='insert':
            replacements['word/_rels/document.xml.rels']=rel
            defaults=E.fromstring(ct).findall(f'{{{CT}}}Default')
            png=[d for d in defaults if d.get('Extension','').lower()=='png']
            if png and any(d.get('ContentType')!='image/png' for d in png):raise ValueError('Conflicting PNG content type')
            if not png:ct=append_child(ct,'Types',b'<CHILD Default Extension="png" ContentType="image/png"/>')
            if ct!=zin.read('[Content_Types].xml'):replacements['[Content_Types].xml']=ct
        destination.parent.mkdir(parents=True,exist_ok=True)
        fd,tempname=tempfile.mkstemp(suffix='.pending.docx',dir=destination.parent);os.close(fd);pending=Path(tempname)
        with ZipFile(pending,'w') as zout:
            zout.comment=zin.comment
            for info in zin.infolist():zout.writestr(deepcopy(info),replacements.get(info.filename,zin.read(info.filename)))
            for member,blob in media:zout.writestr(member,blob,compress_type=ZIP_DEFLATED)
        with ZipFile(pending) as check:
            if not all(zin.read(n)==check.read(n) for n in zin.namelist() if n not in replacements):raise AssertionError('Unrelated package parts changed')
            E.fromstring(check.read('word/document.xml'))
            E.fromstring(check.read('word/_rels/document.xml.rels'))
        # Parse independently before committing; this catches broken OPC relationships.
        parsed=Document(pending)
        if args.mode=='insert' and len(parsed.inline_shapes)!=len(Document(BytesIO(original)).inline_shapes)+len(patches):raise AssertionError('Incorrect image count')
        if sha(source.read_bytes())!=digest:raise RuntimeError('Source changed concurrently; pending file retained')
        if backup:backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(original)
        os.replace(pending,destination)
        report.update(output=str(destination),backup=str(backup) if backup else None,after_sha256=sha(destination.read_bytes()),original_document_xml_recoverable_byte_for_byte=True,original_math_preserved=True,other_package_parts_unchanged=True)
        audit=destination.with_name(destination.stem+'.'+token[:8]+'.figure-audit.json')
        audit.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
