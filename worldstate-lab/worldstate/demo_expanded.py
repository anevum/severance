"""V0.2 integrated offline story: one patient, civic supplies and bridge diversion."""
from __future__ import annotations

import json
from pathlib import Path
from .engine import World
from .scenarios import seed_world


def run_expanded_demo(folder: str | Path) -> dict:
    out=Path(folder)
    out.mkdir(parents=True,exist_ok=True)
    db_path=out/'expanded_world.sqlite3'
    for f in (db_path,Path(str(db_path)+'-wal'),Path(str(db_path)+'-shm')):
        if f.exists():f.unlink()
    with World(db_path) as world:
        s=seed_world(world)
        # A medic gets to a real forest location and stabilizes a mortal resident.
        s.emit('StockProvisioned',holder='character:b1',material='transport_kit',quantity=3)
        s.emit('CharacterMoved',actor='b1',character_id='b1',route_id='road:civic-camp',**{'from':'Civic','to':'Camp'})
        s.emit('CharacterMoved',actor='b1',character_id='b1',route_id='road:camp-forest',**{'from':'Camp','to':'Forest'})
        s.emit('CharacterInjured',character_id='d1',severity=92)
        s.emit('MedicalCaseOpened',case_id='M1',character_id='d1',hospital_site='hospital',deadline_tick=s.tick+40)
        s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        for i,(route,to) in enumerate([('road:camp-forest','Camp'),('road:civic-camp','Civic'),('road:civic-hospital','hospital')],1):
            t=f'MT{i}'
            s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id=t,route_id=route,to=to)
            s.tick+=12
            s.emit('MedicalTransportCompleted',transport_id=t)
        s.tick+=15
        s.emit('MedicalCaseRecovered',case_id='M1')
        # A real cargo movement replenishes an aggregate regional ledger.
        s.emit('DepotRegistered',holder='organization:union',location='Camp')
        s.emit('DepotRegistered',holder='organization:city',location='Civic')
        s.emit('RegionHubRegistered',region_id='Southplain',location='Civic')
        s.emit('CarrierRegistered',carrier_id='union1',owner_org='union',location='Camp',capacity=25,fuel=100)
        s.emit('StockProvisioned',holder='organization:union',material='food',quantity=75)
        start_food=world._one('regions','region_id','Southplain')['food']
        s.emit('ShipmentDispatched',actor='c1',shipment_id='AID1',source_holder='organization:union',destination_holder='region:Southplain',material='food',quantity=20,carrier_id='union1',route_id='road:civic-camp')
        s.tick+=10
        s.emit('ShipmentDelivered',shipment_id='AID1')
        # Now a different community uses a restricted road and must divert.
        s.emit('OrganizationRegistered',org_id='west',name='Westbank Freight Guild')
        s.emit('MembershipGranted',org_id='west',character_id='a1',role='quartermaster')
        s.emit('DepotRegistered',holder='organization:west',location='Westbank')
        s.emit('CarrierRegistered',carrier_id='west1',owner_org='west',location='Westbank',capacity=15,fuel=135)
        s.emit('StockProvisioned',holder='organization:west',material='water',quantity=40)
        s.emit('ShipmentDispatched',actor='a1',shipment_id='H2O1',source_holder='organization:west',destination_holder='organization:city',material='water',quantity=10,carrier_id='west1',route_id='road:central')
        s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-camp',**{'from':'Camp','to':'Civic'})
        s.emit('CharacterMoved',actor='c1',character_id='c1',route_id='road:civic-bridge',**{'from':'Civic','to':'bridge'})
        s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        blocked_distance=world.shortest_route('Westbank','Civic')['km']
        s.emit('ShipmentRerouted',shipment_id='H2O1',route_ids=['road:lower-west','road:lower-east'])
        s.tick+=25
        s.emit('ShipmentDelivered',shipment_id='H2O1')
        report={
            'status':'PASS', 'description':'Offline V0.2 narrative rules demonstration, not the playable game',
            'medical_case':dict(world.db.execute("SELECT * FROM medical_cases WHERE case_id='M1'").fetchone()),
            'rescued_survivor':dict(world._one('characters','character_id','d1')),
            'regional_food_before':start_food,'regional_food_after':world._one('regions','region_id','Southplain')['food'],
            'bridge_route_open_km':2.017,'bridge_route_blocked_km':blocked_distance,
            'alternate_freight_distance_km':dict(world.db.execute("SELECT * FROM shipment_reroutes WHERE shipment_id='H2O1'").fetchone())['distance_km'],
            'city_water_delivered':world.stock('organization:city','water'),
            'survivor_account_recreated':False,
            'events':len(world.ledger()),
            'state_sha256':world.state_hash(),
            'ledger_audit':world.audit_state(),
        }
        world.export_jsonl(out/'expanded_events.jsonl')
        (out/'expanded_snapshot.json').write_text(json.dumps(world.snapshot(),indent=2,sort_keys=True)+'\n',encoding='utf-8')
    with World.replay_jsonl(out/'expanded_events.jsonl') as replay:
        report['replay_state_sha256']=replay.state_hash()
        assert report['state_sha256']==report['replay_state_sha256']
    (out/'expanded_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return report
