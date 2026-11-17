"""阶段化证据解释：获批、施工、送电、运营分别登记，互不推断。

记录类别：
- evidence：阶段观察，保留来源身份、观察日期、楼栋位置与声明口径。
- retraction：公告撤回，按公告身份指向原记录，只追加不删除。
- alias：承包商改名，把新名归并到既有身份，展示仍保留原文用名。
"""
import hashlib
import json
import re
from datetime import date

STAGES=('permitted','construction','energized','operational')
SCOPES=('building','campus')
KINDS=('evidence','retraction','alias')
STAGE_REASONS={'permitted':'建设许可证据尚未取得','construction':'施工迹象证据尚未取得',
               'energized':'送电证据尚未取得','operational':'正式运营公告尚未取得'}
_DATE=re.compile(r'^\d{4}-\d{2}-\d{2}$')

def _date(value,msg):
    if not isinstance(value,str) or not _DATE.match(value):
        raise ValueError(msg)
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(msg)
    return value

def is_staged_doc(raw):
    try:
        doc=json.loads(raw.decode('utf-8'))
    except Exception:
        return False
    if isinstance(doc,dict):
        return doc.get('revision')=='r2'
    if isinstance(doc,list) and doc:
        return all(isinstance(x,dict) and x.get('revision')=='r2' for x in doc)
    return False

def _key(kind,doc):
    if kind=='evidence':
        notice=doc.get('notice')
        if notice:return 'evidence:notice:'+str(notice)
        body=json.dumps(doc,ensure_ascii=False,sort_keys=True)
        return 'evidence:anon:'+hashlib.sha256(body.encode('utf-8')).hexdigest()
    if kind=='retraction':return 'retraction:'+str(doc['target'])
    return 'alias:'+str(doc['name'])

def _row(doc,ingested_on):
    if not isinstance(doc,dict) or doc.get('revision')!='r2':
        raise ValueError('来源版次不明')
    kind=doc.get('kind')
    if kind not in KINDS:raise ValueError('记录类别不明')
    claim=doc.get('claim')
    if not claim or not isinstance(claim,str):raise ValueError('缺少声明口径')
    row={'kind':kind,'key':_key(kind,doc),'claim':claim,
         'observed_on':_date(doc.get('observed_on'),'观察日期不明'),'ingested_on':ingested_on,
         'stage':None,'scope':None,'campus':None,'site':None,'phase':None,'building':None,
         'contractor':None,'notice':None,'quantity':None,'target':None,'name':None,'canonical':None,
         'payload':doc}
    if kind=='evidence':
        stage=doc.get('stage')
        if stage not in STAGES:raise ValueError('阶段不明')
        scope=doc.get('scope')
        if scope not in SCOPES:raise ValueError('声明范围不明')
        campus=doc.get('campus')
        if not campus:raise ValueError('园区不明')
        building=doc.get('building')
        if scope=='building' and not building:raise ValueError('楼栋不明')
        if scope=='campus' and building:raise ValueError('园区级声明不得绑定楼栋')
        quantity=doc.get('quantity')
        if quantity is not None and not isinstance(quantity,dict):raise ValueError('声明数量口径不明')
        row.update(stage=stage,scope=scope,campus=str(campus),
                   site=str(doc['site']) if doc.get('site') else None,
                   phase=str(doc['phase']) if doc.get('phase') else None,
                   building=str(building) if building else None,
                   contractor=str(doc['contractor']) if doc.get('contractor') else None,
                   notice=str(doc['notice']) if doc.get('notice') else None,
                   quantity=quantity)
    elif kind=='retraction':
        target=doc.get('target')
        if not target:raise ValueError('撤回对象不明')
        row['target']=str(target)
    else:
        name=doc.get('name')
        canonical=doc.get('canonical')
        if not name or not canonical:raise ValueError('更名记录不明')
        row.update(name=str(name),canonical=str(canonical))
    return row

def decode_staged(raw,receipt):
    ingested=receipt.get('collected_on')
    if not ingested:raise ValueError('缺少采集日期')
    _date(ingested,'采集日期不明')
    doc=json.loads(raw.decode('utf-8'))
    docs=doc if isinstance(doc,list) else [doc]
    return [_row(d,ingested) for d in docs]

