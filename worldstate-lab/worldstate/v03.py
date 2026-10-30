"""V0.3 offline extension: event versions, scheduled work, consent and multi-stop cargo.

Not a network API, clinical authorization system, or production transport engine.
V0.1/V0.2 event payloads and hash encoding are never rewritten.
"""
from __future__ import annotations

import json
import math
from typing import Any

V3_KINDS = frozenset({
    "TaskPlanned", "TaskTriggered", "TaskCanceled", "EvidenceSubjectBound",
    "EvidenceAccessGranted", "EvidenceAccessRevoked", "EvidenceViewed",
    "ConvoyDispatched", "ConvoyLegArrived", "ConvoyLegDeparted", "ConvoyRerouted",
})

V3_SCHEMAS = (
    """CREATE TABLE IF NOT EXISTS worldstate_schema (
      id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL CHECK(revision>=3),
      created_from INTEGER NOT NULL, description TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS scheduled_tasks (
      task_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES medical_cases(case_id),
      action TEXT NOT NULL CHECK(action='medical_deadline'),
      due_tick INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','executed','skipped','canceled')),
      completed_tick INTEGER)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS one_medical_deadline_task ON scheduled_tasks(case_id,action)""",
    """CREATE TABLE IF NOT EXISTS evidence_subjects (
      record_id TEXT PRIMARY KEY REFERENCES evidence(record_id),
      subject_id TEXT NOT NULL REFERENCES characters(character_id))""",
    """CREATE TABLE IF NOT EXISTS evidence_grants (
      grant_id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES evidence(record_id),
      grantor TEXT NOT NULL REFERENCES characters(character_id),
      grantee TEXT NOT NULL REFERENCES characters(character_id),
      scope TEXT NOT NULL CHECK(scope='read'),
      granted_tick INTEGER NOT NULL, expires_tick INTEGER NOT NULL,
      revoked_tick INTEGER)""",
    """CREATE TABLE IF NOT EXISTS evidence_reads (
      read_id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES evidence(record_id),
      viewer TEXT NOT NULL REFERENCES characters(character_id), read_tick INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS convoys (
      convoy_id TEXT PRIMARY KEY, carrier_id TEXT NOT NULL REFERENCES carriers(carrier_id),
      source_holder TEXT NOT NULL, destination_holder TEXT NOT NULL,
      material TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0),
      route_ids TEXT NOT NULL, next_leg INTEGER NOT NULL,
      location TEXT NOT NULL, destination TEXT NOT NULL,
      eta_tick INTEGER, status TEXT NOT NULL CHECK(status IN ('transit','staged','delivered')),
      departed_tick INTEGER NOT NULL, last_update_tick INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS convoy_hops (
      convoy_id TEXT NOT NULL REFERENCES convoys(convoy_id), leg INTEGER NOT NULL,
      route_id TEXT NOT NULL REFERENCES routes(route_id), origin TEXT NOT NULL,
      destination TEXT NOT NULL, depart_tick INTEGER NOT NULL,
      arrival_tick INTEGER NOT NULL, status TEXT NOT NULL CHECK(status='arrived'),
      PRIMARY KEY(convoy_id,leg))""",
)

V3_TABLES = (
    "scheduled_tasks", "evidence_subjects", "evidence_grants", "evidence_reads", "convoys", "convoy_hops"
)


