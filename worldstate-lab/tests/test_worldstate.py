"""Executable design scenarios S1-S12 plus adversarial transactional tests.

These test an OFFLINE RULES PROTOTYPE; they do not certify client, server, browser
or production authentication/security behavior.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from worldstate import World, WorldRuleError
from worldstate.scenarios import seed_world, run_demo


class WorldStateScenarios(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.s = seed_world(self.w)

    def tearDown(self):
        self.w.close()

    def c(self, cid):
        return dict(self.w._one("characters", "character_id", cid))

    def site(self, sid):
        return dict(self.w._one("sites", "site_id", sid))

    def item(self, iid):
        return dict(self.w._one("items", "item_id", iid))

    def move(self, char, orig, dest, rid):
        return self.s.emit("CharacterMoved", actor=char, character_id=char, route_id=rid, **{"from": orig, "to": dest})

    def setup_repair(self):
        self.move("a1", "Westbank", "Civic", "road:central")
        self.move("a1", "Civic", "pump", "road:civic-pump")
        self.move("b1", "Civic", "pump", "road:civic-pump")
        self.s.emit("StockTransferred", actor="c1", from_holder="organization:union", to_holder="organization:city", material="steel", quantity=8)
        self.s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)

    def setup_bridge_obstruction(self):
        self.move("c1", "Camp", "Civic", "road:civic-camp")
        self.move("c1", "Civic", "bridge", "road:civic-bridge")
        self.s.emit("SiteObstructed", actor="c1", site_id="bridge", expected_version=0)

    def test_s01_mortal_death_new_character_no_knowledge_transfer(self):
        self.s.emit("CharacterPrivateNote", actor="a1", character_id="a1", text="hidden source record")
        self.s.emit("CharacterDied", character_id="a1", reason="irrecoverable")
        self.assertEqual("deceased", self.c("a1")["state"])
        self.assertEqual("estate:a1", self.item("notebook_a")["custodian"])
        self.assertEqual("Westbank", self.item("notebook_a")["location"])
        self.s.emit("CharacterEntered", character_id="a2", account_id="account_a", origin="Orrel Crossing", location="Civic")
        self.assertEqual("active", self.c("a2")["state"])
        self.assertEqual("[]", self.c("a2")["private_knowledge"])
        self.assertEqual(0, len([i for i in self.w.snapshot()["items"] if i["custodian"] == "character:a2"]))
        with self.assertRaisesRegex(WorldRuleError, "dead"):
            self.s.emit("CharacterPrivateNote", actor="a1", character_id="a1", text="still alive")

    def test_s02_rescue_same_physical_character(self):
        self.move("b1", "Civic", "Camp", "road:civic-camp")
        self.move("b1", "Camp", "Forest", "road:camp-forest")
        self.s.emit("CharacterInjured", character_id="d1", severity=92)
        self.assertEqual("incapacitated", self.c("d1")["state"])
        self.s.emit("CharacterStabilized", actor="b1", character_id="d1")
        self.s.emit("CharacterRehabilitating", character_id="d1")
        self.s.emit("CharacterRecovered", character_id="d1")
        self.assertEqual("active", self.c("d1")["state"])
        self.assertEqual(1, self.w.stock("character:b1", "field_kit"))
        self.assertNotIn("d2", [r["character_id"] for r in self.w.snapshot()["characters"]])

    def test_s03_disconnect_reconnect_keeps_identity_and_location(self):
        self.s.emit("CharacterDisconnected", character_id="d1")
        self.assertEqual(0, self.c("d1")["connected"])
        self.assertEqual("Forest", self.c("d1")["location"])
        with self.assertRaisesRegex(WorldRuleError, "not connected"):
            self.s.emit("CharacterPrivateNote", actor="d1", character_id="d1", text="while offline")
        self.s.emit("CharacterReconnected", character_id="d1")
        self.assertEqual(1, self.c("d1")["connected"])
        self.assertEqual("Forest", self.c("d1")["location"])

    def test_s04_account_sanction_outlives_character(self):
        self.s.emit("AccountSanctioned", account_id="account_c", sanctioned=True)
        with self.assertRaisesRegex(WorldRuleError, "sanctioned"):
            self.s.emit("EvidenceRecorded", actor="c1", record_id="illegal", summary="x", source="log", classification="private")
        self.s.emit("CharacterDied", character_id="c1", reason="incident")
        with self.assertRaisesRegex(WorldRuleError, "sanctioned"):
            self.s.emit("CharacterEntered", account_id="account_c", character_id="c2", location="Civic", origin="Westbank")
        self.assertEqual(1, dict(self.w._one("accounts", "account_id", "account_c"))["sanctioned"])

    def test_s05_private_clinical_evidence_not_public(self):
        self.s.emit("EvidenceRecorded", actor="a1", record_id="case_private", summary="Private family medical note", source="hospital", classification="clinical")
        self.assertTrue(self.w.evidence_visible_to("case_private", "a1"))
        self.assertFalse(self.w.evidence_visible_to("case_private", "c1"))
        with self.assertRaisesRegex(WorldRuleError, "clinical"):
            self.s.emit("EvidencePublished", actor="a1", record_id="case_private")
        self.assertFalse(self.w.evidence_visible_to("case_private", None))
        self.s.emit("EvidenceRecorded", actor="a1", record_id="safe_abstract", summary="Summarized public gauge findings", source="public instrument", classification="private")
        self.s.emit("EvidencePublished", actor="a1", record_id="safe_abstract")
        self.assertTrue(self.w.evidence_visible_to("safe_abstract", None))

    def test_s06_two_repair_attempts_only_one_state(self):
        self.setup_repair()
        committed = self.s.emit("SiteRepaired", actor="a1", site_id="pump", expected_version=1, material="steel", quantity=10)
        self.assertEqual("operational", self.site("pump")["status"])
        self.assertEqual(5, self.w.stock("organization:city", "steel"))
        before = self.w.state_hash()
        retry = self.w.apply(committed["event_id"], "SiteRepaired", "a1", {"site_id":"pump", "expected_version":1, "material":"steel", "quantity":10}, tick=self.s.tick)
        self.assertTrue(retry["duplicate"])
        self.assertEqual(before, self.w.state_hash())
        with self.assertRaisesRegex(WorldRuleError, "stale site version"):
            self.s.emit("SiteRepaired", actor="a1", site_id="pump", expected_version=1, material="steel", quantity=10)
        self.assertEqual(5, self.w.stock("organization:city", "steel"))

    def test_s07_item_theft_needs_physical_custody_no_global_conviction(self):
        self.s.emit("ItemDropped", actor="c1", item_id="scanner_c")
        self.move("d1", "Forest", "Camp", "road:camp-forest")
        self.s.emit("ItemCollected", actor="d1", item_id="scanner_c")
        it = self.item("scanner_c")
        self.assertEqual("character:d1", it["custodian"])
        self.assertEqual("character:c1", it["legal_owner"])
        self.assertEqual(1, it["disputed"])
        self.assertEqual(0, len(self.w.snapshot()["reports"]))
        self.s.emit("ReportFiled", actor="c1", report_id="statement_01", community="Westbank", subject="d1", claim="Took my scanner", evidence_ref="")
        self.assertEqual(1, len(self.w.snapshot()["reports"]))

    def test_s08_dam_and_hospital_not_one_click_targets(self):
        self.move("e1", "Civic", "hospital", "road:civic-hospital")
        with self.assertRaisesRegex(WorldRuleError, "high-consequence"):
            self.s.emit("SiteObstructed", actor="e1", site_id="hospital", expected_version=0)
        self.move("c1", "Camp", "Civic", "road:civic-camp")
        self.move("c1", "Civic", "dam", "road:civic-dam")
        with self.assertRaisesRegex(WorldRuleError, "high-consequence"):
            self.s.emit("SiteObstructed", actor="c1", site_id="dam", expected_version=0)
        self.assertEqual("operational", self.site("hospital")["status"])
        self.assertEqual("operational", self.site("dam")["status"])

    def test_s09_biohybrid_requires_energy_and_nutrients(self):
        self.s.emit("AgentAdvanced", agent_id="custodian_01", energy_used=2, nutrients_used=1)
        self.s.emit("AgentAdvanced", agent_id="custodian_01", energy_used=1, nutrients_used=1)
        ag = dict(self.w._one("agents", "agent_id", "custodian_01"))
        self.assertEqual("dormant", ag["status"])
        self.assertEqual(0, ag["energy"])
        self.assertEqual(0, ag["nutrients"])
        with self.assertRaisesRegex(WorldRuleError, "dormant"):
            self.s.emit("AgentAdvanced", agent_id="custodian_01", energy_used=1, nutrients_used=1)

    def test_s10_hotspot_1000_players_is_not_claimed(self):
        # The lab is purposefully NOT a load test. It can register user identities,
        # but cannot satisfy real hardware/browser proof from account counts.
        self.assertFalse(hasattr(self.w, "tick_render_1000_players"))
        self.assertFalse(hasattr(self.w, "webgl_client"))
        self.assertEqual(13, len(self.w.snapshot()["routes"]))

    def test_s11_dormant_population_supply_ledger(self):
        self.s.emit("RegionAdvanced", region_id="Southplain", steps=7)
        rg = dict(self.w._one("regions", "region_id", "Southplain"))
        self.assertEqual(1014, rg["food"])
        self.assertEqual(1021, rg["water"])
        self.assertEqual(7, rg["last_tick"])
        with self.assertRaisesRegex(WorldRuleError, "bounded"):
            self.s.emit("RegionAdvanced", region_id="Southplain", steps=10000)
        self.assertEqual(7, dict(self.w._one("regions", "region_id", "Southplain"))["last_tick"])

    def test_s12_offline_org_asset_not_deleted(self):
        self.s.emit("CharacterDisconnected", character_id="a1")
        self.assertEqual("operational", self.site("repair_shop")["status"])
        self.assertIn("city", [x["org_id"] for x in self.w.snapshot()["organizations"]])
        self.assertEqual("city", self.site("repair_shop")["owner_org"])
        self.s.emit("CharacterReconnected", character_id="a1")
        self.assertEqual("operational", self.site("repair_shop")["status"])

    def test_s13_bridge_closure_and_opening_really_changes_routes(self):
        self.assertEqual(2.017, self.w.shortest_route("Westbank", "Civic")["km"])
        self.setup_bridge_obstruction()
        self.assertEqual(6.61, self.w.shortest_route("Westbank", "Civic")["km"])
        self.assertEqual(1, self.w.stock("character:c1", "barrier_kit"))
        self.move("a1", "Westbank", "LowerCrossing", "road:lower-west")
        self.move("a1", "LowerCrossing", "Civic", "road:lower-east")
        self.move("a1", "Civic", "bridge", "road:civic-bridge")
        self.s.emit("SiteCleared", actor="a1", site_id="bridge", expected_version=1)
        self.assertEqual(2.017, self.w.shortest_route("Westbank", "Civic")["km"])

    def test_s14_interworld_road_closure_does_not_blackout_city(self):
        self.s.emit("RoadClosed", link_id="Cydren Skygate")
        self.s.emit("RoadClosed", link_id="Orveth Freight Ring")
        self.assertEqual("operational", self.site("hospital")["status"])
        self.assertEqual("operational", self.site("bridge")["status"])
        self.assertEqual("restricted", self.site("pump")["status"])
        self.assertEqual("closed", self.w.snapshot()["interworld_links"][0]["status"])

    def test_s15_contract_settles_exactly_once(self):
        self.s.emit("ContractRegistered", contract_id="delivery_1", sponsor="organization:city", contractor="organization:union", material="credits", quantity=10)
        paid = self.s.emit("ContractFulfilled", contract_id="delivery_1")
        self.assertEqual(40, self.w.stock("organization:city", "credits"))
        self.assertEqual(10, self.w.stock("organization:union", "credits"))
        retry = self.w.apply(paid["event_id"], "ContractFulfilled", "system", {"contract_id":"delivery_1"}, tick=self.s.tick)
        self.assertTrue(retry["duplicate"])
        with self.assertRaisesRegex(WorldRuleError, "already fulfilled"):
            self.s.emit("ContractFulfilled", contract_id="delivery_1")
        self.assertEqual(40, self.w.stock("organization:city", "credits"))

    def test_s16_cannot_join_as_second_living_character(self):
        with self.assertRaisesRegex(WorldRuleError, "already has living survivor"):
            self.s.emit("CharacterEntered", character_id="a2", account_id="account_a", origin="Civic", location="Civic")

    def test_s17_stale_site_inspection_rejected(self):
        self.move("b1", "Civic", "pump", "road:civic-pump")
        self.s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)
        with self.assertRaisesRegex(WorldRuleError, "stale site version"):
            self.s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)

    def test_s18_remote_repair_rejected_even_with_role(self):
        self.move("b1", "Civic", "pump", "road:civic-pump")
        self.s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)
        with self.assertRaisesRegex(WorldRuleError, "site presence"):
            self.s.emit("SiteRepaired", actor="a1", site_id="pump", expected_version=1, material="steel", quantity=1)
        self.assertEqual("restricted", self.site("pump")["status"])

    def test_s19_item_cannot_be_transferred_remotely(self):
        with self.assertRaisesRegex(WorldRuleError, "receiver not colocated"):
            self.s.emit("ItemTransferred", actor="a1", item_id="notebook_a", to_holder="character:c1", location="Westbank")
        with self.assertRaisesRegex(WorldRuleError, "remote location"):
            self.s.emit("ItemTransferred", actor="a1", item_id="notebook_a", to_holder="organization:city", location="Lab")

    def test_s20_item_follows_authorized_route(self):
        self.move("a1", "Westbank", "Civic", "road:central")
        self.assertEqual("Civic", self.item("notebook_a")["location"])
        with self.assertRaisesRegex(WorldRuleError, "route does not connect"):
            self.move("a1", "Civic", "Forest", "road:civic-lab")

    def test_s21_knowledge_must_be_authored_by_living_character(self):
        with self.assertRaisesRegex(WorldRuleError, "notes belong"):
            self.s.emit("CharacterPrivateNote", actor="b1", character_id="a1", text="steal expertise")
        self.assertEqual("[]", self.c("a1")["private_knowledge"])

    def test_s22_no_negative_stock(self):
        before = self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError, "insufficient stock"):
            self.s.emit("StockTransferred", actor="c1", from_holder="organization:union", to_holder="organization:city", material="steel", quantity=100)
        self.assertEqual(before, self.w.state_hash())

    def test_s23_no_unbounded_region_ticks(self):
        before = self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError, "bounded"):
            self.s.emit("RegionAdvanced", region_id="Southplain", steps=-1)
        self.assertEqual(before, self.w.state_hash())

    def test_s24_no_global_world_reset_event(self):
        with self.assertRaisesRegex(WorldRuleError, "unsupported event type"):
            self.s.emit("ResetMatch", world="Eloden")

    def test_s25_no_distant_global_crime_notice(self):
        self.s.emit("ReportFiled", actor="c1", report_id="witness_1", community="Westbank", claim="Unknown person entered warehouse", subject="unknown", evidence_ref="")
        self.assertEqual(1, len(self.w.snapshot()["reports"]))
        self.assertFalse("global_reputation" in self.w.snapshot())

    def test_s26_no_untrusted_self_promotion_to_inspector(self):
        with self.assertRaisesRegex(WorldRuleError, "trusted setup"):
            self.s.emit("MembershipGranted", actor="c1", org_id="city", character_id="c1", role="inspector")
        self.assertFalse(self.w._has_role("c1", "city", "inspector"))

    def test_s27_item_legal_owner_preserved_after_drop(self):
        self.s.emit("ItemDropped", actor="c1", item_id="scanner_c")
        self.assertEqual("character:c1", self.item("scanner_c")["legal_owner"])
        self.assertEqual("ground", self.item("scanner_c")["custodian"])

    def test_s28_cannot_move_across_obstructed_bridge(self):
        self.setup_bridge_obstruction()
        self.move("a1", "Westbank", "LowerCrossing", "road:lower-west")
        self.move("a1", "LowerCrossing", "Civic", "road:lower-east")
        with self.assertRaisesRegex(WorldRuleError, "route blocked"):
            self.move("a1", "Civic", "Westbank", "road:central")

    def test_s29_repair_requires_role_and_materials(self):
        self.move("b1", "Civic", "pump", "road:civic-pump")
        self.s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)
        with self.assertRaisesRegex(WorldRuleError, "site presence"):
            self.s.emit("SiteRepaired", actor="a1", site_id="pump", expected_version=1, material="steel", quantity=100)
        self.move("a1", "Westbank", "Civic", "road:central")
        self.move("a1", "Civic", "pump", "road:civic-pump")
        with self.assertRaisesRegex(WorldRuleError, "insufficient materials"):
            self.s.emit("SiteRepaired", actor="a1", site_id="pump", expected_version=1, material="steel", quantity=100)

    def test_s30_offline_actor_cannot_act(self):
        self.s.emit("CharacterDisconnected", character_id="c1")
        with self.assertRaisesRegex(WorldRuleError, "not connected"):
            self.s.emit("ItemDropped", actor="c1", item_id="scanner_c")

    def test_s31_rail_route_only_stays_distinct_from_ground_transport(self):
        self.assertEqual(0.263, self.w.shortest_route("Yard", "Apron", rail_only=True)["km"])
        self.assertIsNone(self.w.shortest_route("Westbank", "Civic", rail_only=True))

    def test_s32_simulated_crash_rolls_back_material_transfer_and_ledger(self):
        state = self.w.state_hash()
        n = len(self.w.ledger())
        payload = {"from_holder":"organization:union","to_holder":"organization:city","material":"steel","quantity":4}
        with self.assertRaisesRegex(RuntimeError, "SIMULATED_CRASH"):
            self.w.apply("CRASH_001", "StockTransferred", "c1", payload, tick=self.s.tick+1, crash_before_commit=True)
        self.assertEqual(n, len(self.w.ledger()))
        self.assertEqual(state, self.w.state_hash())
        accepted = self.w.apply("CRASH_001", "StockTransferred", "c1", payload, tick=self.s.tick+1)
        self.assertFalse(accepted["duplicate"])
        self.assertEqual(4, self.w.stock("organization:union", "steel"))
        self.assertEqual(11, self.w.stock("organization:city", "steel"))

    def test_s33_event_id_cannot_be_reused_with_different_payload(self):
        event = self.s.emit("CharacterPrivateNote", actor="a1", character_id="a1", text="yes")
        before = self.w.state_hash()
        with self.assertRaisesRegex(WorldRuleError, "event ID reused"):
            self.w.apply(event["event_id"], "CharacterPrivateNote", "a1", {"character_id":"a1","text":"changed"}, tick=self.s.tick)
        self.assertEqual(before, self.w.state_hash())

    def test_s34_ticks_cannot_move_backward(self):
        with self.assertRaisesRegex(WorldRuleError, "nonmonotonic"):
            self.w.apply("clock-back", "RoadClosed", "system", {"link_id":"Cydren Skygate"}, tick=0)

    def test_s35_public_hospital_not_road_dependent(self):
        self.s.emit("RoadClosed", link_id="Cydren Skygate")
        self.s.emit("RoadClosed", link_id="Orveth Freight Ring")
        self.assertEqual("operational", self.site("hospital")["status"])
        self.s.emit("AccountRegistered", account_id="new_local")
        self.s.emit("CharacterEntered", account_id="new_local", character_id="new_local_1", origin="Eloden local", location="Civic")
        self.assertEqual("active", self.c("new_local_1")["state"])


class DurableReplayTests(unittest.TestCase):
    def test_sqlite_reopen_and_jsonl_replay_exact_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            p = d / "live.sqlite3"
            with World(p) as world:
                s = seed_world(world)
                s.emit("CharacterDied", character_id="a1", reason="accident")
                expected = world.state_hash()
                world.export_jsonl(d / "trace.jsonl")
            with World(p) as reopened:
                self.assertEqual(expected, reopened.state_hash())
                self.assertEqual("deceased", dict(reopened._one("characters", "character_id", "a1"))["state"])
                self.assertEqual(len(reopened.ledger()), reopened.verify_chain()["verified_events"])
            with World.replay_jsonl(d / "trace.jsonl") as replayed:
                self.assertEqual(expected, replayed.state_hash())

    def test_export_fails_for_manually_modified_ledger(self):
        with World() as w:
            seed_world(w)
            w.db.execute("UPDATE ledger SET payload=? WHERE seq=1", ('{"account_id":"forged"}',))
            with self.assertRaisesRegex(WorldRuleError, "broken hash"):
                w.verify_chain()

    def test_materialized_site_tamper_detected_by_audit(self):
        with World() as w:
            seed_world(w)
            w.db.execute("UPDATE sites SET status='failed' WHERE site_id='hospital'")
            # The ledger remains hash-consistent but materialized state diverges.
            w.verify_chain()
            with self.assertRaisesRegex(WorldRuleError, "materialized state differs"):
                w.audit_state()

    def test_materialized_inventory_tamper_detected_by_audit(self):
        with World() as w:
            seed_world(w)
            w.db.execute("UPDATE stocks SET quantity=99999 WHERE holder='organization:city' AND material='steel'")
            with self.assertRaisesRegex(WorldRuleError, "materialized state differs"):
                w.audit_state()

    def test_tampered_jsonl_is_rejected_during_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "events.jsonl"
            with World() as w:
                seed_world(w)
                w.export_jsonl(p)
            lines = p.read_text().splitlines()
            first = json.loads(lines[0])
            first["payload"]["account_id"] = "forged"
            lines[0] = json.dumps(first)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(WorldRuleError, "tampered replay"):
                World.replay_jsonl(p)

    def test_determinism_of_two_equivalent_replays(self):
        with World() as a, World() as b:
            seed_world(a)
            seed_world(b)
            self.assertEqual(a.state_hash(), b.state_hash())
            self.assertEqual(a.verify_chain()["last_hash"], b.verify_chain()["last_hash"])

    def test_independent_sqlite_writers_conflicting_repair_only_one_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "shared.sqlite3"
            with World(p) as w:
                s = seed_world(w)
                s.emit("CharacterMoved", actor="a1", character_id="a1", route_id="road:central", **{"from":"Westbank", "to":"Civic"})
                s.emit("CharacterMoved", actor="a1", character_id="a1", route_id="road:civic-pump", **{"from":"Civic", "to":"pump"})
                s.emit("CharacterMoved", actor="b1", character_id="b1", route_id="road:civic-pump", **{"from":"Civic", "to":"pump"})
                s.emit("StockTransferred", actor="c1", from_holder="organization:union", to_holder="organization:city", material="steel", quantity=8)
                s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)
                tick = s.tick + 1
            barrier = threading.Barrier(2)
            results = []
            lock = threading.Lock()
            def repair_worker(idx):
                with World(p) as w:
                    barrier.wait(timeout=10)
                    try:
                        w.apply(f"writer_{idx}", "SiteRepaired", "a1", {"site_id":"pump", "expected_version":1, "material":"steel", "quantity":10}, tick=tick)
                        result = "accepted"
                    except WorldRuleError as ex:
                        result = str(ex)
                    with lock:
                        results.append(result)
            th = [threading.Thread(target=repair_worker, args=(i,)) for i in (1,2)]
            for x in th: x.start()
            for x in th: x.join(timeout=15)
            self.assertTrue(all(not x.is_alive() for x in th), "concurrent writers stalled")
            self.assertEqual(1, results.count("accepted"), results)
            self.assertTrue(any("stale site version" in r for r in results), results)
            with World(p) as w:
                self.assertEqual(5, w.stock("organization:city", "steel"))
                self.assertEqual("operational", dict(w._one("sites", "site_id", "pump"))["status"])
                self.assertEqual(2, dict(w._one("sites", "site_id", "pump"))["version"])
                w.verify_chain()

    def test_fresh_demo_export_matches_replayed_world(self):
        with tempfile.TemporaryDirectory() as directory:
            rep = run_demo(directory)
            self.assertEqual("PASS", rep["status"])
            self.assertEqual(rep["state_sha256"], rep["replay_state_sha256"])
            self.assertEqual(2.017, rep["bridge_route_open_km"])
            self.assertEqual(6.61, rep["bridge_route_closed_km"])
            self.assertEqual("operational", rep["hospital_status"])
            self.assertGreater(rep["events"], 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