def assess_staged(records,on=None):
    """按采集日期回查：on 当日及之前入库的记录可见，撤回与改名同样按入库日生效。"""
    if on is not None:_date(on,'回查日期不明')
    rows=[r for r in records if on is None or r['ingested_on']<=on]
    aliases={}
    for r in rows:
        if r['kind']=='alias':aliases[r['name']]=r['canonical']
    def canon(name):
        seen=set()
        while name in aliases and name not in seen:
            seen.add(name)
            name=aliases[name]
        return name
    retractions=[r for r in rows if r['kind']=='retraction']
    targets={r['target'] for r in retractions}
    evidence=[r for r in rows if r['kind']=='evidence']
    def withdrawn(e):
        return (e['notice'] and e['notice'] in targets) or e['key'] in targets
    active=[e for e in evidence if not withdrawn(e)]
    def present(e):
        return {'notice':e['notice'],'stage':e['stage'],'scope':e['scope'],
                'campus':e['campus'],'site':e['site'],'phase':e['phase'],'building':e['building'],
                'contractor':e['contractor'],
                'contractor_canonical':canon(e['contractor']) if e['contractor'] else None,
                'claim':e['claim'],'quantity':e['quantity'],
                'observed_on':e['observed_on'],'ingested_on':e['ingested_on'],
                'source':{'sha256':e['receipt_sha256'],'url':e['source_url']}}
    def by_date(items):
        return sorted(items,key=lambda e:(e['observed_on'],e['key']))
    stage_view={}
    for stage in STAGES:
        ev=by_date(e for e in active if e['stage']==stage and e['scope']=='building')
        claims=by_date(e for e in active if e['stage']==stage and e['scope']=='campus')
        buildings=sorted({e['building'] for e in ev})
        stage_view[stage]={'building_count':len(buildings),'buildings':buildings,
                           'evidence':[present(e) for e in ev],
                           'campus_claims':[present(e) for e in claims]}
    order={s:i for i,s in enumerate(STAGES)}
    building_active=by_date(e for e in active if e['scope']=='building')
    current={}
    location={}
    for e in building_active:
        b=e['building']
        if b not in current or order[e['stage']]>order[current[b]]:
            current[b]=e['stage']
        location[b]={'campus':e['campus'],'site':e['site'],'phase':e['phase']}
    contractors={}
    for e in active:
        if e['contractor']:
            contractors.setdefault(canon(e['contractor']),set()).add(e['contractor'])
    contractor_view=[{'canonical':c,'names':sorted(n)} for c,n in sorted(contractors.items())]
    campus_claims=[]
    for e in by_date(e for e in active if e['scope']=='campus'):
        matched=sorted({b['building'] for b in building_active
                        if b['campus']==e['campus']
                        and (e['phase'] is None or b['phase']==e['phase'])
                        and order[b['stage']]>=order[e['stage']]})
        claimed=(e['quantity'] or {}).get('buildings')
        if claimed is None:status='unquantified'
        elif len(matched)>=claimed:status='matched'
        else:status='pending'
        item=present(e)
        item.update({'claimed_buildings':claimed,'evidenced_buildings':matched,'status':status})
        campus_claims.append(item)
    retracted_view=[]
    for e in by_date(e for e in evidence if withdrawn(e)):
        rel=[r for r in retractions if r['target'] in (e['notice'],e['key'])]
        item=present(e)
        item['retracted_by']=[{'claim':r['claim'],'observed_on':r['observed_on'],
                               'ingested_on':r['ingested_on'],
                               'source':{'sha256':r['receipt_sha256'],'url':r['source_url']}}
                              for r in rel]
        retracted_view.append(item)
    known={e['key'] for e in evidence}|{e['notice'] for e in evidence if e['notice']}
    orphan=[{'target':r['target'],'claim':r['claim'],'observed_on':r['observed_on'],
             'ingested_on':r['ingested_on'],
             'source':{'sha256':r['receipt_sha256'],'url':r['source_url']}}
            for r in retractions if r['target'] not in known]
    pending_buildings=[]
    for b in sorted(current):
        known_stages=sorted({e['stage'] for e in building_active if e['building']==b},key=order.get)
        missing=[s for s in STAGES if s not in known_stages]
        if missing:
            pending_buildings.append({'building':b,**location[b],
                                      'known_stages':known_stages,'missing_stages':missing})
    pending_claims=[c for c in campus_claims if c['status']!='matched']
    reasons=[]
    for stage in STAGES:
        if not stage_view[stage]['buildings'] and not stage_view[stage]['campus_claims']:
            reasons.append(STAGE_REASONS[stage])
    if pending_claims:reasons.append('园区级声明数量尚未由楼栋级证据核实')
    if orphan:reasons.append('存在未匹配到原文的撤回记录')
    return {'as_of':on,'stages':stage_view,'current_stage':current,
            'contractors':contractor_view,'campus_claims':campus_claims,
            'retracted':retracted_view,'orphan_retractions':orphan,
            'pending':{'buildings':pending_buildings,'campus_claims':pending_claims},
            'publishable':not reasons and not pending_buildings,'reasons':reasons}
