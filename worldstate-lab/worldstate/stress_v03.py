"""Repeatable offline multi-stop cargo stress with replay and actual SQLite restarts.

Event counts do not measure concurrent users, network load or gameplay capacity.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from .engine import World,WorldRuleError
from .scenarios import seed_world


def run_v03_stress(out_dir: str | Path, *, rounds: int=100, seed: int=20261029) -> dict:
    if not isinstance(rounds,int) or not 1<=rounds<=1000:
        raise ValueError('rounds 1..1000')
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    db_path=out/'stress_v03.sqlite3'
    if db_path.exists():db_path.unlink()
    rng=random.Random(seed)
    count=0
    tick=0
    errors_expected=0
    restarts=0

    def emit(w,kind,actor='system',**p):
        nonlocal count,tick
        tick+=1;count+=1
        return w.apply(f'ST3-{count:08d}',kind,actor,p,tick=tick)

    w=World(db_path)
    try:
        # Original fixture with its own event ID prefix and tick positions.
        s=seed_world(w)
        tick=s.tick
        emit(w,'OrganizationRegistered',org_id='west',name='Westbank Transfer Depot')
        emit(w,'DepotRegistered',holder='organization:union',location='Camp')
        emit(w,'DepotRegistered',holder='organization:west',location='Westbank')
        emit(w,'StockProvisioned',holder='organization:union',material='food',quantity=rounds*12+100)
        starting=w.stock('organization:union','food')
        total=0
        for i in range(rounds):
            qty=rng.randint(2,10)
            total+=qty
            carrier=f'carrier-{i:04d}'
            convoy=f'convoy-{i:04d}'
            emit(w,'CarrierRegistered',carrier_id=carrier,owner_org='union',location='Camp',capacity=20,fuel=120)
            p={'__v':3,'convoy_id':convoy,'carrier_id':carrier,'source_holder':'organization:union',
               'destination_holder':'organization:west','material':'food','quantity':qty,
               'route_ids':['road:civic-camp','road:lower-east','road:lower-west']}
            emit(w,'ConvoyDispatched',actor='c1',**p)
            if i%7==0:
                # Too-early arrival is rejected with no state mutation.
                before=w.state_hash()
                try:
                    emit(w,'ConvoyLegArrived',__v=3,convoy_id=convoy)
                except WorldRuleError:
                    errors_expected+=1
                else:
                    raise AssertionError('early arrival improperly accepted')
                assert before==w.state_hash()
            for leg in range(3):
                if leg:
                    emit(w,'ConvoyLegDeparted',__v=3,convoy_id=convoy)
                tick+=12
                emit(w,'ConvoyLegArrived',__v=3,convoy_id=convoy)
            stock_total=w.stock('organization:union','food')+w.stock('organization:west','food')
            if stock_total!=starting:
                raise AssertionError('materials lost or duplicated during convoy')
            if (i+1)%20==0:
                w.audit_state()
                w.close();w=World(db_path);restarts+=1
                tail=w.db.execute('SELECT MAX(tick) FROM ledger').fetchone()[0]
                assert tail==tick
        audit=w.audit_state()
        report={'status':'PASS','type':'offline synthetic event/DB stress; no network clients',
                'seed':seed,'rounds':rounds,'events':len(w.ledger()),'committed_convoys':rounds,
                'sqlite_restarts':restarts,'rejected_early_arrivals':errors_expected,
                'first_depot_remaining':w.stock('organization:union','food'),
                'west_depot_delivered':w.stock('organization:west','food'),
                'resource_conservation':w.stock('organization:union','food')+w.stock('organization:west','food')==starting,
                'state_sha256':w.state_hash(),'ledger_tail_hash':audit['ledger_last_hash']}
        w.export_jsonl(out/'stress_events_v03.jsonl')
    finally:
        w.close()
    with World.replay_jsonl(out/'stress_events_v03.jsonl') as replay:
        report['replay_sha256']=replay.state_hash()
        assert report['replay_sha256']==report['state_sha256']
    (out/'stress_report_v03.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