def migrate_v3(db: Any, *, simulate_failure: bool = False) -> None:
    """Rollback-safe local schema migration. PRAGMA user_version=2 remains a legacy ABI marker.

    The authoritative extension revision is worldstate_schema.revision=3. This
    deliberate distinction avoids changing the unmodified V0.2 test contract.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] > 2:
            raise ValueError("unknown incompatible base schema")
        for index, statement in enumerate(V3_SCHEMAS):
            db.execute(statement)
            if simulate_failure and index == 3:
                raise RuntimeError("SIMULATED_MIGRATION_FAILURE")
        db.execute("INSERT OR IGNORE INTO worldstate_schema VALUES(1,3,2,'additive V0.3 offline extensions')")
        row = db.execute("SELECT revision,created_from FROM worldstate_schema WHERE id=1").fetchone()
        if tuple(row) != (3, 2):
            raise ValueError("unsupported worldstate extension revision")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def _valid_version(world: Any, p: dict) -> None:
    world._require(p.get("__v") == 3 and type(p["__v"]) is int, "V0.3 requires hashed __v=3 payload")


def _positive(world: Any, num: Any, label: str, max_value: int = 1_000_000) -> int:
    world._require(type(num) is int and 0 < num <= max_value, label)
    return num


def _route(world: Any, route_id: str, current: str) -> tuple[str, float]:
    from .expansion import _open_route
    edge = world.db.execute("SELECT * FROM routes WHERE route_id=?", (route_id,)).fetchone()
    world._require(edge is not None and current in (edge["point_a"], edge["point_b"]), "disconnected convoy itinerary")
    nxt = edge["point_b"] if edge["point_a"] == current else edge["point_a"]
    _open_route(world, route_id, current, nxt)
    return nxt, edge["km"]


def _validate_plan(world: Any, origin: str, destination: str, route_ids: Any) -> tuple[list[str], float]:
    world._require(isinstance(route_ids, list) and 2 <= len(route_ids) <= 8 and
                   all(isinstance(x, str) and x for x in route_ids), "invalid multi-stop itinerary")
    current, visited, distance = origin, {origin}, 0.0
    for route_id in route_ids:
        current, km = _route(world, route_id, current)
        world._require(current not in visited, "multi-stop itinerary contains cycle")
        visited.add(current)
        distance += km
    world._require(current == destination, "multi-stop itinerary does not reach destination")
    return route_ids, distance


def _convoy(world: Any, convoy_id: str):
    row = world.db.execute("SELECT * FROM convoys WHERE convoy_id=?", (convoy_id,)).fetchone()
    world._require(row is not None, "unknown convoy")
    return row


def _destination(world: Any, dest: str) -> str:
    db = world.db
    if dest.startswith("organization:"):
        world._check_holder(dest)
        row = db.execute("SELECT location FROM depots WHERE holder=?", (dest,)).fetchone()
        world._require(row is not None, "unregistered destination depot")
        return row["location"]
    if dest.startswith("region:"):
        reg = dest.split(":", 1)[1]
        world._one("regions", "region_id", reg)
        row = db.execute("SELECT location FROM region_hubs WHERE region_id=?", (reg,)).fetchone()
        world._require(row is not None, "unregistered region hub")
        return row["location"]
    world._require(False, "invalid destination holder")
    raise AssertionError("unreachable")


def _evidence_access(world: Any, record_id: str, viewer: str, tick: int) -> bool:
    ev = world._one("evidence", "record_id", record_id)
    if viewer == ev["author"] or (ev["published"] and ev["classification"] != "clinical"):
        return True
    if ev["classification"] == "clinical":
        own = world.db.execute("SELECT subject_id FROM evidence_subjects WHERE record_id=?", (record_id,)).fetchone()
        if own is not None and own["subject_id"] == viewer:
            return True
    return world.db.execute(
        "SELECT 1 FROM evidence_grants WHERE record_id=? AND grantee=? AND scope='read' "
        "AND revoked_tick IS NULL AND granted_tick<=? AND expires_tick>=? LIMIT 1",
        (record_id, viewer, tick, tick),
    ).fetchone() is not None


def due_tasks(world: Any, now_tick: int, *, limit: int = 50) -> list[str]:
    """Deterministic query; caller must invoke World.run_due to commit outcomes."""
    _positive(world, limit, "invalid scheduler batch size", 100)
    world._require(type(now_tick) is int and now_tick >= 0, "invalid scheduler time")
    return [x["task_id"] for x in world.db.execute(
        "SELECT task_id FROM scheduled_tasks WHERE state='pending' AND due_tick<=? "
        "ORDER BY due_tick,task_id LIMIT ?", (now_tick, limit)
    )]


def dispatch_v3(world: Any, kind: str, actor: str, p: dict, tick: int) -> bool:
    if kind not in V3_KINDS:
        return False
    _valid_version(world, p)
    db = world.db
    if kind == "TaskPlanned":
        world._system(actor)
        case = db.execute("SELECT * FROM medical_cases WHERE case_id=?", (p["case_id"],)).fetchone()
        world._require(case is not None and case["state"] == "open", "open medical case required")
        world._require(p["due_tick"] == case["deadline_tick"] + 1 and tick <= p["due_tick"],
                       "deadline task must match the medical deadline")
        db.execute("INSERT INTO scheduled_tasks VALUES(?,?,?,?,'pending',NULL)",
                   (p["task_id"], case["case_id"], "medical_deadline", p["due_tick"]))
    elif kind == "TaskCanceled":
        world._system(actor)
        row = db.execute("SELECT state FROM scheduled_tasks WHERE task_id=?", (p["task_id"],)).fetchone()
        world._require(row is not None and row["state"] == "pending", "task is not pending")
        db.execute("UPDATE scheduled_tasks SET state='canceled',completed_tick=? WHERE task_id=?", (tick, p["task_id"]))
    elif kind == "TaskTriggered":
        world._system(actor)
        task = db.execute("SELECT * FROM scheduled_tasks WHERE task_id=?", (p["task_id"],)).fetchone()
        world._require(task is not None and task["state"] == "pending", "task already finished or unknown")
        world._require(tick >= task["due_tick"], "task not yet due")
        case = db.execute("SELECT * FROM medical_cases WHERE case_id=?", (task["case_id"],)).fetchone()
        if case is not None and case["state"] == "open":
            world._dispatch("MedicalCaseExpired", "system", {"case_id": task["case_id"]}, tick)
            state = "executed"
        else:
            state = "skipped"  # stabilized / dead / recovered; no repeated fatal action
        db.execute("UPDATE scheduled_tasks SET state=?,completed_tick=? WHERE task_id=?", (state, tick, task["task_id"]))
    elif kind == "EvidenceSubjectBound":
        world._system(actor)
        ev = world._one("evidence", "record_id", p["record_id"])
        world._require(ev["classification"] == "clinical", "only clinical evidence has a patient subject")
        world._one("characters", "character_id", p["subject_id"])
        db.execute("INSERT INTO evidence_subjects VALUES(?,?)", (p["record_id"], p["subject_id"]))
    elif kind == "EvidenceAccessGranted":
        subject = world._active(actor)
        ev = world._one("evidence", "record_id", p["record_id"])
        grantee = world._one("characters", "character_id", p["grantee"])
        world._require(grantee["state"] != "deceased" and actor != p["grantee"], "invalid recipient")
        world._require(p["scope"] == "read", "grant is read-only")
        world._require(type(p["expires_tick"]) is int, "invalid evidence grant expiry")
        duration = _positive(world, p["expires_tick"] - tick, "grant expiry must be in the future", 100000)
        if ev["classification"] == "clinical":
            row = db.execute("SELECT subject_id FROM evidence_subjects WHERE record_id=?", (p["record_id"],)).fetchone()
            world._require(row is not None and row["subject_id"] == actor, "clinical subject consent required")
        else:
            world._require(ev["author"] == actor, "only the evidence author can grant access")
        db.execute("INSERT INTO evidence_grants VALUES(?,?,?,?,?,?,?,NULL)",
                   (p["grant_id"], p["record_id"], actor, p["grantee"], "read", tick, tick + duration))
    elif kind == "EvidenceAccessRevoked":
        world._active(actor)
        grant = db.execute("SELECT * FROM evidence_grants WHERE grant_id=?", (p["grant_id"],)).fetchone()
        world._require(grant is not None and grant["grantor"] == actor and grant["revoked_tick"] is None,
                       "only the grantor may revoke an active grant")
        db.execute("UPDATE evidence_grants SET revoked_tick=? WHERE grant_id=?", (tick, p["grant_id"]))
    elif kind == "EvidenceViewed":
        world._active(actor)
        world._require(_evidence_access(world, p["record_id"], actor, tick), "evidence access denied")
        db.execute("INSERT INTO evidence_reads VALUES(?,?,?,?)", (p["read_id"], p["record_id"], actor, tick))
    elif kind == "ConvoyDispatched":
        courier = world._active(actor)
        src, dest = p["source_holder"], p["destination_holder"]
        world._require(src.startswith("organization:") and src != dest, "invalid cargo source or destination")
        depot = db.execute("SELECT location FROM depots WHERE holder=?", (src,)).fetchone()
        world._require(depot is not None, "unregistered source depot")
        world._require(world._holder_authorized(actor, src) and courier["location"] == depot["location"],
                       "quartermaster at source required")
        final_location = _destination(world, dest)
        world._require(not dest.startswith("region:") or p["material"] in ("food", "water"),
                       "region only accepts food/water")
        plan, _ = _validate_plan(world, depot["location"], final_location, p["route_ids"])
        carrier = db.execute("SELECT * FROM carriers WHERE carrier_id=?", (p["carrier_id"],)).fetchone()
        world._require(carrier is not None and carrier["owner_org"] == src.split(":", 1)[1] and
                       carrier["location"] == depot["location"] and carrier["status"] == "ready", "carrier unavailable")
        qty = _positive(world, p["quantity"], "invalid cargo quantity")
        world._require(qty <= carrier["capacity"] and world._stock(src, p["material"]) >= qty,
                       "capacity or source stock insufficient")
        nxt, km = _route(world, plan[0], depot["location"])
        fuel_cost = max(1, math.ceil(km * 10))
        world._require(carrier["fuel"] >= fuel_cost, "insufficient initial-leg fuel")
        eta = tick + max(1, math.ceil(km * 3))
        world._set_stock(src, p["material"], world._stock(src, p["material"]) - qty)
        db.execute("UPDATE carriers SET status='transit',fuel=fuel-? WHERE carrier_id=?", (fuel_cost, p["carrier_id"]))
        db.execute("INSERT INTO convoys VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (p["convoy_id"], p["carrier_id"], src, dest, p["material"], qty, json.dumps(plan),
                    0, depot["location"], final_location, eta, "transit", tick, tick))
    elif kind == "ConvoyLegArrived":
        world._system(actor)
        c = _convoy(world, p["convoy_id"])
        world._require(c["status"] == "transit" and tick >= c["eta_tick"], "convoy leg not ready")
        route_ids = json.loads(c["route_ids"])
        world._require(c["next_leg"] < len(route_ids), "convoy route exhausted")
        nxt, km = _route(world, route_ids[c["next_leg"]], c["location"])
        carrier = db.execute("SELECT * FROM carriers WHERE carrier_id=?", (c["carrier_id"],)).fetchone()
        world._require(carrier is not None and carrier["status"] == "transit" and carrier["location"] == c["location"],
                       "carrier position differs from convoy")
        db.execute("INSERT INTO convoy_hops VALUES(?,?,?,?,?,?,?,'arrived')",
                   (c["convoy_id"], c["next_leg"], route_ids[c["next_leg"]], c["location"], nxt,
                    c["last_update_tick"], tick))
        final = (c["next_leg"] + 1 == len(route_ids))
        if final:
            world._require(nxt == c["destination"], "convoy final destination mismatch")
            dest = c["destination_holder"]
            if dest.startswith("organization:"):
                world._set_stock(dest, c["material"], world._stock(dest, c["material"]) + c["quantity"])
            else:
                region = dest.split(":", 1)[1]
                db.execute(f'UPDATE regions SET {c["material"]}={c["material"]}+? WHERE region_id=?',
                           (c["quantity"], region))
            db.execute("UPDATE carriers SET status='ready',location=? WHERE carrier_id=?", (nxt, c["carrier_id"]))
            db.execute("UPDATE convoys SET next_leg=next_leg+1,location=?,status='delivered',eta_tick=NULL,last_update_tick=? "
                       "WHERE convoy_id=?", (nxt, tick, c["convoy_id"]))
        else:
            db.execute("UPDATE carriers SET location=? WHERE carrier_id=?", (nxt, c["carrier_id"]))
            db.execute("UPDATE convoys SET next_leg=next_leg+1,location=?,status='staged',eta_tick=NULL,last_update_tick=? "
                       "WHERE convoy_id=?", (nxt, tick, c["convoy_id"]))
    elif kind == "ConvoyLegDeparted":
        world._system(actor)
        c = _convoy(world, p["convoy_id"])
        world._require(c["status"] == "staged", "convoy not staged")
        plan = json.loads(c["route_ids"])
        world._require(c["next_leg"] < len(plan), "convoy already at destination")
        nxt, km = _route(world, plan[c["next_leg"]], c["location"])
        carrier = db.execute("SELECT * FROM carriers WHERE carrier_id=?", (c["carrier_id"],)).fetchone()
        world._require(carrier is not None and carrier["status"] == "transit" and carrier["location"] == c["location"],
                       "carrier is not staged at location")
        fuel = max(1, math.ceil(km * 10))
        world._require(carrier["fuel"] >= fuel, "insufficient next-leg fuel")
        db.execute("UPDATE carriers SET fuel=fuel-? WHERE carrier_id=?", (fuel, c["carrier_id"]))
        db.execute("UPDATE convoys SET status='transit',eta_tick=?,last_update_tick=? WHERE convoy_id=?",
                   (tick + max(1, math.ceil(km * 3)), tick, c["convoy_id"]))
    elif kind == "ConvoyRerouted":
        world._system(actor)
        c = _convoy(world, p["convoy_id"])
        world._require(c["status"] in ("transit", "staged"), "delivered convoy cannot reroute")
        if c["status"] == "transit":
            current = json.loads(c["route_ids"])[c["next_leg"]]
            row = db.execute("SELECT guarded_by_site FROM routes WHERE route_id=?", (current,)).fetchone()
            world._require(row is not None and row["guarded_by_site"] and
                           world._one("sites", "site_id", row["guarded_by_site"])["status"] != "operational",
                           "active convoy route must be blocked to reroute")
        new_plan, _ = _validate_plan(world, c["location"], c["destination"], p["route_ids"])
        old = json.loads(c["route_ids"])
        prefix = old[:c["next_leg"]]
        combined = prefix + new_plan
        world._require(len(combined) <= 8, "convoy total route exceeds hop limit")
        db.execute("UPDATE convoys SET route_ids=?,status='staged',eta_tick=NULL,last_update_tick=? WHERE convoy_id=?",
                   (json.dumps(combined), tick, c["convoy_id"]))
        # Burnt fuel on the aborted leg is not restored; no credits or cargo teleport.
    return True
