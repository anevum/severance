"""Integrated story for the isolated V0.3 rules. Everything is fictional and synthetic."""
from __future__ import annotations

import json
from pathlib import Path

from .engine import World
from .scenarios import seed_world


def run_v03_demo(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'world_v03.sqlite3'
    if path.exists():
        path.unlink()
    with World(path) as w:
        s = seed_world(w)

        def event(kind: str, *, actor: str='system', **payload):
            return s.emit(kind, actor=actor, **{'__v':3,**payload})

        # Clinical record belongs to a physical patient, not a globally readable archive.
        s.emit('EvidenceRecorded',actor='b1',record_id='clinic-1',
               summary='Synthetic masked clinical record',source='Regional Hospital',classification='clinical')
        event('EvidenceSubjectBound',record_id='clinic-1',subject_id='a1')
        event('EvidenceAccessGranted',actor='a1',record_id='clinic-1',
              grant_id='consent-1',grantee='c1',scope='read',expires_tick=s.tick+50)
        event('EvidenceViewed',actor='c1',record_id='clinic-1',read_id='audit-view-1')
        event('EvidenceAccessRevoked',actor='a1',grant_id='consent-1')
        assert not w.evidence_visible_to('clinic-1','c1')

        # Timed medical rescue: original person survives with no new body or gene-memory.
        s.emit('StockProvisioned',holder='character:b1',material='transport_kit',quantity=3)
        s.emit('CharacterMoved',actor='b1',character_id='b1',route_id='road:civic-camp',**{'from':'Civic','to':'Camp'})
        s.emit('CharacterMoved',actor='b1',character_id='b1',route_id='road:camp-forest',**{'from':'Camp','to':'Forest'})
        s.emit('CharacterInjured',character_id='d1',severity=92)
        s.emit('MedicalCaseOpened',case_id='injury-1',character_id='d1',hospital_site='hospital',deadline_tick=s.tick+60)
        case=w.db.execute("SELECT deadline_tick FROM medical_cases WHERE case_id='injury-1'").fetchone()
        event('TaskPlanned',task_id='deadline-1',case_id='injury-1',due_tick=case['deadline_tick']+1)
        s.emit('MedicalCaseStabilized',actor='b1',case_id='injury-1')
        for i,(road,stop) in enumerate((('road:camp-forest','Camp'),('road:civic-camp','Civic'),('road:civic-hospital','hospital')),1):
            s.emit('MedicalTransportStarted',actor='b1',case_id='injury-1',transport_id=f'med-leg-{i}',route_id=road,to=stop)
            s.tick+=12
            s.emit('MedicalTransportCompleted',transport_id=f'med-leg-{i}')
        s.tick+=12
        s.emit('MedicalCaseRecovered',case_id='injury-1')
        s.tick=max(s.tick,case['deadline_tick']+2)
        scheduled=w.run_due(s.tick)
        assert len(scheduled)==1
        assert w.db.execute("SELECT state FROM scheduled_tasks WHERE task_id='deadline-1'").fetchone()['state']=='skipped'

        # Multi-stop food route through actual valley graph, then local bridge trouble.
        s.emit('OrganizationRegistered',org_id='west',name='Westbank Food Repair Cooperative')
        s.emit('DepotRegistered',holder='organization:union',location='Camp')
        s.emit('DepotRegistered',holder='organization:west',location='Westbank')
        s.emit('CarrierRegistered',carrier_id='convoy-car',owner_org='union',location='Camp',capacity=30,fuel=250)
        s.emit('StockProvisioned',holder='organization:union',material='food',quantity=80)
        event('ConvoyDispatched',actor='c1',convoy_id='food-1',carrier_id='convoy-car',
              source_holder='organization:union',destination_holder='organization:west',
              material='food',quantity=20,route_ids=['road:civic-camp','road:central'])
        s.tick+=10
        event('ConvoyLegArrived',convoy_id='food-1')
        event('ConvoyLegDeparted',convoy_id='food-1')
        s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-camp',**{'from':'Camp','to':'Civic'})
        s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-bridge',**{'from':'Civic','to':'bridge'})
        s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        diverted_km=w.shortest_route('Westbank','Civic')['km']
        event('ConvoyRerouted',convoy_id='food-1',route_ids=['road:lower-east','road:lower-west'])
        for stop in range(2):
            event('ConvoyLegDeparted',convoy_id='food-1')
            s.tick+=13
            event('ConvoyLegArrived',convoy_id='food-1')
        assert w.stock('organization:west','food')==20
        assert w.stock('organization:union','food')==60
        # The two orbital interworld links close; local medicine remains operational.
        s.emit('RoadClosed',link_id='Cydren Skygate')
        s.emit('RoadClosed',link_id='Orveth Freight Ring')
        report={
            'status':'PASS', 'type':'offline rules demo; NOT connected players or clinical software',
            'events':len(w.ledger()),
            'restored_original_character':w._one('characters','character_id','d1')['state']=='active',
            'automatic_deadline_outcome':'skipped',
            'scope_revocation_enforced':not w.evidence_visible_to('clinic-1','c1'),
            'region_cargo_delivered':w.stock('organization:west','food'),
            'three_completed_convoy_hops':len(w.snapshot()['convoy_hops'])==3,
            'bridge_alternative_km':diverted_km,
            'both_offworld_roads_closed':all(x['status']=='closed' for x in w.snapshot()['interworld_links']),
            'hospital_operational':w._one('sites','site_id','hospital')['status']=='operational',
            'state_sha256':w.state_hash(),
            'ledger_tail_hash':w.verify_chain()['last_hash'],
        }
        (out/'snapshot_v03.json').write_text(json.dumps(w.snapshot(),indent=2,sort_keys=True)+'\n')
        w.export_jsonl(out/'events_v03.jsonl')
    with World.replay_jsonl(out/'events_v03.jsonl') as replay:
        report['replay_sha256']=replay.state_hash()
        assert report['state_sha256']==report['replay_sha256']
    (out/'report_v03.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
