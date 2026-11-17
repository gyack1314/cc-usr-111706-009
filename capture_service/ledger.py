"""按来源身份原子登记原文与领域记录。"""
import hashlib
import json
import sqlite3
from .domain import decode
from .stages import decode_staged,is_staged_doc
SCHEMA="""
CREATE TABLE IF NOT EXISTS receipts(collection TEXT NOT NULL,body_sha256 TEXT NOT NULL,source_url TEXT NOT NULL,status INTEGER NOT NULL,raw BLOB NOT NULL,PRIMARY KEY(collection,body_sha256));
CREATE TABLE IF NOT EXISTS entities(collection TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,version TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(collection,entity_type,entity_id,version),FOREIGN KEY(collection,receipt_sha256) REFERENCES receipts(collection,body_sha256));
CREATE TABLE IF NOT EXISTS staged_records(collection TEXT NOT NULL,record_key TEXT NOT NULL,kind TEXT NOT NULL,stage TEXT,scope TEXT,campus TEXT,site TEXT,phase TEXT,building TEXT,contractor TEXT,notice TEXT,claim TEXT,quantity_json TEXT,observed_on TEXT,ingested_on TEXT NOT NULL,target TEXT,name TEXT,canonical TEXT,receipt_sha256 TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(collection,record_key),FOREIGN KEY(collection,receipt_sha256) REFERENCES receipts(collection,body_sha256));
"""
def connect(path):
    c=sqlite3.connect(path)
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript(SCHEMA)
    return c
def receive(c,collection,raw,receipt):
    if receipt['status']!=200:raise ValueError('来源未返回成功正文')
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=receipt['body_sha256']:raise ValueError('收据与原文不符')
    staged=is_staged_doc(raw)
    rows=decode_staged(raw,receipt) if staged else decode(raw,receipt)
    with c:
        c.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?)',(collection,sha,receipt['url'],receipt['status'],raw))
        if staged:
            for row in rows:
                payload=json.dumps(row['payload'],ensure_ascii=False,sort_keys=True)
                prior=c.execute('SELECT payload_json FROM staged_records WHERE collection=? AND record_key=?',(collection,row['key'])).fetchone()
                if prior and prior[0]!=payload:raise ValueError('同一记录身份原文冲突')
                quantity=json.dumps(row['quantity'],ensure_ascii=False,sort_keys=True) if row['quantity'] is not None else None
                c.execute('INSERT OR IGNORE INTO staged_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (collection,row['key'],row['kind'],row['stage'],row['scope'],row['campus'],row['site'],
                           row['phase'],row['building'],row['contractor'],row['notice'],row['claim'],quantity,
                           row['observed_on'],row['ingested_on'],row['target'],row['name'],row['canonical'],
                           sha,payload))
        else:
            for row in rows:
                payload=json.dumps(row['payload'],ensure_ascii=False,sort_keys=True)
                key=(collection,row['type'],row['id'],row['version'])
                prior=c.execute('SELECT receipt_sha256,payload_json FROM entities WHERE collection=? AND entity_type=? AND entity_id=? AND version=?',key).fetchone()
                if prior and prior!=(sha,payload):raise ValueError('同一实体版本原文冲突')
                c.execute('INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)',(*key,sha,payload))
    return sha
def entities(c,collection):
    return [dict(type=r[0],id=r[1],version=r[2],source=r[3],payload=json.loads(r[4])) for r in c.execute('SELECT entity_type,entity_id,version,receipt_sha256,payload_json FROM entities WHERE collection=? ORDER BY entity_type,entity_id,version',(collection,))]
def staged_records(c,collection):
    keys=('key','kind','stage','scope','campus','site','phase','building','contractor','notice','claim',
          'quantity_json','observed_on','ingested_on','target','name','canonical','receipt_sha256','source_url')
    q=('SELECT s.record_key,s.kind,s.stage,s.scope,s.campus,s.site,s.phase,s.building,s.contractor,s.notice,'
       's.claim,s.quantity_json,s.observed_on,s.ingested_on,s.target,s.name,s.canonical,s.receipt_sha256,r.source_url '
       'FROM staged_records s JOIN receipts r ON r.collection=s.collection AND r.body_sha256=s.receipt_sha256 '
       'WHERE s.collection=? ORDER BY s.ingested_on,s.record_key')
    rows=[]
    for r in c.execute(q,(collection,)):
        d=dict(zip(keys,r))
        d['quantity']=json.loads(d.pop('quantity_json')) if d['quantity_json'] is not None else None
        rows.append(d)
    return rows
