"""V0.2 tests of reversible failures, timed rescue, and conserved transport cargo.
These are offline tests only; no clinician or network actor is authenticated.
"""
from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from worldstate import World, WorldRuleError
from worldstate.scenarios import seed_world


class ExpandedRules(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.s = seed_world(self.w)

    def tearDown(self):
        self.w.close()

    def row(self, table, pk, value):
        return dict(self.w.db.execute(f'SELECT * FROM {table} WHERE {pk}=?', (value,)).fetchone())

    def advance(self, n=10):
        self.s.tick += n

    def move(self, actor, route, source, dest):
        return self.s.emit('CharacterMoved', actor=actor, character_id=actor, route_id=route, **{'from':source, 'to':dest})

    def setup_medical(self, injury=95):
        self.s.emit('StockProvisioned', holder='character:b1', material='transport_kit', quantity=8)
        self.move('b1', 'road:civic-camp', 'Civic', 'Camp')
        self.move('b1', 'road:camp-forest', 'Camp', 'Forest')
        self.s.emit('CharacterInjured', character_id='d1', severity=injury)
        self.s.emit('MedicalCaseOpened', case_id='M1', character_id='d1', hospital_site='hospital', deadline_tick=self.s.tick + 40)

    def setup_freight(self):
        self.s.emit('DepotRegistered', holder='organization:union', location='Camp')
        self.s.emit('DepotRegistered', holder='organization:city', location='Civic')
        self.s.emit('RegionHubRegistered', region_id='Southplain', location='Civic')
        self.s.emit('CarrierRegistered', carrier_id='freight1', owner_org='union', location='Camp', capacity=15, fuel=40)
        self.s.emit('StockProvisioned', holder='organization:union', material='food', quantity=500)
        self.s.emit('StockProvisioned', holder='organization:union', material='water', quantity=500)
        self.s.emit('StockProvisioned', holder='organization:union', material='fuel_cell', quantity=200)

    def send(self, name, destination='organization:city', material='food', qty=5, route='road:civic-camp'):
        return self.s.emit('ShipmentDispatched', actor='c1', shipment_id=name, source_holder='organization:union',
                           destination_holder=destination, material=material, quantity=qty, carrier_id='freight1', route_id=route)

    def deliver(self, name):
        return self.s.emit('ShipmentDelivered', shipment_id=name)

    def return_vehicle(self, name):
        self.s.emit('CarrierReturnStarted', move_id=name, carrier_id='freight1', route_id='road:civic-camp')
        self.advance(5)
        return self.s.emit('CarrierReturnCompleted', move_id=name)

    def test_01_all_legacy_cases_still_pass_separately(self):
        self.assertEqual(45, len(self.w.ledger()))
        self.assertEqual(2, self.w.db.execute('PRAGMA user_version').fetchone()[0])
        self.assertIn('medical_cases', self.w.snapshot())

    def test_02_medical_case_requires_incapacitation(self):
        with self.assertRaisesRegex(WorldRuleError,'incapacitated'):
            self.s.emit('MedicalCaseOpened', case_id='bad', character_id='d1', hospital_site='hospital', deadline_tick=self.s.tick+15)

    def test_03_medical_case_deadline_must_be_future_and_bounded(self):
        self.s.emit('CharacterInjured', character_id='d1', severity=95)
        for delta in (0, 123):
            h=self.w.state_hash()
            with self.assertRaisesRegex(WorldRuleError,'rescue deadline'):
                self.s.emit('MedicalCaseOpened', case_id='bad', character_id='d1', hospital_site='hospital', deadline_tick=self.s.tick+delta)
            self.assertEqual(h,self.w.state_hash())

    def test_04_medical_stabilization_is_single_use_and_colocated(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized', actor='b1', case_id='M1')
        self.assertEqual('stabilized', self.row('medical_cases','case_id','M1')['state'])
        self.assertEqual(1,self.w.stock('character:b1','field_kit'))
        with self.assertRaisesRegex(WorldRuleError,'cannot be stabilized'):
            self.s.emit('MedicalCaseStabilized', actor='b1', case_id='M1')

    def test_05_late_medical_rescue_rejected_without_spending_kit(self):
        self.setup_medical()
        self.advance(50)
        before=self.w.stock('character:b1','field_kit')
        with self.assertRaisesRegex(WorldRuleError,'expired'):
            self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        self.assertEqual(before,self.w.stock('character:b1','field_kit'))

    def test_06_expired_case_dies_irreversibly_and_enters_estate(self):
        self.setup_medical()
        self.advance(50)
        self.s.emit('MedicalCaseExpired',case_id='M1')
        self.assertEqual('expired', self.row('medical_cases','case_id','M1')['state'])
        self.assertEqual('deceased', self.row('characters','character_id','d1')['state'])
        with self.assertRaisesRegex(WorldRuleError, 'case is not open'):
            self.s.emit('MedicalCaseExpired',case_id='M1')
        self.s.emit('CharacterEntered', account_id='account_d', character_id='d2', origin='Orrel', location='Civic')
        self.assertEqual('active',self.row('characters','character_id','d2')['state'])

    def test_07_cannot_expire_before_deadline(self):
        self.setup_medical()
        with self.assertRaisesRegex(WorldRuleError,'not yet expired'):
            self.s.emit('MedicalCaseExpired',case_id='M1')
        self.assertEqual('incapacitated',self.row('characters','character_id','d1')['state'])

    def test_08_medical_transport_requires_stabilization(self):
        self.setup_medical()
        with self.assertRaisesRegex(WorldRuleError,'not ready'):
            self.s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id='T1',route_id='road:camp-forest',to='Camp')

    def test_09_medical_transports_multiple_hops_then_recovery(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        for i,(route,to) in enumerate((('road:camp-forest','Camp'),('road:civic-camp','Civic'),('road:civic-hospital','hospital')),1):
            ident=f'T{i}'
            self.s.emit('MedicalTransportStarted', actor='b1', case_id='M1',transport_id=ident,route_id=route,to=to)
            with self.assertRaisesRegex(WorldRuleError,'medical transport'):
                self.move('b1',route,self.row('characters','character_id','b1')['location'],to)
            with self.assertRaisesRegex(WorldRuleError,'in transit'):
                self.s.emit('MedicalTransportCompleted',transport_id=ident)
            self.advance(10)
            self.s.emit('MedicalTransportCompleted',transport_id=ident)
            self.assertEqual(to,self.row('characters','character_id','d1')['location'])
            self.assertEqual(to,self.row('characters','character_id','b1')['location'])
        self.assertEqual('admitted',self.row('medical_cases','case_id','M1')['state'])
        with self.assertRaisesRegex(WorldRuleError,'not complete'):
            self.s.emit('MedicalCaseRecovered',case_id='M1')
        self.advance(11)
        self.s.emit('MedicalCaseRecovered',case_id='M1')
        self.assertEqual('active',self.row('characters','character_id','d1')['state'])
        self.assertEqual('recovered',self.row('medical_cases','case_id','M1')['state'])
        self.w.audit_state()

    def test_10_case_is_not_recoverable_before_admission(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        self.advance(30)
        with self.assertRaisesRegex(WorldRuleError,'not admitted'):
            self.s.emit('MedicalCaseRecovered',case_id='M1')

    def test_11_a_survivor_can_have_a_second_emergency_after_recovery(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        self.s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id='T1',route_id='road:camp-forest',to='Camp')
        self.advance(10)
        self.s.emit('MedicalTransportCompleted',transport_id='T1')
        self.s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id='T2',route_id='road:civic-camp',to='Civic')
        self.advance(10)
        self.s.emit('MedicalTransportCompleted',transport_id='T2')
        self.s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id='T3',route_id='road:civic-hospital',to='hospital')
        self.advance(10)
        self.s.emit('MedicalTransportCompleted',transport_id='T3')
        self.advance(11)
        self.s.emit('MedicalCaseRecovered',case_id='M1')
        self.s.emit('CharacterInjured',character_id='d1',severity=90)
        self.s.emit('MedicalCaseOpened',case_id='M2',character_id='d1',hospital_site='hospital',deadline_tick=self.s.tick+30)
        self.assertEqual('open',self.row('medical_cases','case_id','M2')['state'])

    def test_12_cannot_use_legacy_stabilize_to_bypass_timer(self):
        self.setup_medical()
        with self.assertRaisesRegex(WorldRuleError,'timed case'):
            self.s.emit('CharacterStabilized',actor='b1',character_id='d1')

    def test_13_death_closes_active_medical_case(self):
        self.setup_medical()
        self.s.emit('CharacterDied',character_id='d1',reason='terminal')
        self.assertEqual('deceased',self.row('medical_cases','case_id','M1')['state'])

    def test_14_freight_dispatch_custody_and_no_instant_delivery(self):
        self.setup_freight()
        self.send('S1')
        self.assertEqual(495,self.w.stock('organization:union','food'))
        self.assertEqual(0,self.w.stock('organization:city','food'))
        self.assertEqual('transit',self.row('shipments','shipment_id','S1')['status'])
        with self.assertRaisesRegex(WorldRuleError,'in transit'):
            self.deliver('S1')
        self.advance(10)
        self.deliver('S1')
        self.assertEqual(5,self.w.stock('organization:city','food'))

    def test_15_shipment_cannot_exceed_capacity(self):
        self.setup_freight()
        with self.assertRaisesRegex(WorldRuleError,'capacity'):
            self.send('S1',qty=20)
        self.assertEqual(500,self.w.stock('organization:union','food'))

    def test_16_no_shipments_without_existing_route_or_permission(self):
        self.setup_freight()
        for actor,route,part in (('a1','road:civic-camp','quartermaster'),('c1','road:civic-lab','route does not connect')):
            before=self.w.state_hash()
            with self.assertRaisesRegex(WorldRuleError,part):
                self.s.emit('ShipmentDispatched',actor=actor,shipment_id='Bad',source_holder='organization:union',destination_holder='organization:city',material='food',quantity=5,carrier_id='freight1',route_id=route)
            self.assertEqual(before,self.w.state_hash())

    def test_17_region_supply_delivered_not_just_recorded(self):
        self.setup_freight()
        before=self.row('regions','region_id','Southplain')['food']
        self.send('S1',destination='region:Southplain',material='food',qty=13)
        self.assertEqual(before,self.row('regions','region_id','Southplain')['food'])
        self.advance(10)
        self.deliver('S1')
        self.assertEqual(before+13,self.row('regions','region_id','Southplain')['food'])
        self.w.audit_state()

    def test_18_region_cannot_receive_nonfood_material(self):
        self.setup_freight()
        with self.assertRaisesRegex(WorldRuleError,'food or water'):
            self.send('S1',destination='region:Southplain',material='steel')

    def test_19_cannot_dispatch_two_shipments_with_one_carrier(self):
        self.setup_freight()
        self.send('S1')
        with self.assertRaisesRegex(WorldRuleError,'unavailable'):
            self.send('S2')

    def test_20_shipment_duplicate_after_delivery_is_exact_once(self):
        self.setup_freight()
        start=self.send('S1')
        self.advance(10)
        finish=self.deliver('S1')
        before=self.w.state_hash()
        d=self.w.apply(finish['event_id'],'ShipmentDelivered','system',{'shipment_id':'S1'},tick=self.s.tick)
        self.assertTrue(d['duplicate'])
        self.assertEqual(before,self.w.state_hash())
        with self.assertRaisesRegex(WorldRuleError,'already delivered'):
            self.deliver('S1')

    def test_21_carrier_return_requires_duration_and_fuel(self):
        self.setup_freight()
        self.send('S1')
        self.advance(10)
        self.deliver('S1')
        self.s.emit('CarrierReturnStarted',move_id='RT1',carrier_id='freight1',route_id='road:civic-camp')
        with self.assertRaisesRegex(WorldRuleError,'still in transit'):
            self.s.emit('CarrierReturnCompleted',move_id='RT1')
        self.advance(10)
        self.s.emit('CarrierReturnCompleted',move_id='RT1')
        self.assertEqual('Camp',self.row('carriers','carrier_id','freight1')['location'])

    def test_22_refuel_requires_actual_cells_and_local_quartermaster(self):
        self.setup_freight()
        before=self.w.stock('organization:union','fuel_cell')
        self.s.emit('CarrierRefueled',actor='c1',carrier_id='freight1',quantity=2)
        self.assertEqual(before-2,self.w.stock('organization:union','fuel_cell'))
        self.assertEqual(80,self.row('carriers','carrier_id','freight1')['fuel'])

    def test_23_refuel_failure_rolls_back(self):
        self.setup_freight()
        old=self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError,'insufficient fuel cells'):
            self.s.emit('CarrierRefueled',actor='c1',carrier_id='freight1',quantity=201)
        self.assertEqual(old,self.w.state_hash())

    def test_24_region_production_can_be_changed(self):
        self.setup_freight()
        self.s.emit('RegionProductionChanged',region_id='Southplain',food_production=0,water_production=0)
        self.s.emit('RegionAdvanced',region_id='Southplain',steps=2)
        self.assertEqual(980,self.row('regions','region_id','Southplain')['food'])

    def test_25_crash_during_shipment_dispatch_rolls_back_cargo_and_fuel(self):
        self.setup_freight()
        before=self.w.state_hash()
        tick=self.s.tick+1
        with self.assertRaisesRegex(RuntimeError,'SIMULATED_CRASH'):
            self.w.apply('CrashShipment','ShipmentDispatched','c1',{'shipment_id':'SC','source_holder':'organization:union','destination_holder':'organization:city','material':'food','quantity':5,'carrier_id':'freight1','route_id':'road:civic-camp'},tick=tick,crash_before_commit=True)
        self.assertEqual(before,self.w.state_hash())
        self.assertEqual(0,self.w.db.execute('SELECT COUNT(*) FROM shipments').fetchone()[0])

    def test_26_bridge_obstruction_stalls_but_does_not_lose_shipment(self):
        # A newly authorized depot on Westbank ships across the physical bridge.
        self.s.emit('MembershipGranted',org_id='city',character_id='a1',role='quartermaster')
        self.s.emit('DepotRegistered',holder='organization:city',location='Westbank')
        self.s.emit('DepotRegistered',holder='organization:union',location='Civic')
        self.s.emit('CarrierRegistered',carrier_id='c',owner_org='city',location='Westbank',capacity=10,fuel=50)
        self.s.emit('StockProvisioned',holder='organization:city',material='food',quantity=10)
        self.s.emit('ShipmentDispatched',actor='a1',shipment_id='S',source_holder='organization:city',destination_holder='organization:union',material='food',quantity=5,carrier_id='c',route_id='road:central')
        self.move('c1','road:civic-camp','Camp','Civic')
        self.move('c1','road:civic-bridge','Civic','bridge')
        self.s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        self.advance(15)
        with self.assertRaisesRegex(WorldRuleError,'obstructed'):
            self.s.emit('ShipmentDelivered',shipment_id='S')
        self.assertEqual(0,self.w.stock('organization:union','food'))
        self.assertEqual('transit',self.row('shipments','shipment_id','S')['status'])
        self.move('a1','road:lower-west','Westbank','LowerCrossing')
        self.move('a1','road:lower-east','LowerCrossing','Civic')
        self.move('a1','road:civic-bridge','Civic','bridge')
        self.s.emit('SiteCleared',actor='a1',site_id='bridge',expected_version=1)
        self.s.emit('ShipmentDelivered',shipment_id='S')
        self.assertEqual(5,self.w.stock('organization:union','food'))

    def test_27_old_v01_trace_replays_in_new_schema(self):
        old=Path(__file__).parents[1]/'output'/'demo_events.jsonl'
        with World.replay_jsonl(old) as w:
            self.assertEqual(64,len(w.ledger()))
            self.assertEqual(2,w.db.execute('PRAGMA user_version').fetchone()[0])
            self.assertEqual(0,len(w.snapshot()['shipments']))
            self.assertEqual('PASS',w.audit_state()['status'])

    def test_28_multiple_case_only_one_active_at_time(self):
        self.setup_medical()
        with self.assertRaisesRegex(WorldRuleError,'open medical case'):
            self.s.emit('MedicalCaseOpened',case_id='M2',character_id='d1',hospital_site='hospital',deadline_tick=self.s.tick+30)

    def test_29_cannot_discharge_during_nonmedical_case(self):
        self.setup_medical()
        with self.assertRaisesRegex(WorldRuleError,'not admitted'):
            self.s.emit('MedicalCaseRecovered',case_id='M1')

    def test_30_audits_verify_expanded_tables(self):
        self.setup_freight()
        self.send('S1')
        self.assertEqual('PASS',self.w.audit_state()['status'])
        self.w.db.execute("UPDATE shipments SET quantity=999 WHERE shipment_id='S1'")
        with self.assertRaisesRegex(WorldRuleError,'materialized state'):
            self.w.audit_state()

    def test_31_randomized_cargo_cycles_and_replay(self):
        self.setup_freight()
        rng=random.Random(8619)
        source_totals={m:self.w.stock('organization:union',m)+self.w.stock('organization:city',m) for m in ('food','water')}
        for i in range(75):
            m=rng.choice(('food','water'))
            q=rng.randint(1,10)
            if self.row('carriers','carrier_id','freight1')['fuel']<20:
                self.s.emit('CarrierRefueled',actor='c1',carrier_id='freight1',quantity=3)
            name=f'X{i:03}'
            self.send(name,material=m,qty=q)
            carried=sum(x['quantity'] for x in self.w.snapshot()['shipments'] if x['status']=='transit' and x['material']==m)
            self.assertEqual(source_totals[m],self.w.stock('organization:union',m)+self.w.stock('organization:city',m)+carried)
            self.advance(5)
            self.deliver(name)
            self.assertEqual(source_totals[m],self.w.stock('organization:union',m)+self.w.stock('organization:city',m))
            self.return_vehicle(f'R{i:03}')
        self.assertEqual('PASS',self.w.audit_state()['status'])
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'out.jsonl'
            self.w.export_jsonl(f)
            with World.replay_jsonl(f) as replay:
                self.assertEqual(self.w.state_hash(),replay.state_hash())

    def test_32_randomized_invalid_actions_leave_state_unchanged(self):
        self.setup_freight()
        rng=random.Random(641)
        for i in range(80):
            q=rng.choice((-100,0,16,20,False,3.5,100001))
            prior=self.w.state_hash()
            try:
                self.send(f'FAIL{i}',qty=q)
            except (WorldRuleError,TypeError,ValueError):
                self.assertEqual(prior,self.w.state_hash())
            else:
                self.fail(f'bad shipment quantity accepted: {q!r}')

    def test_33_reroute_open_bridge_rejected(self):
        self.s.emit('MembershipGranted',org_id='city',character_id='a1',role='quartermaster')
        self.s.emit('DepotRegistered',holder='organization:city',location='Westbank')
        self.s.emit('DepotRegistered',holder='organization:union',location='Civic')
        self.s.emit('CarrierRegistered',carrier_id='c',owner_org='city',location='Westbank',capacity=12,fuel=120)
        self.s.emit('StockProvisioned',holder='organization:city',material='food',quantity=20)
        self.s.emit('ShipmentDispatched',actor='a1',shipment_id='S',source_holder='organization:city',destination_holder='organization:union',material='food',quantity=5,carrier_id='c',route_id='road:central')
        with self.assertRaisesRegex(WorldRuleError,'not obstructed'):
            self.s.emit('ShipmentRerouted',shipment_id='S',route_ids=['road:lower-west','road:lower-east'])
        self.assertEqual(0,len(self.w.snapshot()['shipment_reroutes']))

    def test_34_reroute_blocked_bridge_uses_real_alternate_and_extra_fuel(self):
        self.s.emit('MembershipGranted',org_id='city',character_id='a1',role='quartermaster')
        self.s.emit('DepotRegistered',holder='organization:city',location='Westbank')
        self.s.emit('DepotRegistered',holder='organization:union',location='Civic')
        self.s.emit('CarrierRegistered',carrier_id='c',owner_org='city',location='Westbank',capacity=12,fuel=130)
        self.s.emit('StockProvisioned',holder='organization:city',material='food',quantity=20)
        self.s.emit('ShipmentDispatched',actor='a1',shipment_id='S',source_holder='organization:city',destination_holder='organization:union',material='food',quantity=5,carrier_id='c',route_id='road:central')
        self.move('c1','road:civic-camp','Camp','Civic')
        self.move('c1','road:civic-bridge','Civic','bridge')
        self.s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        failed=self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError,'disconnected'):
            self.s.emit('ShipmentRerouted',shipment_id='S',route_ids=['road:lower-east','road:lower-west'])
        self.assertEqual(failed,self.w.state_hash())
        self.s.emit('ShipmentRerouted',shipment_id='S',route_ids=['road:lower-west','road:lower-east'])
        self.assertAlmostEqual(6.61,self.row('shipment_reroutes','shipment_id','S')['distance_km'])
        self.assertEqual(130-21-67,self.row('carriers','carrier_id','c')['fuel'])
        with self.assertRaisesRegex(WorldRuleError,'in transit'):
            self.s.emit('ShipmentDelivered',shipment_id='S')
        self.advance(25)
        self.s.emit('ShipmentDelivered',shipment_id='S')
        self.assertEqual(5,self.w.stock('organization:union','food'))
        self.assertEqual('operational',self.row('sites','site_id','hospital')['status'])
        self.assertEqual('PASS',self.w.audit_state()['status'])

    def test_35_medical_transport_aborts_when_patient_dies(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        self.s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id='T1',route_id='road:camp-forest',to='Camp')
        self.s.emit('CharacterDied',character_id='d1',reason='terminal')
        self.assertEqual('aborted',self.row('medical_transports','transport_id','T1')['status'])
        self.advance(15)
        with self.assertRaisesRegex(WorldRuleError,'not in progress'):
            self.s.emit('MedicalTransportCompleted',transport_id='T1')
        self.w.audit_state()

    def test_36_medical_transport_aborts_when_responder_dies(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        self.s.emit('MedicalTransportStarted',actor='b1',case_id='M1',transport_id='T1',route_id='road:camp-forest',to='Camp')
        self.s.emit('CharacterDied',character_id='b1',reason='terminal')
        self.assertEqual('aborted',self.row('medical_transports','transport_id','T1')['status'])
        self.w.audit_state()

    def test_37_ill_patient_cannot_walk_out_of_hospital(self):
        self.setup_medical()
        self.s.emit('MedicalCaseStabilized',actor='b1',case_id='M1')
        with self.assertRaisesRegex(WorldRuleError,'patient requires medical transport'):
            self.move('d1','road:camp-forest','Forest','Camp')

    def test_38_reroute_extra_fuel_cannot_be_negative(self):
        self.s.emit('MembershipGranted',org_id='city',character_id='a1',role='quartermaster')
        self.s.emit('DepotRegistered',holder='organization:city',location='Westbank')
        self.s.emit('DepotRegistered',holder='organization:union',location='Civic')
        self.s.emit('CarrierRegistered',carrier_id='c',owner_org='city',location='Westbank',capacity=12,fuel=35)
        self.s.emit('StockProvisioned',holder='organization:city',material='food',quantity=20)
        self.s.emit('ShipmentDispatched',actor='a1',shipment_id='S',source_holder='organization:city',destination_holder='organization:union',material='food',quantity=5,carrier_id='c',route_id='road:central')
        self.move('c1','road:civic-camp','Camp','Civic')
        self.move('c1','road:civic-bridge','Civic','bridge')
        self.s.emit('SiteObstructed',actor='c1',site_id='bridge',expected_version=0)
        before=self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError,'insufficient fuel'):
            self.s.emit('ShipmentRerouted',shipment_id='S',route_ids=['road:lower-west','road:lower-east'])
        self.assertEqual(before,self.w.state_hash())
        self.assertEqual(5,self.row('shipments','shipment_id','S')['quantity'])

    def test_39_legacy_v01_sqlite_database_opens_and_audits(self):
        import shutil
        original=Path(__file__).parents[1]/'output'/'demo_world.sqlite3'
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'old.sqlite3'
            shutil.copy2(original,db)
            with World(db) as older:
                self.assertEqual(2,older.db.execute('PRAGMA user_version').fetchone()[0])
                self.assertEqual(64,len(older.ledger()))
                self.assertEqual('PASS',older.audit_state()['status'])
                self.assertEqual([],older.snapshot()['medical_cases'])

    def test_40_multi_seed_randomized_stress_replays_identically(self):
        from worldstate.stress import run_stress
        with tempfile.TemporaryDirectory() as directory:
            result_a=run_stress(Path(directory)/'a',seed=239,rounds=35,restart_every=7)
            result_b=run_stress(Path(directory)/'b',seed=239,rounds=35,restart_every=7)
            self.assertEqual(result_a['state_sha256'],result_b['state_sha256'])
            self.assertEqual(result_a['ledger_last_hash'],result_b['ledger_last_hash'])
            self.assertEqual('PASS',result_a['status'])
            self.assertEqual(result_a['events'],result_b['events'])

    def test_41_legacy_stock_transfer_cannot_bypass_registered_remote_depots(self):
        self.setup_freight()
        before=self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError,'remote depots require physical shipment'):
            self.s.emit('StockTransferred',actor='c1',from_holder='organization:union',to_holder='organization:city',material='food',quantity=20)
        self.assertEqual(before,self.w.state_hash())

    def test_42_expanded_narrative_demo_replays_exactly(self):
        from worldstate.demo_expanded import run_expanded_demo
        with tempfile.TemporaryDirectory() as d:
            report=run_expanded_demo(d)
            self.assertEqual('PASS',report['status'])
            self.assertEqual('recovered',report['medical_case']['state'])
            self.assertEqual(20,report['regional_food_after']-report['regional_food_before'])
            self.assertAlmostEqual(6.61,report['alternate_freight_distance_km'])
            self.assertEqual(report['state_sha256'],report['replay_state_sha256'])


if __name__=='__main__':
    unittest.main()
