# Architecture and world rules

## A. Transaction model

Every accepted world mutation is one **Event** with a globally unique identifier, monotonic *logical ordering tick*, event type, actor, JSON payload, sequence number and SHA-256 hash-chain link. The engine performs a `BEGIN IMMEDIATE` transaction on an SQLite database; it validates the event, updates materialized state, appends the ledger row, and commits atomically.

An exact duplicate event ID with the same actor/type/payload/tick returns `duplicate: true` without a second mutation. The same ID with a different payload is rejected. Events with stale expected site versions are rejected. A simulated exception before commit rolls back both material state and ledger.

SQLite is appropriate for an **offline single-database rules laboratory**. It is not evidence of distributed state ownership, geographic server handoff or 1,000-player capacity.

## B. Identity, mortality and medicine

- An `Account` is out-of-world; a `Character` is one living Eloden person.
- One living player character per account is the current laboratory rule, not approved final game policy.
- A permanently dead character has state `deceased`, cannot act/reconnect and cannot be revived.
- The account may create a fresh survivor; new character IDs have no inherited private memories or inventory.
- Carried items of the deceased move to an estate custody record **without teleporting into the successor's possession**.
- Field stabilization consumes a legitimate responder's field kit, requires physical co-location and does not change the character's identity.
- A health state machine covers active → injured/incapacitated → stabilized → rehabilitating → active, or irreversible deceased.

The code intentionally does *not* implement a real clinical simulation or treatment details.

## C. Site and material authority

Sites are owned by organizations and have `status`, `version`, `critical` and inspection status. The repair rule requires:

1. Valid active character and correct physical site;
2. An independent inspection by an authorized inspector;
3. A licensed maintainer for the owning organization;
4. An expected site version matching the current authoritative version;
5. Sufficient committed material stock;
6. One transaction that debits material and changes site status.

For this test model, `StockTransferred` is an **abstract authorized custody transfer**, not a moving freight vehicle or physical transport. Future material logistics must require actual depot geography, vehicle capacity, scheduling and custody receipts.

One bridge obstruction requires a physically present character and barrier supplies. High-consequence hospital/dam obstruction is explicitly rejected by this generic event type; eventual dedicated, approved physical incidents will require much more granular controls and consequences.

## D. One real bridge and two actual Roads

The normal local bridge route Westbank–Civic measures **2.017 km** in the synthetic graph, versus **6.610 km** on the alternate lower crossing route. A `SiteObstructed` event disables routes explicitly protected by that site's state. This uses 13 sample graph edges and is not physics or pedestrian pathfinding.

Two independent off-world `Road` objects—Cydren Skygate and Orveth Freight Ring—can be closed separately. Their closure events have **no automatic power-grid, hospital, rail or local-government effects**, in keeping with the Eloden premise and established Transcosmic rules.

## E. Knowledge and reputation

`CharacterPrivateNote` stays on the specific survivor. Source observations can be recorded as separately classified evidence. Clinical-classified evidence cannot be publicly published via the basic publication event. The viewer query defaults to published evidence only; author and trusted fixture system can inspect their own private data.

`ReportFiled` creates testimony in a **specific community**, not a universal hard-coded guilt flag. False witnesses, adjudication, detailed provenance and legal accountability remain to be designed.

## F. Biology and off-screen society

An instrumented bioadaptive work-unit has a resource ledger for energy and nutrients. Advancing without sufficient support fails. A zero-support unit becomes dormant and cannot execute further active ticks.

A remote region has population, basic food and water stocks and production per bounded step. The model consumes one unit each per 100 residents per step as an *arbitrary economy proof*, not a credible demographic nutrition balance. The event is bounded to at most 30 steps in one accepted update. No organism inheritance, physical reproduction, genetics, population mobility, weather or consciousness is simulated.

## G. Source-of-truth reconstruction

1. `ledger()` returns committed events ordered by sequence.
2. `verify_chain()` verifies IDs/sequence progression and the previous/current SHA-256 hash link.
3. `audit_state()` **replays all committed events into a clean in-memory database** and requires the reconstructed snapshot hash to match the materialized tables. This detects unlogged edits to inventory, sites, accounts and other tables even when the event hash-chain is untouched.
4. `export_jsonl()` writes a portable event history, only after state audit passes.
5. `replay_jsonl()` verifies each event hash and re-applies accepted events in order into another fresh database.

The event ledger is a logical source of truth in this prototype; it is not a security-audited or production-qualified event-sourcing architecture.

## H. Future production interface, not implemented

```text
Browser client (untrusted intent)
          |
     Authenticated Gateway (not built)
          |
   Server-authoritative simulation (not built)
          |
   Validated domain actions / access scopes
          |
       Durable event service
          |
       State snapshots / read models
          |
         Game events & client replication
```

The current package implements only the **logical domain action/event store** portion in one local SQLite process. It does not implement the surrounding network, authoritative position and time validation, adaptive interest management, asset-streaming/world rendering or distributed servers.
