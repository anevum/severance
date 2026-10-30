"""Offline V0.2 extension: bounded rescue, physical cargo, and regional supply.

Not a real medical model, transport simulation, API permission layer, or server.
Every transition runs inside World.apply()'s existing SQLite transaction.
"""
from __future__ import annotations

import math
from typing import Any

EXPANSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS medical_cases (
 case_id TEXT PRIMARY KEY,
 character_id TEXT NOT NULL REFERENCES characters(character_id),
 state TEXT NOT NULL CHECK(state IN ('open','stabilized','transit','admitted','recovered','expired','deceased')),
 opened_tick INTEGER NOT NULL, deadline_tick INTEGER NOT NULL,
 stabilized_tick INTEGER, admitted_tick INTEGER, completed_tick INTEGER,
 hospital_site TEXT NOT NULL REFERENCES sites(site_id)
);
CREATE TABLE IF NOT EXISTS medical_transports (
 transport_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES medical_cases(case_id),
 responder TEXT NOT NULL REFERENCES characters(character_id),
 route_id TEXT NOT NULL REFERENCES routes(route_id),
 origin TEXT NOT NULL, destination TEXT NOT NULL,
 departed_tick INTEGER NOT NULL, earliest_arrival_tick INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('traveling','arrived','aborted'))
);
CREATE UNIQUE INDEX IF NOT EXISTS medical_one_active ON medical_cases(character_id)
WHERE state IN ('open','stabilized','transit','admitted');
CREATE TABLE IF NOT EXISTS depots (
 holder TEXT PRIMARY KEY,
 location TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS region_hubs (
 region_id TEXT PRIMARY KEY REFERENCES regions(region_id),
 location TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carriers (
 carrier_id TEXT PRIMARY KEY,
 owner_org TEXT NOT NULL REFERENCES organizations(org_id),
 location TEXT NOT NULL,
 capacity INTEGER NOT NULL CHECK(capacity > 0),
 fuel INTEGER NOT NULL CHECK(fuel >= 0),
 status TEXT NOT NULL CHECK(status IN ('ready','transit'))
);
CREATE TABLE IF NOT EXISTS shipment_reroutes (
 shipment_id TEXT PRIMARY KEY REFERENCES shipments(shipment_id),
 route_ids TEXT NOT NULL, distance_km REAL NOT NULL CHECK(distance_km>0),
 earliest_arrival_tick INTEGER NOT NULL, extra_fuel INTEGER NOT NULL CHECK(extra_fuel>=0)
);
CREATE TABLE IF NOT EXISTS carrier_moves (
 move_id TEXT PRIMARY KEY, carrier_id TEXT NOT NULL REFERENCES carriers(carrier_id),
 route_id TEXT NOT NULL REFERENCES routes(route_id),
 origin TEXT NOT NULL, destination TEXT NOT NULL, departed_tick INTEGER NOT NULL,
 earliest_arrival_tick INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('transit','completed'))
);
CREATE TABLE IF NOT EXISTS shipments (
 shipment_id TEXT PRIMARY KEY,
 source_holder TEXT NOT NULL,
 destination_holder TEXT NOT NULL,
 material TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity > 0),
 carrier_id TEXT NOT NULL REFERENCES carriers(carrier_id),
 route_id TEXT NOT NULL REFERENCES routes(route_id),
 origin TEXT NOT NULL, destination TEXT NOT NULL,
 departed_tick INTEGER NOT NULL, earliest_arrival_tick INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('transit','delivered'))
);
"""

EXTRA_TABLES = (
    'medical_cases', 'medical_transports', 'depots', 'region_hubs', 'carriers', 'carrier_moves', 'shipments', 'shipment_reroutes'
)


def _posint(world: Any, value: Any, reason: str, *, upper: int = 1000000) -> int:
    world._require(type(value) is int and 0 < value <= upper, reason)
    return value


def _nonnegative_int(world: Any, value: Any, reason: str, *, upper: int = 1000000) -> int:
    world._require(type(value) is int and 0 <= value <= upper, reason)
    return value


def _open_route(world: Any, route_id: str, origin: str, destination: str) -> Any:
    row = world.db.execute('SELECT * FROM routes WHERE route_id=?', (route_id,)).fetchone()
    world._require(row is not None, 'unknown transit route')
    world._require(origin != destination and {origin, destination} == {row['point_a'], row['point_b']},
                   'transit route does not connect endpoints')
    if row['guarded_by_site']:
        gate = world._one('sites', 'site_id', row['guarded_by_site'])
        world._require(gate['status'] == 'operational', 'transit route obstructed')
    return row


def _case(world: Any, cid: str) -> Any:
    row = world.db.execute('SELECT * FROM medical_cases WHERE case_id=?', (cid,)).fetchone()
    world._require(row is not None, 'unknown medical case')
    return row


def _shipment(world: Any, sid: str) -> Any:
    row = world.db.execute('SELECT * FROM shipments WHERE shipment_id=?', (sid,)).fetchone()
    world._require(row is not None, 'unknown shipment')
    return row


def _end_life(world: Any, character: str, loc: str) -> None:
    # Same irreversible consequence as the existing CharacterDied event.
    world.db.execute("UPDATE characters SET state='deceased',health=0,connected=0,version=version+1 WHERE character_id=?", (character,))
    world.db.execute('UPDATE items SET custodian=?,location=? WHERE custodian=?',
                     (f'estate:{character}', loc, f'character:{character}'))


def dispatch_expanded(world: Any, kind: str, actor: str, p: dict, tick: int) -> bool:
    """Return True when the V0.2 event was handled; raise for rule failures."""
    db = world.db
    if kind == 'MedicalCaseOpened':
        world._system(actor)
        ch = world._one('characters', 'character_id', p['character_id'])
        world._require(ch['state'] == 'incapacitated', 'patient must be incapacitated')
        world._require(db.execute("SELECT 1 FROM medical_cases WHERE character_id=? AND state IN ('open','stabilized','transit','admitted')", (p['character_id'],)).fetchone() is None, 'open medical case already exists')
        hospital = world._one('sites', 'site_id', p['hospital_site'])
        world._require(hospital['kind'] == 'medical' and hospital['status'] == 'operational', 'hospital unavailable')
        deadline = _posint(world, p['deadline_tick'], 'invalid rescue deadline')
        world._require(tick < deadline <= tick + 120, 'rescue deadline out of bounds')
        db.execute('INSERT INTO medical_cases(case_id,character_id,state,opened_tick,deadline_tick,hospital_site) '
                   'VALUES(?,?,?,?,?,?)', (p['case_id'], p['character_id'], 'open', tick, deadline, p['hospital_site']))
        return True
    if kind == 'MedicalCaseStabilized':
        responder = world._active(actor)
        case = _case(world, p['case_id'])
        patient = world._one('characters', 'character_id', case['character_id'])
        world._require(case['state'] == 'open' and patient['state'] == 'incapacitated', 'patient cannot be stabilized')
        world._require(tick <= case['deadline_tick'], 'medical rescue window expired')
        world._require(responder['location'] == patient['location'], 'responder not colocated')
        kit_holder = f'character:{actor}'
        world._require(world._stock(kit_holder, 'field_kit') >= 1, 'missing field kit')
        world._set_stock(kit_holder, 'field_kit', world._stock(kit_holder, 'field_kit') - 1)
        db.execute("UPDATE characters SET state='stabilized',health=25,version=version+1 WHERE character_id=?",
                   (patient['character_id'],))
        db.execute("UPDATE medical_cases SET state='stabilized',stabilized_tick=? WHERE case_id=?", (tick, p['case_id']))
        return True
    if kind == 'MedicalCaseExpired':
        world._system(actor)
        case = _case(world, p['case_id'])
        patient = world._one('characters', 'character_id', case['character_id'])
        world._require(case['state'] == 'open' and patient['state'] == 'incapacitated', 'case is not open')
        world._require(tick > case['deadline_tick'], 'rescue window not yet expired')
        _end_life(world, case['character_id'], patient['location'])
        db.execute("UPDATE medical_cases SET state='expired',completed_tick=? WHERE case_id=?", (tick, p['case_id']))
        return True
    if kind == 'MedicalTransportStarted':
        medic = world._active(actor)
        case = _case(world, p['case_id'])
        patient = world._one('characters', 'character_id', case['character_id'])
        world._require(case['state'] == 'stabilized' and patient['state'] == 'stabilized', 'not ready for transport')
        world._require(medic['location'] == patient['location'], 'responder not colocated')
        route = _open_route(world, p['route_id'], medic['location'], p['to'])
        world._require(medic['location'] != case['hospital_site'], 'patient already at hospital')
        holder = f'character:{actor}'
        world._require(world._stock(holder, 'transport_kit') >= 1, 'missing transport equipment')
        world._set_stock(holder, 'transport_kit', world._stock(holder, 'transport_kit') - 1)
        arrival = tick + max(1, math.ceil(route['km'] * 3))
        db.execute('INSERT INTO medical_transports VALUES(?,?,?,?,?,?,?,?,?)',
                   (p['transport_id'], p['case_id'], actor, p['route_id'], medic['location'], p['to'], tick, arrival, 'traveling'))
        db.execute("UPDATE medical_cases SET state='transit' WHERE case_id=?", (p['case_id'],))
        return True
    if kind == 'MedicalTransportCompleted':
        world._system(actor)
        journey = db.execute('SELECT * FROM medical_transports WHERE transport_id=?', (p['transport_id'],)).fetchone()
        world._require(journey is not None and journey['status'] == 'traveling', 'transport not in progress')
        case = _case(world, journey['case_id'])
        patient = world._one('characters', 'character_id', case['character_id'])
        medic = world._one('characters', 'character_id', journey['responder'])
        world._require(tick >= journey['earliest_arrival_tick'], 'transport still in transit')
        world._require(medic['state'] != 'deceased', 'responder deceased')
        world._require(case['state'] == 'transit' and patient['state'] == 'stabilized', 'patient not in medical transit')
        world._require(patient['location'] == journey['origin'] and medic['location'] == journey['origin'], 'patient or medic moved unexpectedly')
        _open_route(world, journey['route_id'], journey['origin'], journey['destination'])
        at_hospital = journey['destination'] == case['hospital_site']
        if at_hospital:
            hospital = world._one('sites', 'site_id', case['hospital_site'])
            world._require(hospital['status'] == 'operational', 'hospital no longer operational')
        for char_id in (case['character_id'], journey['responder']):
            db.execute('UPDATE characters SET location=?,version=version+1 WHERE character_id=?', (journey['destination'], char_id))
            db.execute('UPDATE items SET location=? WHERE custodian=?', (journey['destination'], f'character:{char_id}'))
        db.execute("UPDATE medical_transports SET status='arrived' WHERE transport_id=?", (p['transport_id'],))
        if at_hospital:
            db.execute("UPDATE medical_cases SET state='admitted',admitted_tick=? WHERE case_id=?", (tick, case['case_id']))
        else:
            db.execute("UPDATE medical_cases SET state='stabilized' WHERE case_id=?", (case['case_id'],))
        return True
    if kind == 'MedicalCaseRecovered':
        world._system(actor)
        case = _case(world, p['case_id'])
        patient = world._one('characters', 'character_id', case['character_id'])
        world._require(case['state'] == 'admitted' and patient['state'] == 'stabilized', 'patient not admitted')
        world._require(tick >= case['admitted_tick'] + 10, 'rehabilitation time not complete')
        hospital = world._one('sites', 'site_id', case['hospital_site'])
        world._require(patient['location'] == case['hospital_site'] and hospital['status'] == 'operational', 'patient not at an operating hospital')
        db.execute("UPDATE characters SET state='active',health=85,version=version+1 WHERE character_id=?", (case['character_id'],))
        db.execute("UPDATE medical_cases SET state='recovered',completed_tick=? WHERE case_id=?", (tick, case['case_id']))
        return True
    if kind == 'DepotRegistered':
        world._system(actor)
        world._check_holder(p['holder'])
        world._require(p['holder'].startswith('organization:'), 'depots must belong to organizations')
        world._require(isinstance(p['location'], str) and p['location'], 'invalid depot location')
        db.execute('INSERT INTO depots VALUES(?,?)', (p['holder'], p['location']))
        return True
    if kind == 'RegionHubRegistered':
        world._system(actor)
        world._one('regions', 'region_id', p['region_id'])
        world._require(isinstance(p['location'], str) and p['location'], 'invalid region hub')
        db.execute('INSERT INTO region_hubs VALUES(?,?)', (p['region_id'], p['location']))
        return True
    if kind == 'CarrierRegistered':
        world._system(actor)
        world._one('organizations', 'org_id', p['owner_org'])
        capacity = _posint(world, p['capacity'], 'invalid carrier capacity')
        fuel = _nonnegative_int(world, p['fuel'], 'invalid carrier fuel')
        world._require(isinstance(p['location'], str) and p['location'], 'invalid carrier location')
        db.execute('INSERT INTO carriers VALUES(?,?,?,?,?,?)', (p['carrier_id'], p['owner_org'], p['location'], capacity, fuel, 'ready'))
        return True
    if kind == 'ShipmentDispatched':
        courier = world._active(actor)
        src, dst = p['source_holder'], p['destination_holder']
        world._require(src != dst, 'shipment source and destination identical')
        world._require(src.startswith('organization:'), 'shipment must leave an organization depot')
        world._check_holder(src)
        depot = db.execute('SELECT * FROM depots WHERE holder=?', (src,)).fetchone()
        world._require(depot is not None, 'unregistered source depot')
        world._require(world._holder_authorized(actor, src), 'quartermaster permission required')
        world._require(courier['location'] == depot['location'], 'courier not at source depot')
        carrier = db.execute('SELECT * FROM carriers WHERE carrier_id=?', (p['carrier_id'],)).fetchone()
        world._require(carrier is not None and carrier['status'] == 'ready', 'carrier unavailable')
        world._require(carrier['owner_org'] == src.split(':', 1)[1] and carrier['location'] == depot['location'], 'carrier not at owning depot')
        if dst.startswith('organization:'):
            world._check_holder(dst)
            arrival = db.execute('SELECT location FROM depots WHERE holder=?', (dst,)).fetchone()
            world._require(arrival is not None, 'unregistered destination depot')
            destination = arrival['location']
        elif dst.startswith('region:'):
            region_id = dst.split(':', 1)[1]
            world._one('regions', 'region_id', region_id)
            arrival = db.execute('SELECT location FROM region_hubs WHERE region_id=?', (region_id,)).fetchone()
            world._require(arrival is not None, 'unregistered destination hub')
            world._require(p['material'] in ('food', 'water'), 'regional deliveries require food or water')
            destination = arrival['location']
        else:
            world._require(False, 'invalid destination holder')
        route = _open_route(world, p['route_id'], depot['location'], destination)
        qty = _posint(world, p['quantity'], 'invalid shipment quantity')
        world._require(qty <= carrier['capacity'], 'carrier capacity exceeded')
        material = p['material']
        world._require(isinstance(material, str) and bool(material), 'invalid cargo material')
        world._require(world._stock(src, material) >= qty, 'insufficient depot stock')
        fuel_cost = max(1, math.ceil(route['km'] * 10))
        world._require(carrier['fuel'] >= fuel_cost, 'insufficient carrier fuel')
        world._set_stock(src, material, world._stock(src, material) - qty)
        db.execute("UPDATE carriers SET status='transit',fuel=fuel-? WHERE carrier_id=?", (fuel_cost, carrier['carrier_id']))
        eta = tick + max(1, math.ceil(route['km'] * 3))
        db.execute('INSERT INTO shipments VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   (p['shipment_id'], src, dst, material, qty, carrier['carrier_id'], p['route_id'], depot['location'], destination, tick, eta, 'transit'))
        return True
    if kind == 'ShipmentDelivered':
        world._system(actor)
        s = _shipment(world, p['shipment_id'])
        world._require(s['status'] == 'transit', 'shipment already delivered')
        world._require(tick >= s['earliest_arrival_tick'], 'shipment still in transit')
        alternate = db.execute('SELECT * FROM shipment_reroutes WHERE shipment_id=?', (s['shipment_id'],)).fetchone()
        if alternate is None:
            _open_route(world, s['route_id'], s['origin'], s['destination'])
        else:
            import json
            pos = s['origin']
            for route_id in json.loads(alternate['route_ids']):
                route = db.execute('SELECT * FROM routes WHERE route_id=?', (route_id,)).fetchone()
                world._require(route is not None and pos in (route['point_a'],route['point_b']), 'reroute no longer connected')
                nxt = route['point_b'] if route['point_a']==pos else route['point_a']
                _open_route(world,route_id,pos,nxt)
                pos = nxt
            world._require(pos == s['destination'], 'reroute destination mismatch')
            world._require(tick >= alternate['earliest_arrival_tick'], 'rerouted shipment still in transit')
        carrier = db.execute('SELECT * FROM carriers WHERE carrier_id=?', (s['carrier_id'],)).fetchone()
        world._require(carrier is not None and carrier['status'] == 'transit' and carrier['location'] == s['origin'], 'carrier state inconsistent')
        dst = s['destination_holder']
        if dst.startswith('organization:'):
            world._set_stock(dst, s['material'], world._stock(dst, s['material']) + s['quantity'])
        else:
            region_id = dst.split(':', 1)[1]
            world._require(s['material'] in ('food', 'water'), 'unfit regional cargo')
            db.execute(f'UPDATE regions SET {s["material"]}={s["material"]}+? WHERE region_id=?', (s['quantity'], region_id))
        db.execute("UPDATE carriers SET status='ready',location=? WHERE carrier_id=?", (s['destination'], s['carrier_id']))
        db.execute("UPDATE shipments SET status='delivered' WHERE shipment_id=?", (s['shipment_id'],))
        return True
    if kind == 'ShipmentRerouted':
        world._system(actor)  # trusted simulated dispatcher, NOT remote client permission
        s = _shipment(world, p['shipment_id'])
        world._require(s['status']=='transit', 'shipment not traveling')
        world._require(db.execute('SELECT 1 FROM shipment_reroutes WHERE shipment_id=?', (s['shipment_id'],)).fetchone() is None, 'shipment already rerouted')
        rlist=p['route_ids']
        world._require(isinstance(rlist,list) and 2<=len(rlist)<=6 and all(isinstance(v,str) for v in rlist), 'invalid reroute itinerary')
        previous=db.execute('SELECT * FROM routes WHERE route_id=?', (s['route_id'],)).fetchone()
        world._require(previous is not None and previous['guarded_by_site'] is not None and world._one('sites','site_id',previous['guarded_by_site'])['status']!='operational', 'original route not obstructed')
        visited={s['origin']}
        pos=s['origin']
        distance=0.0
        for route_id in rlist:
            edge=db.execute('SELECT * FROM routes WHERE route_id=?',(route_id,)).fetchone()
            world._require(edge is not None and pos in (edge['point_a'],edge['point_b']), 'reroute itinerary disconnected')
            nxt=edge['point_b'] if pos==edge['point_a'] else edge['point_a']
            world._require(nxt not in visited, 'reroute itinerary contains cycle')
            _open_route(world,route_id,pos,nxt)
            visited.add(nxt)
            pos=nxt
            distance+=edge['km']
        world._require(pos==s['destination'], 'reroute does not reach destination')
        carrier=db.execute('SELECT * FROM carriers WHERE carrier_id=?',(s['carrier_id'],)).fetchone()
        world._require(carrier is not None and carrier['status']=='transit', 'cargo carrier not moving')
        extra_fuel=max(1,math.ceil(distance*10))
        world._require(carrier['fuel']>=extra_fuel, 'insufficient fuel for alternate route')
        eta=tick+max(1,math.ceil(distance*3))
        import json
        db.execute('INSERT INTO shipment_reroutes VALUES(?,?,?,?,?)',(s['shipment_id'],json.dumps(rlist,separators=(',',':')),distance,eta,extra_fuel))
        db.execute('UPDATE carriers SET fuel=fuel-? WHERE carrier_id=?',(extra_fuel,s['carrier_id']))
        return True
    if kind == 'CarrierRefueled':
        courier = world._active(actor)
        carrier = db.execute('SELECT * FROM carriers WHERE carrier_id=?', (p['carrier_id'],)).fetchone()
        world._require(carrier is not None and carrier['status'] == 'ready', 'carrier unavailable')
        holder = f'organization:{carrier["owner_org"]}'
        depot = db.execute('SELECT location FROM depots WHERE holder=?', (holder,)).fetchone()
        world._require(depot is not None and carrier['location'] == depot['location'] and courier['location'] == depot['location'], 'refuel requires owning depot presence')
        world._require(world._holder_authorized(actor, holder), 'quartermaster permission required')
        qty = _posint(world, p['quantity'], 'invalid refuel quantity')
        world._require(world._stock(holder, 'fuel_cell') >= qty, 'insufficient fuel cells')
        world._set_stock(holder, 'fuel_cell', world._stock(holder, 'fuel_cell') - qty)
        db.execute('UPDATE carriers SET fuel=fuel+? WHERE carrier_id=?', (qty * 20, p['carrier_id']))
        return True
    if kind == 'CarrierReturnStarted':
        world._system(actor)
        carrier = db.execute('SELECT * FROM carriers WHERE carrier_id=?', (p['carrier_id'],)).fetchone()
        world._require(carrier is not None and carrier['status'] == 'ready', 'carrier unavailable')
        depot = db.execute('SELECT location FROM depots WHERE holder=?', (f'organization:{carrier["owner_org"]}',)).fetchone()
        world._require(depot is not None, 'unregistered owning depot')
        route = _open_route(world, p['route_id'], carrier['location'], depot['location'])
        fuel_cost = max(1, math.ceil(route['km'] * 10))
        world._require(carrier['fuel'] >= fuel_cost, 'insufficient carrier fuel')
        arrival = tick + max(1, math.ceil(route['km'] * 3))
        db.execute('INSERT INTO carrier_moves VALUES(?,?,?,?,?,?,?,?)',
                   (p['move_id'], carrier['carrier_id'], p['route_id'], carrier['location'], depot['location'], tick, arrival, 'transit'))
        db.execute("UPDATE carriers SET status='transit',fuel=fuel-? WHERE carrier_id=?", (fuel_cost, carrier['carrier_id']))
        return True
    if kind == 'CarrierReturnCompleted':
        world._system(actor)
        move = db.execute('SELECT * FROM carrier_moves WHERE move_id=?', (p['move_id'],)).fetchone()
        world._require(move is not None and move['status'] == 'transit', 'return trip not in progress')
        world._require(tick >= move['earliest_arrival_tick'], 'return trip still in transit')
        _open_route(world, move['route_id'], move['origin'], move['destination'])
        carrier = db.execute('SELECT * FROM carriers WHERE carrier_id=?', (move['carrier_id'],)).fetchone()
        world._require(carrier['status'] == 'transit' and carrier['location'] == move['origin'], 'carrier return state inconsistent')
        db.execute("UPDATE carrier_moves SET status='completed' WHERE move_id=?", (p['move_id'],))
        db.execute("UPDATE carriers SET status='ready',location=? WHERE carrier_id=?", (move['destination'], move['carrier_id']))
        return True
    if kind == 'RegionProductionChanged':
        world._system(actor)
        world._one('regions', 'region_id', p['region_id'])
        food = _nonnegative_int(world, p['food_production'], 'invalid region food rate')
        water = _nonnegative_int(world, p['water_production'], 'invalid region water rate')
        db.execute('UPDATE regions SET food_production=?,water_production=? WHERE region_id=?', (food, water, p['region_id']))
        return True
    return False
