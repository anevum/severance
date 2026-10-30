"""Reproducible offline state-machine stress run, NOT network or rendering load."""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from .engine import World, WorldRuleError
from .scenarios import seed_world


def _total_material(w: World, material: str) -> int:
    holdings = sum(int(row['quantity']) for row in w.db.execute('SELECT quantity FROM stocks WHERE material=?', (material,)))
    in_transit = sum(int(row['quantity']) for row in w.db.execute('SELECT quantity FROM shipments WHERE material=? AND status=\'transit\'', (material,)))
    regional = sum(int(row[material]) for row in w.db.execute('SELECT food,water FROM regions'))
    return holdings + in_transit + regional


def run_stress(folder: str | Path, *, seed: int = 8619, rounds: int = 250, restart_every: int = 37) -> dict:
    """Execute bounded randomized cargo + regional supply, restarting SQLite periodically.

    Invariants checked each trip: conservation across depot, transit and region,
    delayed arrival, duplicate handling, carrier location, and deterministic replay.
    This does not test actual server clients or multi-process world authority.
    """
    if type(seed) is not int or type(rounds) is not int or not (1 <= rounds <= 1200):
        raise ValueError('seed must be integer; rounds must be 1..1200')
    if type(restart_every) is not int or restart_every < 1:
        raise ValueError('restart_every must be positive integer')
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    db_path = target / 'stress.sqlite3'
    for f in (db_path, Path(str(db_path)+'-wal'), Path(str(db_path)+'-shm')):
        if f.exists(): f.unlink()
    rng = random.Random(seed)
    world = World(db_path)
    restarts = 0
    supply = {'food': 0, 'water': 0}
    shipment_count = 0
    invalid_rejections = 0
    try:
        s = seed_world(world)
        s.emit('DepotRegistered', holder='organization:union', location='Camp')
        s.emit('DepotRegistered', holder='organization:city', location='Civic')
        s.emit('RegionHubRegistered', region_id='Southplain', location='Civic')
        s.emit('CarrierRegistered', carrier_id='freight1', owner_org='union', location='Camp', capacity=15, fuel=50)
        for material, qty in [('food',5000),('water',5000),('fuel_cell',rounds*3)]:
            s.emit('StockProvisioned', holder='organization:union', material=material, quantity=qty)
        for i in range(rounds):
            carrier = world.db.execute("SELECT * FROM carriers WHERE carrier_id='freight1'").fetchone()
            if carrier['fuel'] < 20:
                s.emit('CarrierRefueled', actor='c1', carrier_id='freight1', quantity=2)
            material = rng.choice(['food','water'])
            qty = rng.randint(1,12)
            dest = rng.choice(['organization:city','region:Southplain'])
            baseline = _total_material(world, material)
            sid = f'S{seed}-{i:04d}'
            details = {'shipment_id':sid,'source_holder':'organization:union','destination_holder':dest,
                       'material':material,'quantity':qty,'carrier_id':'freight1','route_id':'road:civic-camp'}
            dispatched=s.emit('ShipmentDispatched', actor='c1', **details)
            assert _total_material(world, material) == baseline, 'dispatched material not conserved'
            if i%19==0:
                # Same identity and exact payload must remain a no-op.
                before=world.state_hash()
                duplicate=world.apply(dispatched['event_id'],'ShipmentDispatched','c1',details,tick=s.tick)
                assert duplicate['duplicate'] and before == world.state_hash(), 'duplicate applied twice'
            if i%17==0:
                # Invalid action under a separate event ID must not change state.
                before=world.state_hash()
                try:
                    s.emit('ShipmentDelivered', shipment_id=sid)
                except WorldRuleError:
                    invalid_rejections += 1
                else:
                    raise AssertionError('premature delivery accepted')
                assert before==world.state_hash(), 'failed event changed state'
            s.tick += 6
            s.emit('ShipmentDelivered', shipment_id=sid)
            shipment_count += 1
            assert _total_material(world, material) == baseline, 'delivered material not conserved'
            if dest.startswith('region:'): supply[material]+=qty
            move=f'R{seed}-{i:04d}'
            s.emit('CarrierReturnStarted',move_id=move,carrier_id='freight1',route_id='road:civic-camp')
            s.tick += 6
            s.emit('CarrierReturnCompleted',move_id=move)
            back=world.db.execute("SELECT * FROM carriers WHERE carrier_id='freight1'").fetchone()
            assert back['status']=='ready' and back['location']=='Camp', 'carrier return inconsistent'
            if i%11==0:
                s.emit('RegionAdvanced', region_id='Southplain', steps=1)
            if i%23==0:
                new_food=rng.randint(8,15)
                new_water=rng.randint(9,16)
                s.emit('RegionProductionChanged',region_id='Southplain',food_production=new_food,water_production=new_water)
            if i and i%restart_every==0:
                world.close()
                world=World(db_path)
                s.world=world
                restarts += 1
        final_hash=world.state_hash()
        audit=world.audit_state()
        path=target/'stress_events.jsonl'
        world.export_jsonl(path)
        report={'status':'PASS','seed':seed,'rounds':rounds,'shipments_delivered':shipment_count,
                'regional_relief_delivered':supply,'forced_invalid_operations_rejected':invalid_rejections,
                'sqlite_restarts':restarts,'events':len(world.ledger()),'state_sha256':final_hash,
                'ledger_last_hash':audit['ledger_last_hash'],'total_food_now':_total_material(world,'food'),
                'total_water_now':_total_material(world,'water')}
    finally:
        world.close()
    with World.replay_jsonl(path) as reconstructed:
        report['replay_state_sha256']=reconstructed.state_hash()
        if report['replay_state_sha256'] != report['state_sha256']:
            raise AssertionError('stress replay mismatch')
        report['replay_audit']=reconstructed.audit_state()['status']
    (target/'stress_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return report
