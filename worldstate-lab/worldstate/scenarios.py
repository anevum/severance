"""Offline deterministic fixtures and a reproducible narrated test run."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import World, WorldRuleError, canonical


class Fixture:
    def __init__(self, world: World) -> None:
        self.world = world
        self.tick = 0
        self.number = 0

    def emit(self, event_type: str, actor: str = "system", **payload: Any) -> dict:
        self.tick += 1
        self.number += 1
        return self.world.apply(f"E{self.number:05d}", event_type, actor, payload, tick=self.tick)


def seed_world(world: World) -> Fixture:
    s = Fixture(world)
    for id_ in ("account_a", "account_b", "account_c", "account_d", "account_e"):
        s.emit("AccountRegistered", account_id=id_)
    for name, org in (("Orrel Civic Trust", "city"), ("Westbank Repair Union", "union")):
        s.emit("OrganizationRegistered", org_id=org, name=name)
    for acc, char, origin, location in (
        ("account_a", "a1", "Orrel Westbank", "Westbank"),
        ("account_b", "b1", "Orrel Crossing", "Civic"),
        ("account_c", "c1", "Westbank repair district", "Camp"),
        ("account_d", "d1", "Southplain settlements", "Forest"),
        ("account_e", "e1", "Orrel Crossing", "Civic"),
    ):
        s.emit("CharacterEntered", account_id=acc, character_id=char, origin=origin, location=location, occupation="resident")
    for org, char, role in (
        ("city", "a1", "maintainer"), ("city", "b1", "inspector"),
        ("union", "c1", "quartermaster"), ("union", "d1", "maintainer"),
    ):
        s.emit("MembershipGranted", org_id=org, character_id=char, role=role)
    for sid, name, kind, status, critical in (
        ("bridge", "Central Road Bridge", "bridge", "operational", True),
        ("pump", "Orrel water pump", "water", "restricted", True),
        ("hospital", "Regional General Hospital", "medical", "operational", True),
        ("dam", "Northweir Dam", "dam", "operational", True),
        ("repair_shop", "Westbank Repair Workshop", "workshop", "operational", False),
    ):
        s.emit("SiteRegistered", site_id=sid, name=name, kind=kind, status=status, critical=critical, owner_org="city")
    for rid, u, v, km, guarded in (
        ("road:central", "Westbank", "Civic", 2.017, "bridge"),
        ("road:lower-west", "Westbank", "LowerCrossing", 3.200, None),
        ("road:lower-east", "LowerCrossing", "Civic", 3.410, None),
        ("road:civic-bridge", "Civic", "bridge", 1.0085, None),
        ("road:bridge-westbank", "bridge", "Westbank", 1.0085, "bridge"),
        ("road:civic-lab", "Civic", "Lab", 2.014, None),
        ("road:civic-pump", "Civic", "pump", 0.250, None),
        ("road:civic-hospital", "Civic", "hospital", 0.700, None),
        ("road:civic-camp", "Civic", "Camp", 1.000, None),
        ("road:camp-forest", "Camp", "Forest", 2.000, None),
        ("road:civic-dam", "Civic", "dam", 4.000, None),
        ("rail:yard-apron", "Yard", "Apron", 0.263, None),
        ("rail:yard-south", "Yard", "SouthRail", 2.459, None),
    ):
        s.emit("RouteRegistered", route_id=rid, point_a=u, point_b=v, km=km, guarded_by_site=guarded)
    for link in ("Cydren Skygate", "Orveth Freight Ring"):
        s.emit("RoadRegistered", link_id=link, status="open")
    for holder, material, qty in (
        ("organization:city", "steel", 7),
        ("organization:union", "steel", 8),
        ("organization:city", "credits", 50),
        ("character:b1", "field_kit", 2),
        ("character:c1", "barrier_kit", 2),
    ):
        s.emit("StockProvisioned", holder=holder, material=material, quantity=qty)
    s.emit("ItemRegistered", item_id="notebook_a", name="Field notebook", custodian="character:a1", location="Westbank")
    s.emit("ItemRegistered", item_id="scanner_c", name="Survey scanner", custodian="character:c1", location="Camp")
    s.emit("AgentRegistered", agent_id="custodian_01", name="Survey custodian", kind="biohybrid platform", energy=3, nutrients=2)
    s.emit("RegionRegistered", region_id="Southplain", population=1000, food=1000, water=1000, food_production=12, water_production=13)
    return s


def run_demo(folder: str | Path) -> dict:
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    db_path = target / "demo_world.sqlite3"
    if db_path.exists():
        db_path.unlink()
    for extra in ("-wal", "-shm"):
        transient = Path(str(db_path) + extra)
        if transient.exists():
            transient.unlink()
    with World(db_path) as world:
        s = seed_world(world)
        initial_route = world.shortest_route("Westbank", "Civic")
        s.emit("CharacterPrivateNote", actor="a1", character_id="a1", text="Independent calibration discrepancy observed")
        s.emit("CharacterMoved", actor="a1", character_id="a1", route_id="road:central", **{"from": "Westbank", "to": "Civic"})
        s.emit("StockTransferred", actor="c1", from_holder="organization:union", to_holder="organization:city", material="steel", quantity=8)
        s.emit("CharacterMoved", actor="b1", character_id="b1", route_id="road:civic-pump", **{"from": "Civic", "to": "pump"})
        s.emit("CharacterMoved", actor="a1", character_id="a1", route_id="road:civic-pump", **{"from": "Civic", "to": "pump"})
        s.emit("SiteInspected", actor="b1", site_id="pump", expected_version=0)
        repaired = s.emit("SiteRepaired", actor="a1", site_id="pump", expected_version=1, material="steel", quantity=10)
        repeat = world.apply(repaired["event_id"], "SiteRepaired", "a1", {"site_id": "pump", "expected_version": 1, "material": "steel", "quantity": 10}, tick=s.tick)
        s.emit("EvidenceRecorded", actor="a1", record_id="physical_gauge", summary="Analog pressure differs from archived automated gauge", source="instrument gallery", classification="private")
        s.emit("EvidencePublished", actor="a1", record_id="physical_gauge")
        s.emit("CharacterMoved", actor="c1", character_id="c1", route_id="road:civic-camp", **{"from": "Camp", "to": "Civic"})
        s.emit("CharacterMoved", actor="c1", character_id="c1", route_id="road:civic-bridge", **{"from": "Civic", "to": "bridge"})
        s.emit("SiteObstructed", actor="c1", site_id="bridge", expected_version=0)
        alternate_route = world.shortest_route("Westbank", "Civic")
        s.emit("CharacterInjured", character_id="d1", severity=95)
        s.emit("CharacterDied", character_id="d1", reason="irrecoverable trauma")
        s.emit("CharacterEntered", account_id="account_d", character_id="d2", origin="Orrel Crossing", location="Civic", occupation="farm courier")
        s.emit("RegionAdvanced", region_id="Southplain", steps=7)
        s.emit("AgentAdvanced", agent_id="custodian_01", energy_used=2, nutrients_used=1)
        s.emit("RoadClosed", link_id="Cydren Skygate")
        s.emit("RoadClosed", link_id="Orveth Freight Ring")
        report = {
            "status": "PASS",
            "description": "Offline world-state event-replay demonstration; not a playable MMO",
            "events": len(world.ledger()),
            "bridge_route_open_km": initial_route["km"],
            "bridge_route_closed_km": alternate_route["km"],
            "pump_status": dict(world._one("sites", "site_id", "pump"))["status"],
            "pump_version": dict(world._one("sites", "site_id", "pump"))["version"],
            "city_steel_remaining": world.stock("organization:city", "steel"),
            "duplicate_repair_rejected_as_new": repeat["duplicate"],
            "old_character_state": dict(world._one("characters", "character_id", "d1"))["state"],
            "new_character_state": dict(world._one("characters", "character_id", "d2"))["state"],
            "both_interworld_roads_closed": all(v["status"] == "closed" for v in world.snapshot()["interworld_links"]),
            "hospital_status": dict(world._one("sites", "site_id", "hospital"))["status"],
            "state_sha256": world.state_hash(),
            "ledger_verification": world.verify_chain(),
            "state_audit": world.audit_state(),
        }
        (target / "demo_snapshot.json").write_text(json.dumps(world.snapshot(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        world.export_jsonl(target / "demo_events.jsonl")
    with World.replay_jsonl(target / "demo_events.jsonl") as replay:
        report["replay_state_sha256"] = replay.state_hash()
        if report["replay_state_sha256"] != report["state_sha256"]:
            raise WorldRuleError("demo replay mismatch")
    (target / "demo_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
