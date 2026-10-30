"""Severance world-state lab: deterministic, transactional offline event simulation.

THIS IS NOT A MULTIPLAYER SERVER, AUTHENTICATION SERVICE, OR GAME ENGINE.
No biological procedure or confidential novel lore is encoded here.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .expansion import EXPANSION_SCHEMA, EXTRA_TABLES, dispatch_expanded
from .v03 import V3_TABLES, V3_KINDS, migrate_v3, dispatch_v3, due_tasks, _evidence_access


class WorldRuleError(ValueError):
    """An event is inconsistent with the simulated world rules."""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS accounts (
 account_id TEXT PRIMARY KEY, sanctioned INTEGER NOT NULL DEFAULT 0 CHECK(sanctioned IN (0,1))
);
CREATE TABLE IF NOT EXISTS characters (
 character_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(account_id),
 origin TEXT NOT NULL, occupation TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active',
 location TEXT NOT NULL, health INTEGER NOT NULL DEFAULT 100 CHECK(health BETWEEN 0 AND 100),
 connected INTEGER NOT NULL DEFAULT 1 CHECK(connected IN (0,1)),
 private_knowledge TEXT NOT NULL DEFAULT '[]', version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS organizations (
 org_id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
 org_id TEXT NOT NULL REFERENCES organizations(org_id),
 character_id TEXT NOT NULL REFERENCES characters(character_id), role TEXT NOT NULL,
 PRIMARY KEY(org_id, character_id, role)
);
CREATE TABLE IF NOT EXISTS sites (
 site_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 owner_org TEXT NOT NULL REFERENCES organizations(org_id),
 status TEXT NOT NULL CHECK(status IN ('operational','restricted','failed','obstructed')),
 version INTEGER NOT NULL DEFAULT 0, inspected INTEGER NOT NULL DEFAULT 0,
 critical INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS stocks (
 holder TEXT NOT NULL, material TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity >= 0),
 PRIMARY KEY(holder,material)
);
CREATE TABLE IF NOT EXISTS items (
 item_id TEXT PRIMARY KEY, name TEXT NOT NULL,
 custodian TEXT NOT NULL, legal_owner TEXT NOT NULL, location TEXT NOT NULL,
 disputed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS evidence (
 record_id TEXT PRIMARY KEY, author TEXT NOT NULL REFERENCES characters(character_id),
 summary TEXT NOT NULL, source TEXT NOT NULL, classification TEXT NOT NULL
 CHECK(classification IN ('public','private','clinical')),
 published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1))
);
CREATE TABLE IF NOT EXISTS reports (
 report_id TEXT PRIMARY KEY, reporter TEXT NOT NULL REFERENCES characters(character_id),
 community TEXT NOT NULL, claim TEXT NOT NULL, subject TEXT NOT NULL, evidence_ref TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
 agent_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 energy INTEGER NOT NULL CHECK(energy >= 0), nutrients INTEGER NOT NULL CHECK(nutrients >= 0),
 status TEXT NOT NULL CHECK(status IN ('active','dormant'))
);
CREATE TABLE IF NOT EXISTS routes (
 route_id TEXT PRIMARY KEY, point_a TEXT NOT NULL, point_b TEXT NOT NULL,
 km REAL NOT NULL CHECK(km > 0), guarded_by_site TEXT REFERENCES sites(site_id)
);
CREATE TABLE IF NOT EXISTS interworld_links (
 link_id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('open','closed'))
);
CREATE TABLE IF NOT EXISTS contracts (
 contract_id TEXT PRIMARY KEY, sponsor TEXT NOT NULL, contractor TEXT NOT NULL,
 compensation_material TEXT NOT NULL, compensation_quantity INTEGER NOT NULL CHECK(compensation_quantity > 0),
 state TEXT NOT NULL CHECK(state IN ('open','fulfilled'))
);
CREATE TABLE IF NOT EXISTS regions (
 region_id TEXT PRIMARY KEY, population INTEGER NOT NULL CHECK(population >= 0),
 food INTEGER NOT NULL CHECK(food >= 0), water INTEGER NOT NULL CHECK(water >= 0),
 food_production INTEGER NOT NULL CHECK(food_production >= 0),
 water_production INTEGER NOT NULL CHECK(water_production >= 0), last_tick INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
 seq INTEGER PRIMARY KEY AUTOINCREMENT,
 event_id TEXT NOT NULL UNIQUE, tick INTEGER NOT NULL,
 actor TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
 prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL
);
"""

TABLES = (
    "accounts", "characters", "organizations", "memberships", "sites", "stocks",
    "items", "evidence", "reports", "agents", "routes", "interworld_links", "contracts", "regions"
) + EXTRA_TABLES + V3_TABLES


