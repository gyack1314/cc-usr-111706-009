"""核对阶段化采集：分阶段呈现、数量口径不摊派、多次送电去重、撤回与改名、按日回查。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from capture_service.transport import Replay
from capture_service.ledger import connect,receive,staged_records
from capture_service.view import staged_overview
ROOT=Path(__file__).resolve().parents[1]
COLLECTION='commissioning'
EMPTY=hashlib.sha256(b'').hexdigest()
ORIGIN='https://facility.example.test'

def collect(manifest):
    replay=Replay(manifest)
    db=connect(':memory:')
    for step in replay.steps:
        req=step['request']
        raw,receipt=replay.request(req['method'],req['url'])
        receive(db,COLLECTION,raw,receipt)
    return db

def write_manifest(root,entries):
    """entries: (url_path, doc, collected_on)；collected_on 为 None 时省略采集日期。"""
    steps=[]
    for i,(path,doc,collected) in enumerate(entries):
        raw=json.dumps(doc,ensure_ascii=False,sort_keys=True).encode('utf-8')
        name='source-%d.bin'%i
        (root/name).write_bytes(raw)
        resp={'file':name,'status':200,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        if collected is not None:resp['collected_on']=collected
        steps.append({'request':{'method':'GET','url':ORIGIN+'/'+path,'body_sha256':EMPTY},'response':resp})
    manifest=root/'manifest.json'
    manifest.write_text(json.dumps({'allowed_origins':[ORIGIN],'steps':steps},ensure_ascii=False),encoding='utf-8')
    return manifest

def evidence(notice='PR-1',stage='permitted',scope='building',building='B-1',**extra):
    doc={'kind':'evidence','revision':'r2','notice':notice,'stage':stage,'scope':scope,
         'campus':'C-1','site':'P-1','phase':'一期','observed_on':'2026-01-15','claim':'声明原文'}
    if building is not None:doc['building']=building
    doc.update(extra)
    return doc

class StagedIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=collect(ROOT/'data/staged.json')
    @classmethod
    def tearDownClass(cls):
        cls.db.close()
    def view(self,on=None):
        return staged_overview(self.db,COLLECTION,on=on)
    def test_stages_presented_separately_with_provenance(self):
        view=self.view()
        self.assertEqual(view['stages']['permitted']['buildings'],['B-1'])
        self.assertEqual(view['stages']['construction']['buildings'],['B-1'])
        self.assertEqual(view['stages']['energized']['buildings'],['B-1','B-2'])
        self.assertEqual(view['stages']['operational']['buildings'],['B-1'])
        record=view['stages']['permitted']['evidence'][0]
        self.assertEqual(record['building'],'B-1')
        self.assertEqual(record['campus'],'C-1')
        self.assertEqual(record['site'],'P-1')
        self.assertEqual(record['observed_on'],'2026-01-15')
        self.assertEqual(record['ingested_on'],'2026-01-16')
        self.assertEqual(record['claim'],'B-1 数据楼取得建设工程施工许可')
        self.assertEqual(len(record['source']['sha256']),64)
        self.assertTrue(record['source']['url'].startswith(ORIGIN))
    def test_multiple_energizations_count_building_once(self):
        view=self.view()
        b1=[e for e in view['stages']['energized']['evidence'] if e['building']=='B-1']
        self.assertEqual(len(b1),2)
        self.assertEqual(view['stages']['energized']['building_count'],2)
        self.assertEqual(view['current_stage'],{'B-1':'operational','B-2':'energized'})
    def test_campus_claim_not_allocated_to_sites(self):
        view=self.view()
        self.assertEqual(view['stages']['construction']['building_count'],1)
        self.assertEqual(view['stages']['construction']['buildings'],['B-1'])
        claims=view['campus_claims']
        self.assertEqual(len(claims),1)
        claim=claims[0]
        self.assertEqual(claim['notice'],'N-2')
        self.assertEqual(claim['scope'],'campus')
        self.assertEqual(claim['phase'],'二期')
        self.assertEqual(claim['claimed_buildings'],4)
        self.assertEqual(claim['evidenced_buildings'],[])
        self.assertEqual(claim['status'],'pending')
        self.assertIn(claim,view['pending']['campus_claims'])
    def test_contractor_rename_merges_identity(self):
        view=self.view()
        self.assertEqual(len(view['contractors']),1)
        contractor=view['contractors'][0]
        self.assertEqual(contractor['canonical'],'建设集团甲')
        self.assertCountEqual(contractor['names'],['建设集团甲','甲建工集团'])
        b2=[e for e in view['stages']['energized']['evidence'] if e['building']=='B-2'][0]
        self.assertEqual(b2['contractor'],'甲建工集团')
        self.assertEqual(b2['contractor_canonical'],'建设集团甲')
    def test_retraction_withdraws_but_keeps_history(self):
        view=self.view()
        self.assertEqual(view['stages']['permitted']['buildings'],['B-1'])
        self.assertEqual(len(view['retracted']),1)
        withdrawn=view['retracted'][0]
        self.assertEqual(withdrawn['notice'],'PR-3')
        self.assertEqual(withdrawn['building'],'B-3')
        self.assertEqual(withdrawn['retracted_by'][0]['claim'],'发布方撤回 B-3 施工许可公告')
        self.assertEqual(len(withdrawn['retracted_by'][0]['source']['sha256']),64)
    def test_pending_scope_lists_missing_stages(self):
        view=self.view()
        pending={p['building']:p for p in view['pending']['buildings']}
        self.assertNotIn('B-1',pending)
        self.assertEqual(pending['B-2']['known_stages'],['energized'])
        self.assertEqual(pending['B-2']['missing_stages'],['permitted','construction','operational'])
        self.assertEqual(pending['B-2']['site'],'P-2')
        self.assertFalse(view['publishable'])
        self.assertTrue(view['reasons'])
    def test_as_of_replays_known_evidence_and_pending_scope(self):
        early=self.view(on='2026-03-01')
        self.assertEqual(early['as_of'],'2026-03-01')
        self.assertEqual(early['stages']['permitted']['buildings'],['B-1'])
        self.assertEqual(early['stages']['construction']['buildings'],[])
        self.assertEqual(early['stages']['energized']['buildings'],[])
        pending={p['building']:p for p in early['pending']['buildings']}
        self.assertEqual(pending['B-1']['missing_stages'],['construction','energized','operational'])
        before_retract=self.view(on='2026-05-15')
        self.assertEqual(before_retract['stages']['permitted']['buildings'],['B-1','B-3'])
        self.assertEqual(before_retract['retracted'],[])
        after_retract=self.view(on='2026-06-20')
        self.assertEqual(after_retract['stages']['permitted']['buildings'],['B-1'])
        self.assertEqual(len(after_retract['retracted']),1)
        self.assertEqual(after_retract['retracted'][0]['building'],'B-3')
    def test_as_of_before_rename_keeps_names_separate(self):
        view=self.view(on='2026-04-15')
        self.assertEqual(view['contractors'],[{'canonical':'建设集团甲','names':['建设集团甲']}])

class StagedRejection(unittest.TestCase):
    def run_manifest(self,entries):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=write_manifest(Path(tmp),entries)
            replay=Replay(manifest)
            db=connect(':memory:')
            try:
                for step in replay.steps:
                    req=step['request']
                    raw,receipt=replay.request(req['method'],req['url'])
                    receive(db,COLLECTION,raw,receipt)
            finally:
                db.close()
    def test_missing_collected_on_rejected(self):
        with self.assertRaises(ValueError):
            self.run_manifest([('permits/b1',evidence(),None)])
    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError):
            self.run_manifest([('permits/b1',evidence(stage='launched'),'2026-01-16')])
    def test_campus_scope_bound_to_building_rejected(self):
        doc=evidence(notice='N-9',stage='construction',scope='campus',building='B-9')
        with self.assertRaises(ValueError):
            self.run_manifest([('news/n9',doc,'2026-01-16')])
    def test_missing_claim_rejected(self):
        doc=evidence()
        del doc['claim']
        with self.assertRaises(ValueError):
            self.run_manifest([('permits/b1',doc,'2026-01-16')])
    def test_same_notice_conflict_rolls_back(self):
        first=evidence(claim='B-1 取得施工许可')
        second=evidence(claim='B-1 取得的是另一份许可')
        with tempfile.TemporaryDirectory() as tmp:
            manifest=write_manifest(Path(tmp),[('permits/b1',first,'2026-01-16'),
                                               ('permits/b1b',second,'2026-01-17')])
            replay=Replay(manifest)
            db=connect(':memory:')
            req=replay.steps[0]['request']
            raw,receipt=replay.request(req['method'],req['url'])
            receive(db,COLLECTION,raw,receipt)
            before=staged_records(db,COLLECTION)
            req=replay.steps[1]['request']
            raw,receipt=replay.request(req['method'],req['url'])
            with self.assertRaises(ValueError):
                receive(db,COLLECTION,raw,receipt)
            self.assertEqual(staged_records(db,COLLECTION),before)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],1)
            db.close()
    def test_orphan_retraction_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries=[('news/retract',{'kind':'retraction','revision':'r2','target':'NOPE-1',
                                      'observed_on':'2026-02-01','claim':'撤回不存在的公告'},'2026-02-02')]
            manifest=write_manifest(Path(tmp),entries)
            db=collect(manifest)
            view=staged_overview(db,COLLECTION)
            self.assertEqual(len(view['orphan_retractions']),1)
            self.assertEqual(view['orphan_retractions'][0]['target'],'NOPE-1')
            self.assertIn('存在未匹配到原文的撤回记录',view['reasons'])
            db.close()
