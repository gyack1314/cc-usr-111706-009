"""重放冻结来源并显示采集状态。"""
import argparse
import json
from .transport import Replay
from .ledger import connect,receive
from .view import overview,staged_overview
def _collect(manifest):
    replay=Replay(manifest)
    db=connect(':memory:')
    collection='commissioning'
    for step in replay.steps:
        req=step['request']
        raw,receipt=replay.request(req['method'],req['url'])
        receive(db,collection,raw,receipt)
    return db,collection
def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['inspect','stages'])
    p.add_argument('manifest')
    p.add_argument('--on',default=None,help='回查日期 YYYY-MM-DD，仅显示当日及之前入库的记录')
    args=p.parse_args()
    db,collection=_collect(args.manifest)
    if args.command=='inspect':
        print(json.dumps(overview(db,collection),ensure_ascii=False,indent=2))
    else:
        print(json.dumps(staged_overview(db,collection,on=args.on),ensure_ascii=False,indent=2))
    db.close()
if __name__=='__main__':main()