class World:
    """Single-writer logical authority with SQLite BEGIN IMMEDIATE and idempotent events.

    For offline experiments only: the special actor 'system' is trusted by this API,
    NOT cryptographically authenticated. Do not expose apply() to untrusted clients.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.path = str(db_path)
        self.db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 8000")
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")
            self.db.execute("PRAGMA synchronous = FULL")
        self.db.executescript(SCHEMA + EXPANSION_SCHEMA)
        # Additive V0.2 schema; legacy event rows remain replayable as written.
        self.db.execute("PRAGMA user_version=2")
        try:
            migrate_v3(self.db)
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "World":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _one(self, table: str, column: str, value: str) -> sqlite3.Row:
        if table not in TABLES:
            raise WorldRuleError("invalid table")
        if column not in {"account_id", "character_id", "org_id", "site_id", "item_id", "record_id", "agent_id", "link_id", "contract_id", "region_id"}:
            raise WorldRuleError("invalid lookup")
        row = self.db.execute(f"SELECT * FROM {table} WHERE {column}=?", (value,)).fetchone()
        if row is None:
            raise WorldRuleError(f"unknown {table}:{value}")
        return row

    def _require(self, condition: bool, reason: str) -> None:
        if not condition:
            raise WorldRuleError(reason)

    def _system(self, actor: str) -> None:
        self._require(actor == "system", "requires trusted setup authority")

    def _active(self, actor: str) -> sqlite3.Row:
        ch = self._one("characters", "character_id", actor)
        self._require(ch["state"] != "deceased", "dead characters cannot act")
        self._require(self._one("accounts", "account_id", ch["account_id"])["sanctioned"] == 0, "account sanctioned")
        self._require(ch["connected"] == 1, "actor not connected")
        self._require(ch["state"] in ("active", "injured", "stabilized", "rehabilitating"), "actor cannot take action")
        return ch

    def _has_role(self, character: str, org: str, role: str) -> bool:
        row = self.db.execute("SELECT 1 FROM memberships WHERE org_id=? AND character_id=? AND role=?", (org, character, role)).fetchone()
        return row is not None

    def _stock(self, holder: str, material: str) -> int:
        row = self.db.execute("SELECT quantity FROM stocks WHERE holder=? AND material=?", (holder, material)).fetchone()
        return int(row[0]) if row else 0

    def stock(self, holder: str, material: str) -> int:
        return self._stock(holder, material)

    def _set_stock(self, holder: str, material: str, qty: int) -> None:
        self._require(isinstance(qty, int) and qty >= 0, "negative stock")
        self.db.execute(
            "INSERT INTO stocks(holder,material,quantity) VALUES(?,?,?) "
            "ON CONFLICT(holder,material) DO UPDATE SET quantity=excluded.quantity",
            (holder, material, qty),
        )

    @staticmethod
    def _valid_holder(holder: str) -> bool:
        return holder.startswith("character:") or holder.startswith("organization:")

    def _check_holder(self, holder: str) -> None:
        self._require(self._valid_holder(holder), "bad stock or item holder")
        kind, key = holder.split(":", 1)
        if kind == "character":
            self._one("characters", "character_id", key)
        else:
            self._one("organizations", "org_id", key)

    def _holder_authorized(self, actor: str, holder: str, role: str = "quartermaster") -> bool:
        if actor == "system":
            return True
        if holder == f"character:{actor}":
            return True
        if holder.startswith("organization:"):
            return self._has_role(actor, holder.split(":", 1)[1], role)
        return False

    def _assert_version(self, site: sqlite3.Row, payload: Mapping[str, Any]) -> None:
        self._require("expected_version" in payload, "site expected_version required")
        self._require(site["version"] == payload["expected_version"], "stale site version")

    def apply(self, event_id: str, kind: str, actor: str, payload: Mapping[str, Any], *, tick: int, crash_before_commit: bool = False) -> dict:
        """Apply one fully atomic operation; exact retries are safe.

        If the same ID is reused with different content, reject it rather than silently
        accepting an unrelated mutation. Synthetic 'crash_before_commit' simulates an
        exception after state + ledger are staged, before SQLite commits them.
        """
        self._require(isinstance(event_id, str) and 1 <= len(event_id) <= 128, "bad event ID")
        self._require(isinstance(kind, str) and kind and isinstance(actor, str) and actor, "bad kind or actor")
        self._require(isinstance(tick, int) and tick >= 0, "tick must be nonnegative integer")
        self._require(isinstance(payload, Mapping), "payload must be an object")
        clean_payload = json.loads(canonical(dict(payload)))
        if kind in V3_KINDS:
            self._require(type(clean_payload.get("__v")) is int and clean_payload["__v"] == 3,
                          "V0.3 events require hashed __v=3 payload")
        else:
            self._require("__v" not in clean_payload, "legacy event payload must remain unversioned")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute("SELECT seq,kind,actor,payload,tick,event_hash FROM ledger WHERE event_id=?", (event_id,)).fetchone()
            if prior is not None:
                self._require(prior["kind"] == kind and prior["actor"] == actor and prior["tick"] == tick and prior["payload"] == canonical(clean_payload), "event ID reused with different payload")
                self.db.execute("COMMIT")
                return {"event_id": event_id, "seq": prior["seq"], "duplicate": True, "event_hash": prior["event_hash"]}
            tail = self.db.execute("SELECT seq, tick, event_hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
            seq = int(tail["seq"]) + 1 if tail else 1
            self._require(tail is None or tick >= tail["tick"], "nonmonotonic world tick")
            self._dispatch(kind, actor, clean_payload, tick)
            prev = tail["event_hash"] if tail else "0" * 64
            row_data = {"seq": seq, "event_id": event_id, "tick": tick, "actor": actor,
                        "kind": kind, "payload": clean_payload, "prev_hash": prev}
            event_hash = sha256(row_data)
            self.db.execute(
                "INSERT INTO ledger(seq,event_id,tick,actor,kind,payload,prev_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)",
                (seq, event_id, tick, actor, kind, canonical(clean_payload), prev, event_hash),
            )
            if crash_before_commit:
                raise RuntimeError("SIMULATED_CRASH_BEFORE_COMMIT")
            self.db.execute("COMMIT")
            return {"event_id": event_id, "seq": seq, "duplicate": False, "event_hash": event_hash}
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _dispatch(self, k: str, actor: str, p: dict, tick: int) -> None:
        db = self.db
        if k == "AccountRegistered":
            self._system(actor)
            db.execute("INSERT INTO accounts(account_id) VALUES(?)", (p["account_id"],))
        elif k == "AccountSanctioned":
            self._system(actor)
            self._one("accounts", "account_id", p["account_id"])
            db.execute("UPDATE accounts SET sanctioned=? WHERE account_id=?", (int(bool(p["sanctioned"])), p["account_id"]))
        elif k == "CharacterEntered":
            self._system(actor)
            acc = self._one("accounts", "account_id", p["account_id"])
            self._require(acc["sanctioned"] == 0, "sanctioned account cannot enter")
            alive = db.execute("SELECT 1 FROM characters WHERE account_id=? AND state!='deceased' LIMIT 1", (p["account_id"],)).fetchone()
            self._require(alive is None, "account already has living survivor")
            db.execute("INSERT INTO characters(character_id,account_id,origin,occupation,location) VALUES(?,?,?,?,?)",
                       (p["character_id"], p["account_id"], p["origin"], p.get("occupation", "resident"), p["location"]))
        elif k == "OrganizationRegistered":
            self._system(actor)
            db.execute("INSERT INTO organizations(org_id,name) VALUES(?,?)", (p["org_id"], p["name"]))
        elif k == "MembershipGranted":
            self._system(actor)
            self._one("organizations", "org_id", p["org_id"])
            self._one("characters", "character_id", p["character_id"])
            db.execute("INSERT INTO memberships VALUES(?,?,?)", (p["org_id"], p["character_id"], p["role"]))
        elif k == "SiteRegistered":
            self._system(actor)
            self._one("organizations", "org_id", p["owner_org"])
            db.execute("INSERT INTO sites(site_id,name,kind,owner_org,status,critical) VALUES(?,?,?,?,?,?)",
                       (p["site_id"], p["name"], p["kind"], p["owner_org"], p.get("status", "operational"), int(bool(p.get("critical", False)))))
        elif k == "CharacterMoved":
            ch = self._active(actor)
            self._require(actor == p["character_id"], "cannot move someone else")
            self._require(ch["location"] == p["from"], "not at departure location")
            self._require(db.execute("SELECT 1 FROM medical_cases WHERE character_id=? AND state IN ('transit','stabilized','admitted')", (actor,)).fetchone() is None, "patient requires medical transport or discharge")
            self._require(db.execute("SELECT 1 FROM medical_transports WHERE responder=? AND status='traveling'", (actor,)).fetchone() is None, "responder already in medical transport")
            self._require(isinstance(p["to"], str) and p["to"], "bad destination")
            route = db.execute("SELECT * FROM routes WHERE route_id=?", (p["route_id"],)).fetchone()
            self._require(route is not None, "unknown route")
            self._require({p["from"], p["to"]} == {route["point_a"], route["point_b"]}, "route does not connect endpoints")
            if route["guarded_by_site"] is not None:
                gate = self._one("sites", "site_id", route["guarded_by_site"])
                self._require(gate["status"] == "operational", "route blocked by physical site")
            # This checks topological connectivity, NOT elapsed travel time or navmesh collision.
            db.execute("UPDATE characters SET location=?,version=version+1 WHERE character_id=?", (p["to"], actor))
            db.execute("UPDATE items SET location=? WHERE custodian=?", (p["to"], f"character:{actor}"))
        elif k == "CharacterInjured":
            self._system(actor)
            ch = self._one("characters", "character_id", p["character_id"])
            self._require(ch["state"] in ("active", "injured"), "invalid injury state")
            severity = p["severity"]
            self._require(isinstance(severity, int) and 1 <= severity <= 100, "invalid injury severity")
            new_hp = max(0, ch["health"] - severity)
            state = "incapacitated" if new_hp <= 20 else "injured"
            db.execute("UPDATE characters SET state=?, health=?,version=version+1 WHERE character_id=?", (state, new_hp, p["character_id"]))
        elif k == "CharacterStabilized":
            target = self._one("characters", "character_id", p["character_id"])
            self._require(target["state"] == "incapacitated", "target not incapacitated")
            self._require(db.execute("SELECT 1 FROM medical_cases WHERE character_id=? AND state NOT IN ('expired','deceased','recovered')", (p["character_id"],)).fetchone() is None, "timed case requires MedicalCaseStabilized")
            responder = self._active(actor)
            self._require(responder["location"] == target["location"], "responder not colocated")
            h = f"character:{actor}"
            self._require(self._stock(h, "field_kit") >= 1, "missing field kit")
            self._set_stock(h, "field_kit", self._stock(h, "field_kit") - 1)
            db.execute("UPDATE characters SET state='stabilized', health=25,version=version+1 WHERE character_id=?", (p["character_id"],))
        elif k == "CharacterRehabilitating":
            self._system(actor)
            ch = self._one("characters", "character_id", p["character_id"])
            self._require(ch["state"] == "stabilized", "must be stabilized first")
            self._require(db.execute("SELECT 1 FROM medical_cases WHERE character_id=? AND state NOT IN ('expired','deceased','recovered')", (p["character_id"],)).fetchone() is None, "timed case requires medical treatment workflow")
            db.execute("UPDATE characters SET state='rehabilitating',version=version+1 WHERE character_id=?", (p["character_id"],))
        elif k == "CharacterRecovered":
            self._system(actor)
            ch = self._one("characters", "character_id", p["character_id"])
            self._require(ch["state"] == "rehabilitating", "must complete rehabilitation")
            self._require(db.execute("SELECT 1 FROM medical_cases WHERE character_id=? AND state NOT IN ('expired','deceased','recovered')", (p["character_id"],)).fetchone() is None, "timed case requires MedicalCaseRecovered")
            db.execute("UPDATE characters SET state='active',health=85,version=version+1 WHERE character_id=?", (p["character_id"],))
        elif k == "CharacterDied":
            self._system(actor)
            ch = self._one("characters", "character_id", p["character_id"])
            self._require(ch["state"] != "deceased", "death is terminal")
            db.execute("UPDATE characters SET state='deceased',health=0,connected=0,version=version+1 WHERE character_id=?", (p["character_id"],))
            db.execute("UPDATE medical_transports SET status='aborted' WHERE status='traveling' AND (responder=? OR case_id IN (SELECT case_id FROM medical_cases WHERE character_id=?))", (p["character_id"],p["character_id"]))
            db.execute("UPDATE medical_cases SET state='deceased',completed_tick=? WHERE character_id=? AND state NOT IN ('recovered','expired','deceased')", (tick, p["character_id"]))
            # Physical carried possessions become an estate, retaining legal ownership.
            db.execute("UPDATE items SET custodian=?,location=? WHERE custodian=?",
                       (f"estate:{p['character_id']}", ch["location"], f"character:{p['character_id']}"))
        elif k == "CharacterDisconnected":
            self._system(actor)
            ch = self._one("characters", "character_id", p["character_id"])
            self._require(ch["state"] != "deceased", "dead cannot disconnect")
            db.execute("UPDATE characters SET connected=0,version=version+1 WHERE character_id=?", (p["character_id"],))
        elif k == "CharacterReconnected":
            self._system(actor)
            ch = self._one("characters", "character_id", p["character_id"])
            self._require(ch["state"] != "deceased", "dead cannot reconnect")
            self._require(self._one("accounts", "account_id", ch["account_id"])["sanctioned"] == 0, "account sanctioned")
            db.execute("UPDATE characters SET connected=1,version=version+1 WHERE character_id=?", (p["character_id"],))
        elif k == "CharacterPrivateNote":
            ch = self._active(actor)
            self._require(actor == p["character_id"], "notes belong to author")
            existing = json.loads(ch["private_knowledge"])
            self._require(isinstance(p["text"], str) and p["text"], "empty note")
            db.execute("UPDATE characters SET private_knowledge=?,version=version+1 WHERE character_id=?", (canonical(existing + [p["text"]]), actor))
        elif k == "StockProvisioned":
            self._system(actor)
            self._check_holder(p["holder"])
            self._require(isinstance(p["quantity"], int) and p["quantity"] > 0, "bad stock qty")
            self._set_stock(p["holder"], p["material"], self._stock(p["holder"], p["material"]) + p["quantity"])
        elif k == "StockTransferred":
            self._active(actor)
            source, dest = p["from_holder"], p["to_holder"]
            self._check_holder(source)
            self._check_holder(dest)
            self._require(source != dest, "invalid same holder")
            self._require(self._holder_authorized(actor, source), "no stock custody permission")
            # Preserve legacy V0.1 abstract transfers only while no physical
            # depot mapping is in force. A pair of real separate depots must
            # use ShipmentDispatched/ShipmentDelivered, not teleport stock.
            if source.startswith("organization:") and dest.startswith("organization:"):
                source_depot = db.execute("SELECT location FROM depots WHERE holder=?", (source,)).fetchone()
                dest_depot = db.execute("SELECT location FROM depots WHERE holder=?", (dest,)).fetchone()
                if source_depot is not None or dest_depot is not None:
                    self._require(source_depot is not None and dest_depot is not None and source_depot["location"] == dest_depot["location"], "remote depots require physical shipment")
            qty = p["quantity"]
            self._require(isinstance(qty, int) and qty > 0 and self._stock(source, p["material"]) >= qty, "insufficient stock")
            self._set_stock(source, p["material"], self._stock(source, p["material"]) - qty)
            self._set_stock(dest, p["material"], self._stock(dest, p["material"]) + qty)
        elif k == "ItemRegistered":
            self._system(actor)
            self._check_holder(p["custodian"])
            if p["custodian"].startswith("character:"):
                char = self._one("characters", "character_id", p["custodian"].split(":",1)[1])
                self._require(p["location"] == char["location"], "registered carried item not colocated")
            db.execute("INSERT INTO items(item_id,name,custodian,legal_owner,location) VALUES(?,?,?,?,?)",
                       (p["item_id"], p["name"], p["custodian"], p.get("legal_owner", p["custodian"]), p["location"]))
        elif k == "ItemTransferred":
            self._active(actor)
            it = self._one("items", "item_id", p["item_id"])
            self._require(self._holder_authorized(actor, it["custodian"]), "item not in authorized custody")
            self._check_holder(p["to_holder"])
            dest = p["to_holder"]
            if dest.startswith("character:"):
                receiving = self._one("characters", "character_id", dest.split(":",1)[1])
                self._require(receiving["location"] == self._active(actor)["location"], "receiver not colocated")
            position = self._active(actor)["location"]
            self._require(p["location"] == position, "cannot move item to a remote location")
            db.execute("UPDATE items SET custodian=?,legal_owner=?,location=?,disputed=0 WHERE item_id=?",
                       (p["to_holder"], p["to_holder"], position, p["item_id"]))
        elif k == "ItemDropped":
            ch = self._active(actor)
            it = self._one("items", "item_id", p["item_id"])
            self._require(it["custodian"] == f"character:{actor}", "not carrying item")
            db.execute("UPDATE items SET custodian='ground',location=? WHERE item_id=?", (ch["location"], p["item_id"]))
        elif k == "ItemCollected":
            ch = self._active(actor)
            it = self._one("items", "item_id", p["item_id"])
            self._require(it["custodian"] == "ground" and it["location"] == ch["location"], "item not physically available")
            contested = it["legal_owner"] != f"character:{actor}"
            db.execute("UPDATE items SET custodian=?,disputed=? WHERE item_id=?", (f"character:{actor}", int(contested), p["item_id"]))
        elif k == "SiteInspected":
            ch = self._active(actor)
            site = self._one("sites", "site_id", p["site_id"])
            self._assert_version(site, p)
            self._require(ch["location"] == site["site_id"], "inspection requires site presence")
            self._require(self._has_role(ch["character_id"], site["owner_org"], "inspector"), "inspector role required")
            db.execute("UPDATE sites SET inspected=1,version=version+1 WHERE site_id=?", (p["site_id"],))
        elif k == "SiteRepaired":
            ch = self._active(actor)
            site = self._one("sites", "site_id", p["site_id"])
            self._assert_version(site, p)
            self._require(ch["location"] == site["site_id"], "repair requires site presence")
            self._require(site["status"] in ("restricted", "failed") and site["inspected"] == 1, "site must be restricted/failed and inspected")
            self._require(self._has_role(ch["character_id"], site["owner_org"], "maintainer"), "maintainer role required")
            material, qty = p["material"], p["quantity"]
            self._require(isinstance(qty, int) and qty > 0, "bad repair qty")
            holder = f"organization:{site['owner_org']}"
            self._require(self._stock(holder, material) >= qty, "insufficient materials")
            self._set_stock(holder, material, self._stock(holder, material) - qty)
            db.execute("UPDATE sites SET status='operational',inspected=0,version=version+1 WHERE site_id=?", (p["site_id"],))
        elif k == "SiteObstructed":
            ch = self._active(actor)
            site = self._one("sites", "site_id", p["site_id"])
            self._assert_version(site, p)
            self._require(ch["location"] == site["site_id"], "must be physically present")
            self._require(site["status"] == "operational", "only open sites can become obstructed")
            self._require(not site["critical"] or site["kind"] == "bridge", "high-consequence site protected by independent interlocks")
            if site["kind"] == "bridge":
                holder = f"character:{actor}"
                self._require(self._stock(holder, "barrier_kit") >= 1, "bridge obstruction requires physical barrier equipment")
                self._set_stock(holder, "barrier_kit", self._stock(holder, "barrier_kit") - 1)
            db.execute("UPDATE sites SET status='obstructed',version=version+1 WHERE site_id=?", (p["site_id"],))
        elif k == "SiteCleared":
            ch = self._active(actor)
            site = self._one("sites", "site_id", p["site_id"])
            self._assert_version(site, p)
            self._require(ch["location"] == site["site_id"], "clearing requires physical presence")
            self._require(site["status"] == "obstructed", "site not obstructed")
            self._require(self._has_role(ch["character_id"], site["owner_org"], "maintainer"), "maintainer required")
            db.execute("UPDATE sites SET status='operational',version=version+1 WHERE site_id=?", (p["site_id"],))
        elif k == "RouteRegistered":
            self._system(actor)
            if p.get("guarded_by_site"):
                self._one("sites", "site_id", p["guarded_by_site"])
            self._require(isinstance(p["km"], (float, int)) and p["km"] > 0, "invalid route distance")
            db.execute("INSERT INTO routes VALUES(?,?,?,?,?)", (p["route_id"], p["point_a"], p["point_b"], p["km"], p.get("guarded_by_site")))
        elif k == "EvidenceRecorded":
            self._active(actor)
            self._require(p["classification"] in ("public", "private", "clinical"), "invalid classification")
            db.execute("INSERT INTO evidence(record_id,author,summary,source,classification) VALUES(?,?,?,?,?)",
                       (p["record_id"], actor, p["summary"], p["source"], p["classification"]))
        elif k == "EvidencePublished":
            self._active(actor)
            ev = self._one("evidence", "record_id", p["record_id"])
            self._require(ev["author"] == actor, "cannot publish another author's record")
            self._require(ev["classification"] != "clinical", "clinical evidence cannot be publicly released by default")
            self._require(ev["published"] == 0, "already published")
            db.execute("UPDATE evidence SET published=1 WHERE record_id=?", (p["record_id"],))
        elif k == "ReportFiled":
            self._active(actor)
            db.execute("INSERT INTO reports VALUES(?,?,?,?,?,?)", (p["report_id"], actor, p["community"], p["claim"], p["subject"], p.get("evidence_ref", "")))
        elif k == "AgentRegistered":
            self._system(actor)
            self._require(all(isinstance(p[n], int) and p[n] >= 0 for n in ("energy", "nutrients")), "bad biologic resources")
            db.execute("INSERT INTO agents VALUES(?,?,?,?,?,?)", (p["agent_id"], p["name"], p["kind"], p["energy"], p["nutrients"], "active" if p["energy"] and p["nutrients"] else "dormant"))
        elif k == "AgentAdvanced":
            self._system(actor)
            ag = self._one("agents", "agent_id", p["agent_id"])
            self._require(ag["status"] == "active", "dormant agent cannot act")
            e, n = p["energy_used"], p["nutrients_used"]
            self._require(isinstance(e, int) and isinstance(n, int) and e > 0 and n > 0, "invalid biological draw")
            self._require(ag["energy"] >= e and ag["nutrients"] >= n, "insufficient biological support")
            status = "dormant" if ag["energy"] == e or ag["nutrients"] == n else "active"
            db.execute("UPDATE agents SET energy=energy-?,nutrients=nutrients-?,status=? WHERE agent_id=?", (e, n, status, p["agent_id"]))
        elif k == "RegionRegistered":
            self._system(actor)
            ints = [p[v] for v in ("population", "food", "water", "food_production", "water_production")]
            self._require(all(isinstance(x, int) and x >= 0 for x in ints), "bad region resources")
            db.execute("INSERT INTO regions VALUES(?,?,?,?,?,?,?)", (p["region_id"], *ints, p.get("last_tick", 0)))
        elif k == "RegionAdvanced":
            self._system(actor)
            reg = self._one("regions", "region_id", p["region_id"])
            steps = p["steps"]
            self._require(isinstance(steps, int) and 1 <= steps <= 30, "region advancement must be bounded 1..30")
            # One unit food and water per 100 aggregate residents each step; simplified test ledger.
            need = (reg["population"] + 99) // 100 * steps
            food = reg["food"] + reg["food_production"] * steps - need
            water = reg["water"] + reg["water_production"] * steps - need
            self._require(food >= 0 and water >= 0, "insufficient aggregate supplies")
            db.execute("UPDATE regions SET food=?,water=?,last_tick=last_tick+? WHERE region_id=?", (food, water, steps, p["region_id"]))
        elif k == "RoadRegistered":
            self._system(actor)
            db.execute("INSERT INTO interworld_links VALUES(?,?)", (p["link_id"], p.get("status", "open")))
        elif k == "RoadClosed":
            self._system(actor)
            road = self._one("interworld_links", "link_id", p["link_id"])
            self._require(road["status"] == "open", "road already closed")
            db.execute("UPDATE interworld_links SET status='closed' WHERE link_id=?", (p["link_id"],))
        elif k == "ContractRegistered":
            self._system(actor)
            self._require(p["sponsor"] != p["contractor"], "invalid counterparty")
            self._require(isinstance(p["quantity"], int) and p["quantity"] > 0, "invalid compensation")
            self._require(self._stock(p["sponsor"], p["material"]) >= p["quantity"], "sponsor insolvent")
            db.execute("INSERT INTO contracts VALUES(?,?,?,?,?,'open')", (p["contract_id"], p["sponsor"], p["contractor"], p["material"], p["quantity"]))
        elif k == "ContractFulfilled":
            self._system(actor)  # future signed adjudicator, not client authority
            ct = self._one("contracts", "contract_id", p["contract_id"])
            self._require(ct["state"] == "open", "contract already fulfilled")
            self._require(self._stock(ct["sponsor"], ct["compensation_material"]) >= ct["compensation_quantity"], "sponsor insufficient at payment")
            self._set_stock(ct["sponsor"], ct["compensation_material"], self._stock(ct["sponsor"], ct["compensation_material"]) - ct["compensation_quantity"])
            self._set_stock(ct["contractor"], ct["compensation_material"], self._stock(ct["contractor"], ct["compensation_material"]) + ct["compensation_quantity"])
            db.execute("UPDATE contracts SET state='fulfilled' WHERE contract_id=?", (p["contract_id"],))
        else:
            if not dispatch_v3(self, k, actor, p, tick) and not dispatch_expanded(self, k, actor, p, tick):
                raise WorldRuleError(f"unsupported event type: {k}")

    def evidence_visible_to(self, record_id: str, viewer: str | None = None, *, at_tick: int | None = None) -> bool:
        self._one("evidence", "record_id", record_id)
        if viewer == "system":
            return True  # Off-line fixture only; NOT a production caller identity.
        if viewer is None:
            return bool(self._one("evidence", "record_id", record_id)["published"])
        if at_tick is None:
            tail = self.db.execute("SELECT tick FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
            at_tick = int(tail["tick"]) if tail else 0
        return _evidence_access(self, record_id, viewer, at_tick)

    def run_due(self, now_tick: int, *, limit: int = 50) -> list[dict]:
        """Advance up to `limit` due jobs by explicit durable ledger events.

        Not a clock daemon; the trusted test harness calls this method.
        """
        due = due_tasks(self, now_tick, limit=limit)
        latest = self.db.execute("SELECT tick FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        self._require(latest is None or now_tick >= latest["tick"], "scheduler cannot move time backwards")
        return [self.apply(f"scheduled:{task_id}", "TaskTriggered", "system",
                           {"__v": 3, "task_id": task_id}, tick=now_tick) for task_id in due]


    def shortest_route(self, start: str, end: str, *, rail_only: bool = False) -> dict | None:
        """Surface graph only, not 3D pathfinding. Nodes named by stable route anchors."""
        edges: dict[str, list[tuple[float, str, str]]] = {}
        for r in self.db.execute("SELECT * FROM routes ORDER BY route_id"):
            if r["guarded_by_site"]:
                site = self._one("sites", "site_id", r["guarded_by_site"])
                if site["status"] != "operational":
                    continue
            if rail_only and not r["route_id"].startswith("rail:"):
                continue
            for a, b in ((r["point_a"], r["point_b"]), (r["point_b"], r["point_a"])):
                edges.setdefault(a, []).append((r["km"], b, r["route_id"]))
        frontier = [(0.0, start, [start], [])]
        best = {start: 0.0}
        while frontier:
            d, node, nodes, routes = heapq.heappop(frontier)
            if node == end:
                return {"km": round(d, 3), "nodes": nodes, "routes": routes}
            if d > best.get(node, float("inf")) + 1e-10:
                continue
            for km, dest, rid in edges.get(node, []):
                cand = d + km
                if cand + 1e-10 < best.get(dest, float("inf")):
                    best[dest] = cand
                    heapq.heappush(frontier, (cand, dest, nodes + [dest], routes + [rid]))
        return None

    def ledger(self) -> list[dict]:
        return [{"seq": r["seq"], "event_id": r["event_id"], "tick": r["tick"],
                 "actor": r["actor"], "kind": r["kind"], "payload": json.loads(r["payload"]),
                 "prev_hash": r["prev_hash"], "event_hash": r["event_hash"]}
                for r in self.db.execute("SELECT * FROM ledger ORDER BY seq")]

    def verify_chain(self) -> dict:
        prev = "0" * 64
        count = 0
        for event in self.ledger():
            self._require(event["seq"] == count + 1, "ledger sequence broken")
            self._require(event["prev_hash"] == prev, f"broken prev hash at {event['seq']}")
            data = {k: event[k] for k in ("seq", "event_id", "tick", "actor", "kind", "payload", "prev_hash")}
            self._require(sha256(data) == event["event_hash"], f"broken hash at {event['seq']}")
            prev = event["event_hash"]
            count += 1
        return {"verified_events": count, "last_hash": prev, "status": "hash-chain-consistent"}

    def snapshot(self) -> dict:
        # Sorted stable row values, excludes auto-generated SQLite metadata and wall clock.
        result: dict[str, list[dict]] = {}
        for table in TABLES:
            rows = [dict(r) for r in self.db.execute(f"SELECT * FROM {table}")]
            result[table] = sorted(rows, key=canonical)
        return result

    def state_hash(self) -> str:
        return sha256(self.snapshot())

    def audit_state(self) -> dict:
        """Rebuild materialized tables from committed ledger, catching row tampering.

        A hash chain alone cannot detect someone manually editing a materialized
        site row while leaving the ledger untouched. This verifies both layers.
        """
        chain = self.verify_chain()
        with World() as replay:
            for ev in self.ledger():
                replay.apply(ev["event_id"], ev["kind"], ev["actor"], ev["payload"], tick=ev["tick"])
            calculated = replay.state_hash()
            observed = self.state_hash()
            self._require(calculated == observed, "materialized state differs from ledger replay")
            return {"status": "PASS", "events": chain["verified_events"],
                    "state_sha256": observed, "ledger_last_hash": chain["last_hash"]}

    def export_jsonl(self, target: str | Path) -> None:
        self.audit_state()
        Path(target).write_text("".join(canonical(ev) + "\n" for ev in self.ledger()), encoding="utf-8")

    @classmethod
    def replay_jsonl(cls, input_path: str | Path, target_db: str | Path = ":memory:") -> "World":
        world = cls(target_db)
        try:
            for raw in Path(input_path).read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                ev = json.loads(raw)
                expected_fields = {"seq", "event_id", "tick", "actor", "kind", "payload", "prev_hash", "event_hash"}
                world._require(set(ev) == expected_fields, "unexpected replay fields")
                data = {key: ev[key] for key in ("seq", "event_id", "tick", "actor", "kind", "payload", "prev_hash")}
                world._require(sha256(data) == ev["event_hash"], "tampered replay event")
                committed = world.apply(ev["event_id"], ev["kind"], ev["actor"], ev["payload"], tick=ev["tick"])
                world._require(committed["seq"] == ev["seq"] and committed["event_hash"] == ev["event_hash"], "replay checksum mismatch")
            world.verify_chain()
            return world
        except Exception:
            world.close()
            raise
