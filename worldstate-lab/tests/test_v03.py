"""V0.3 offline rules verification: schema, deadlines, consent, staged cargo.
All operations use the unmodified World.apply ledger and transaction boundary.
"""
from __future__ import annotations

import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from worldstate import World, WorldRuleError
from worldstate.scenarios import seed_world
from worldstate.v03 import migrate_v3, V3_TABLES


class V03Rules(unittest.TestCase):
    def setUp(self):
        self.w=World()
        self.s=seed_world(self.w)

    def tearDown(self):
        self.w.close()

    def ev(self, kind, *, actor='system', **p):
        return self.s.emit(kind, actor=actor, **{'__v':3, **p})

    def row(self, table, col, key):
        r=self.w.db.execute(f'SELECT * FROM {table} WHERE {col}=?',(key,)).fetchone()
        return dict(r) if r is not None else None

    def setup_case(self):
        self.s.emit('CharacterInjured',character_id='d1',severity=93)
        self.s.emit('MedicalCaseOpened',case_id='case1',character_id='d1',deadline_tick=self.s.tick+15,hospital_site='hospital')
        self.ev('TaskPlanned',task_id='deadline1',case_id='case1',due_tick=self.row('medical_cases','case_id','case1')['deadline_tick']+1)

    def setup_evidence(self, clinical=True):
        classification='clinical' if clinical else 'private'
        self.s.emit('EvidenceRecorded',actor='b1',record_id='E1',summary='PRIVATE_FAKE_STUDY',source='lab',classification=classification)
        if clinical:self.ev('EvidenceSubjectBound',record_id='E1',subject_id='a1')

    def setup_convoy(self):
        self.s.emit('OrganizationRegistered',org_id='west',name='Westbank Freight')
        self.s.emit('DepotRegistered',holder='organization:union',location='Camp')
        self.s.emit('DepotRegistered',holder='organization:west',location='Westbank')
        self.s.emit('CarrierRegistered',carrier_id='C1',owner_org='union',location='Camp',capacity=50,fuel=300)
        self.s.emit('StockProvisioned',holder='organization:union',material='food',quantity=125)

    def trip(self, plan=None, qty=15):
        if plan is None:plan=['road:civic-camp','road:lower-east','road:lower-west']
        return self.ev('ConvoyDispatched',actor='c1',convoy_id='V1',carrier_id='C1',source_holder='organization:union',destination_holder='organization:west',material='food',quantity=qty,route_ids=plan)

    def arrive(self, delta=12):
        self.s.tick+=delta
        return self.ev('ConvoyLegArrived',convoy_id='V1')

    def depart(self):
        return self.ev('ConvoyLegDeparted',convoy_id='V1')

    def test_01_database_revision_registry_not_v02_compat_pragma(self):
        self.assertEqual(2,self.w.db.execute('PRAGMA user_version').fetchone()[0])
        self.assertEqual((3,2),tuple(self.w.db.execute('SELECT revision,created_from FROM worldstate_schema').fetchone()))
        for table in V3_TABLES:self.assertIn(table,self.w.snapshot())

    def test_02_atomic_migration_rollback_when_failure_injected(self):
        db=sqlite3.connect(':memory:')
        db.execute('PRAGMA user_version=2')
        with self.assertRaisesRegex(RuntimeError,'SIMULATED_MIGRATION_FAILURE'):
            migrate_v3(db,simulate_failure=True)
        self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='worldstate_schema'").fetchone())
        self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='scheduled_tasks'").fetchone())
        migrate_v3(db)
        self.assertEqual(3,db.execute('SELECT revision FROM worldstate_schema').fetchone()[0])
        migrate_v3(db)
        db.close()

    def test_03_new_events_reject_missing_or_bad_version(self):
        self.setup_case()
        for tag in (None,2,4,'3',True):
            p={'task_id':'deadline_other','case_id':'case1','due_tick':self.row('medical_cases','case_id','case1')['deadline_tick']+1}
            if tag is not None:p['__v']=tag
            before=self.w.state_hash()
            with self.assertRaises(WorldRuleError):self.s.emit('TaskPlanned',**p)
            self.assertEqual(before,self.w.state_hash())

    def test_04_legacy_events_reject_new_version_tag(self):
        with self.assertRaises(WorldRuleError):
            self.s.emit('RoadClosed',link_id='Cydren Skygate',**{'__v':3})

    def test_05_deadline_scheduler_expires_unrescued(self):
        self.setup_case()
        due=self.row('scheduled_tasks','task_id','deadline1')['due_tick']
        self.assertEqual([],self.w.run_due(due-1))
        self.assertEqual(1,len(self.w.run_due(due)))
        self.assertEqual('deceased',self.row('characters','character_id','d1')['state'])
        self.assertEqual('expired',self.row('medical_cases','case_id','case1')['state'])
        self.assertEqual('executed',self.row('scheduled_tasks','task_id','deadline1')['state'])
        self.assertEqual([],self.w.run_due(due))
        self.assertEqual('PASS',self.w.audit_state()['status'])

    def test_06_stabilized_patient_scheduler_skips_without_killing(self):
        self.setup_case()
        self.s.emit('CharacterMoved',actor='b1',character_id='b1',route_id='road:civic-camp',**{'from':'Civic','to':'Camp'})
        self.s.emit('CharacterMoved',actor='b1',character_id='b1',route_id='road:camp-forest',**{'from':'Camp','to':'Forest'})
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='case1')
        due=self.row('scheduled_tasks','task_id','deadline1')['due_tick']
        self.w.run_due(due)
        self.assertEqual('stabilized',self.row('characters','character_id','d1')['state'])
        self.assertEqual('skipped',self.row('scheduled_tasks','task_id','deadline1')['state'])
        self.assertEqual('PASS',self.w.audit_state()['status'])

    def test_07_task_cannot_trigger_early_or_twice(self):
        self.setup_case()
        due=self.row('scheduled_tasks','task_id','deadline1')['due_tick']
        with self.assertRaisesRegex(WorldRuleError,'not yet due'):
            self.ev('TaskTriggered',task_id='deadline1')
        self.w.run_due(due)
        with self.assertRaises(WorldRuleError):
            self.s.emit('TaskTriggered',task_id='deadline1',**{'__v':3})

    def test_08_task_can_be_cancelled(self):
        self.setup_case()
        self.ev('TaskCanceled',task_id='deadline1')
        due=self.row('scheduled_tasks','task_id','deadline1')['due_tick']
        self.assertEqual([],self.w.run_due(due))
        self.assertEqual('incapacitated',self.row('characters','character_id','d1')['state'])

    def test_09_task_commit_failure_does_not_kill_patient(self):
        self.setup_case()
        due=self.row('scheduled_tasks','task_id','deadline1')['due_tick']
        before=self.w.state_hash()
        with self.assertRaisesRegex(RuntimeError,'SIMULATED_CRASH'):
            self.w.apply('scheduled:deadline1','TaskTriggered','system',{'__v':3,'task_id':'deadline1'},tick=due,crash_before_commit=True)
        self.assertEqual(before,self.w.state_hash())
        self.w.run_due(due)
        self.assertEqual('deceased',self.row('characters','character_id','d1')['state'])

    def test_10_repeated_scheduler_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'restart.sqlite3'
            with World(f) as w:
                s=seed_world(w)
                s.emit('CharacterInjured',character_id='d1',severity=93)
                s.emit('MedicalCaseOpened',case_id='case1',character_id='d1',deadline_tick=s.tick+12,hospital_site='hospital')
                w.apply('planner','TaskPlanned','system',{'__v':3,'task_id':'taskX','case_id':'case1','due_tick':w.db.execute("SELECT deadline_tick FROM medical_cases WHERE case_id='case1'").fetchone()[0]+1},tick=s.tick+1)
            with World(f) as w:
                w.run_due(1000)
                self.assertEqual(1,len(w.db.execute("SELECT * FROM ledger WHERE event_id='scheduled:taskX'").fetchall()))
                self.assertEqual('PASS',w.audit_state()['status'])

    def test_11_no_clinical_access_without_subject(self):
        self.s.emit('EvidenceRecorded',actor='b1',record_id='E1',summary='clinical record',source='clinic',classification='clinical')
        with self.assertRaisesRegex(WorldRuleError,'consent required'):
            self.ev('EvidenceAccessGranted',actor='b1',record_id='E1',grant_id='G1',grantee='c1',scope='read',expires_tick=self.s.tick+20)

    def test_12_subject_approves_clinical_evidence_access(self):
        self.setup_evidence()
        self.assertFalse(self.w.evidence_visible_to('E1','c1'))
        self.ev('EvidenceAccessGranted',actor='a1',record_id='E1',grant_id='G1',grantee='c1',scope='read',expires_tick=self.s.tick+20)
        self.assertTrue(self.w.evidence_visible_to('E1','c1'))
        self.ev('EvidenceViewed',actor='c1',record_id='E1',read_id='read1')
        self.assertEqual(1,len(self.w.snapshot()['evidence_reads']))
        self.assertNotIn('PRIVATE_FAKE_STUDY',self.w.ledger()[-1]['payload'].values())
        self.assertEqual('PASS',self.w.audit_state()['status'])

    def test_13_consent_grant_revocable(self):
        self.setup_evidence()
        self.ev('EvidenceAccessGranted',actor='a1',record_id='E1',grant_id='G1',grantee='c1',scope='read',expires_tick=self.s.tick+30)
        self.ev('EvidenceAccessRevoked',actor='a1',grant_id='G1')
        self.assertFalse(self.w.evidence_visible_to('E1','c1'))
        with self.assertRaisesRegex(WorldRuleError,'access denied'):
            self.ev('EvidenceViewed',actor='c1',record_id='E1',read_id='read2')

    def test_14_consent_grant_expires(self):
        self.setup_evidence(clinical=False)
        self.ev('EvidenceAccessGranted',actor='b1',record_id='E1',grant_id='G1',grantee='c1',scope='read',expires_tick=self.s.tick+2)
        self.s.tick+=4
        with self.assertRaisesRegex(WorldRuleError,'access denied'):
            self.ev('EvidenceViewed',actor='c1',record_id='E1',read_id='read2')

    def test_15_non_owner_cannot_grant_private_access(self):
        self.setup_evidence(clinical=False)
        with self.assertRaisesRegex(WorldRuleError,'author'):
            self.ev('EvidenceAccessGranted',actor='c1',record_id='E1',grant_id='G1',grantee='a1',scope='read',expires_tick=self.s.tick+10)

    def test_16_subject_cannot_publish_clinical_record(self):
        self.setup_evidence()
        with self.assertRaises(WorldRuleError):self.s.emit('EvidencePublished',actor='b1',record_id='E1')

    def test_17_two_hop_convoy_moves_cargo_not_teleport(self):
        self.setup_convoy()
        self.trip()
        self.assertEqual(110,self.w.stock('organization:union','food'))
        self.assertEqual(0,self.w.stock('organization:west','food'))
        with self.assertRaisesRegex(WorldRuleError,'not ready'):
            self.ev('ConvoyLegArrived',convoy_id='V1')
        self.arrive()
        self.assertEqual('Civic',self.row('convoys','convoy_id','V1')['location'])
        self.assertEqual(0,self.w.stock('organization:west','food'))
        self.depart()
        self.arrive()
        self.depart()
        self.arrive()
        self.assertEqual(15,self.w.stock('organization:west','food'))
        self.assertEqual('ready',self.row('carriers','carrier_id','C1')['status'])
        self.assertEqual('delivered',self.row('convoys','convoy_id','V1')['status'])
        self.assertEqual(3,len(self.w.snapshot()['convoy_hops']))
        self.assertEqual('PASS',self.w.audit_state()['status'])

    def test_18_duplicate_convoy_dispatch_id_no_double_material(self):
        self.setup_convoy()
        result=self.trip()
        same=self.w.apply(result['event_id'],'ConvoyDispatched','c1',self.w.ledger()[-1]['payload'],tick=self.s.tick)
        self.assertTrue(same['duplicate'])
        self.assertEqual(110,self.w.stock('organization:union','food'))

    def test_19_wrong_convoy_route_rejected_without_debit(self):
        self.setup_convoy()
        start=self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError,'itinerary'):
            self.trip(['road:lower-east','road:lower-west'])
        self.assertEqual(start,self.w.state_hash())

    def test_20_convoy_cannot_arrive_early(self):
        self.setup_convoy()
        self.trip()
        with self.assertRaisesRegex(WorldRuleError,'not ready'):
            self.arrive(delta=0)
        self.assertEqual(0,len(self.w.snapshot()['convoy_hops']))

    def test_21_bridge_blocked_after_departure_then_reroute(self):
        self.setup_convoy()
        self.trip(['road:civic-camp','road:central'])
        self.arrive()
        self.depart()
        # c1 starts Camp; moves Civic then site bridge to obstruct the central span.
        self.s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-camp',**{'from':'Camp','to':'Civic'})
        self.s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-bridge',**{'from':'Civic','to':'bridge'})
        self.s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        with self.assertRaises(WorldRuleError):self.arrive()
        self.ev('ConvoyRerouted',convoy_id='V1',route_ids=['road:lower-east','road:lower-west'])
        self.depart()
        self.arrive()
        self.depart()
        self.arrive()
        self.assertEqual(15,self.w.stock('organization:west','food'))
        self.assertEqual(3,len(self.w.snapshot()['convoy_hops']))
        self.w.audit_state()

    def test_22_convoy_cannot_overfill_carrier(self):
        self.setup_convoy()
        with self.assertRaisesRegex(WorldRuleError,'capacity'):
            self.trip(qty=60)
        self.assertEqual(125,self.w.stock('organization:union','food'))

    def test_23_convoy_cannot_double_arrive(self):
        self.setup_convoy()
        self.trip()
        self.arrive()
        before=self.w.state_hash()
        with self.assertRaises(WorldRuleError):self.arrive()
        self.assertEqual(before,self.w.state_hash())

    def test_24_remaining_fuel_no_unbounded_trip(self):
        self.setup_convoy()
        self.w.db.execute('UPDATE carriers SET fuel=1 WHERE carrier_id=?',('C1',))
        with self.assertRaisesRegex(WorldRuleError,'fuel'):
            self.trip()
        self.assertEqual(125,self.w.stock('organization:union','food'))

    def test_25_convoy_commit_crash_does_not_remove_stock(self):
        self.setup_convoy()
        before=self.w.state_hash()
        p={'__v':3,'convoy_id':'V1','carrier_id':'C1','source_holder':'organization:union',
           'destination_holder':'organization:west','material':'food','quantity':15,
           'route_ids':['road:civic-camp','road:lower-east','road:lower-west']}
        with self.assertRaisesRegex(RuntimeError,'SIMULATED_CRASH'):
            self.w.apply('CRASH_V3','ConvoyDispatched','c1',p,tick=self.s.tick+1,crash_before_commit=True)
        self.assertEqual(before,self.w.state_hash())
        self.w.apply('CRASH_V3','ConvoyDispatched','c1',p,tick=self.s.tick+1)
        self.assertEqual(110,self.w.stock('organization:union','food'))

    def test_26_multi_hop_graph_blocks_disconnected_cycles(self):
        self.setup_convoy()
        for plan in (["road:civic-camp","road:civic-camp","road:central"],
                     ["road:civic-camp","road:civic-bridge"],
                     ["road:civic-camp","road:lower-east","road:civic-camp"]):
            with self.assertRaises(WorldRuleError):self.trip(plan)

    def test_27_convoy_replay_and_stored_state_audit(self):
        self.setup_convoy()
        self.trip()
        for idx in range(3):
            if idx:self.depart()
            self.arrive()
        self.w.audit_state()
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'trace.jsonl'
            self.w.export_jsonl(f)
            with World.replay_jsonl(f) as r:
                self.assertEqual(self.w.state_hash(),r.state_hash())

    def test_28_grant_replay_confidentiality(self):
        self.setup_evidence()
        self.ev('EvidenceAccessGranted',actor='a1',record_id='E1',grant_id='G1',grantee='c1',scope='read',expires_tick=self.s.tick+50)
        self.ev('EvidenceViewed',actor='c1',record_id='E1',read_id='R1')
        self.w.audit_state()

    def test_29_stable_task_ordering(self):
        self.setup_case()
        tasks=self.w.run_due(1000)
        self.assertEqual(['scheduled:deadline1'],[t['event_id'] for t in tasks])

    def test_30_forbid_arbitrary_system_job_event(self):
        self.setup_case()
        with self.assertRaisesRegex(WorldRuleError,'deadline'):
            self.ev('TaskPlanned',task_id='bad',case_id='case1',due_tick=self.s.tick+5)

    def test_31_event_version_has_integrity_bound_to_hash(self):
        self.setup_case()
        self.assertEqual(3,self.w.ledger()[-1]['payload']['__v'])
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'trace.jsonl';self.w.export_jsonl(f)
            lines=f.read_text().splitlines();last=json.loads(lines[-1]);last['payload']['__v']=4
            lines[-1]=json.dumps(last)
            f.write_text('\n'.join(lines)+'\n')
            with self.assertRaises(WorldRuleError):
                with World.replay_jsonl(f): pass

    def test_32_clinical_access_blocked_after_subject_death(self):
        self.setup_evidence()
        self.s.emit('CharacterDied',character_id='a1',reason='test-only death')
        with self.assertRaises(WorldRuleError):
            self.ev('EvidenceAccessGranted',actor='a1',record_id='E1',grant_id='Gdead',
                    grantee='c1',scope='read',expires_tick=self.s.tick+20)

    def test_33_real_hub_receives_multi_stop_cargo_once(self):
        self.setup_convoy()
        self.s.emit('RegionHubRegistered',region_id='Southplain',location='Civic')
        self.s.emit('RouteRegistered',route_id='road:camp-lab',point_a='Camp',point_b='Lab',km=2.2)
        food=self.row('regions','region_id','Southplain')['food']
        self.ev('ConvoyDispatched',actor='c1',convoy_id='V1',carrier_id='C1',
                source_holder='organization:union',destination_holder='region:Southplain',
                material='food',quantity=7,route_ids=['road:camp-lab','road:civic-lab'])
        self.arrive(delta=12)
        self.depart()
        self.arrive(delta=12)
        self.assertEqual(food+7,self.row('regions','region_id','Southplain')['food'])
        self.assertEqual('delivered',self.row('convoys','convoy_id','V1')['status'])

    def test_34_no_instant_transfer_between_registered_depots(self):
        self.setup_convoy()
        with self.assertRaisesRegex(WorldRuleError,'physical shipment'):
            self.s.emit('StockTransferred',actor='c1',from_holder='organization:union',
                       to_holder='organization:west',material='food',quantity=10)

    def test_35_reopen_mid_convoy_and_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'convoy.sqlite3'
            with World(f) as w:
                s=seed_world(w)
                for kind,p in [('OrganizationRegistered',{'org_id':'west','name':'Westbank'}),
                               ('DepotRegistered',{'holder':'organization:union','location':'Camp'}),
                               ('DepotRegistered',{'holder':'organization:west','location':'Westbank'}),
                               ('CarrierRegistered',{'carrier_id':'C1','owner_org':'union','location':'Camp','capacity':20,'fuel':140}),
                               ('StockProvisioned',{'holder':'organization:union','material':'food','quantity':50})]:
                    s.emit(kind,**p)
                s.emit('ConvoyDispatched',actor='c1',__v=3,convoy_id='V1',carrier_id='C1',
                       source_holder='organization:union',destination_holder='organization:west',material='food',
                       quantity=6,route_ids=['road:civic-camp','road:lower-east','road:lower-west'])
                s.tick+=10;s.emit('ConvoyLegArrived',__v=3,convoy_id='V1')
                resume_tick=s.tick
            with World(f) as w:
                for i in range(2):
                    w.apply(f'restart-depart-{i}','ConvoyLegDeparted','system',
                            {'__v':3,'convoy_id':'V1'},tick=resume_tick+1+i*15)
                    w.apply(f'restart-arrive-{i}','ConvoyLegArrived','system',
                            {'__v':3,'convoy_id':'V1'},tick=resume_tick+14+i*15)
                self.assertEqual(6,w.stock('organization:west','food'))
                self.assertEqual('PASS',w.audit_state()['status'])

    def test_36_incorrect_schema_revision_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'bad_revision.sqlite3'
            with World(f) as w:
                w.db.execute('UPDATE worldstate_schema SET revision=4 WHERE id=1')
            with self.assertRaises(ValueError):
                with World(f):pass

    def test_37_failed_arrival_during_bridge_obstruction_keeps_cargo(self):
        self.setup_convoy()
        self.trip(['road:civic-camp','road:central'])
        self.arrive()
        self.depart()
        self.s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-camp',
                    **{'from':'Camp','to':'Civic'})
        self.s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-bridge',
                    **{'from':'Civic','to':'bridge'})
        self.s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        before=self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError,'obstructed'):
            self.arrive(delta=12)
        self.assertEqual(before,self.w.state_hash())
        self.assertEqual(0,self.w.stock('organization:west','food'))
        self.assertEqual('transit',self.row('convoys','convoy_id','V1')['status'])

    def test_38_fuel_consumption_measured_on_each_leg(self):
        self.setup_convoy()
        initial=self.row('carriers','carrier_id','C1')['fuel']
        self.trip()
        self.assertLess(self.row('carriers','carrier_id','C1')['fuel'],initial)
        self.arrive()
        after_first=self.row('carriers','carrier_id','C1')['fuel']
        self.assertEqual(initial-max(1,1*10),after_first)
        self.depart()
        self.assertLess(self.row('carriers','carrier_id','C1')['fuel'],after_first)

    def test_39_unknown_v03_event_tag_never_bypasses_legacy_dispatch(self):
        with self.assertRaises(WorldRuleError):
            self.ev('InventedMiracleEvent',invented=True)

    def test_40_unsanctioned_evidence_reader_cannot_grant_to_self(self):
        self.setup_evidence()
        self.ev('EvidenceAccessGranted',actor='a1',record_id='E1',grant_id='G1',
                grantee='c1',scope='read',expires_tick=self.s.tick+15)
        with self.assertRaisesRegex(WorldRuleError,'consent required'):
            self.ev('EvidenceAccessGranted',actor='c1',record_id='E1',grant_id='G2',
                    grantee='d1',scope='read',expires_tick=self.s.tick+15)


if __name__=='__main__':unittest.main()
