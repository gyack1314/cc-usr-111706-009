"""按领域解释结果展示已接收证据及缺口。"""
from .ledger import entities,staged_records
from .domain import assess
from .stages import assess_staged
def overview(c,collection):
    rows=entities(c,collection)
    result=assess(rows)
    result['collection']=collection
    result['records']=[{'type':r['type'],'id':r['id'],'version':r['version'],'source_sha256':r['source']} for r in rows]
    return result
def staged_overview(c,collection,on=None):
    result=assess_staged(staged_records(c,collection),on=on)
    result['collection']=collection
    return result
