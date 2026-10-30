# V0.3 Implementation / Compatibility Contract

Session: `ANEVUM.ANEVUM.BUILD.2026-10-29.001.SEVERANCE-WORLDSTATE-V03`

## What is actually implemented

This extension is **offline** and local. It uses SQLite and Python standard-library code. It is not Godot code, a playable game, production authentication, medical software, a networking server, or a live site. The main entry points are `worldstate/v03.py`, `worldstate/demo_v03.py`, and `worldstate/stress_v03.py`. Core V0.1/V0.2 event semantics and event hashes remain unchanged.

### Versioned events and schema migration

- V0.3 adds an explicit integer `"__v": 3` field to each **new** event payload. `World.apply` refuses V0.3 events lacking the tag, and refuses version tags on the frozen legacy event kinds. Because event payloads are hashed inside ledger events, the V0.3 version tag is covered by the event hash chain.
- Existing V0.1/V0.2 events are untagged, unchanged, and replayed in the exact original order. The previously recorded 64-event and 76-event traces both verify unchanged last-event hashes.
- The new schema has a transactionally created `worldstate_schema` table with `revision=3` and a fixed source revision of 2; `migrate_v3` applies DDL in one `BEGIN IMMEDIATE` transaction. A deliberate exception after a partially completed migration verifies that DDL and metadata roll back together.
- **Intentional compatibility compromise:** the legacy `PRAGMA user_version` remains **2**, because three unmodified V0.2 tests explicitly require it, while the extension revision is recorded as **3** in `worldstate_schema`. This is not a general-purpose production migration framework. Replace the mixed-version markers with one formal migration catalog before networking or deployment.
- Materialized snapshot hashes change with the addition of six new empty tables. **This does not change any old ledger event hash.** Replay consistency is verified between worlds using the *same V0.3 engine*.

### Deterministic scheduled work

- `TaskPlanned` records a medical case's exact deadline+1 due tick.
- `World.run_due(now_tick)` enumerates pending jobs in `(due_tick, task_id)` order and applies **explicit committed** `TaskTriggered` ledger events with stable event IDs `scheduled:<task_id>`.
- On expiry of an **unstabilized** case, the existing V0.2 `MedicalCaseExpired` transition is invoked inside that one atomic event transaction. If the case is already stabilized, admitted, recovered, or deceased, the task commits as `skipped` with no second death.
- `TaskCanceled` requires test-only trusted system authority, and due jobs cannot be completed twice. A simulated crash before commit leaves both the medical state and task pending.
- No real-time OS daemon, waking background task, medical physiology or external network clock exists. A trusted harness **must call** `run_due`; missing planning events do not generate themselves retroactively.

### Clinical evidence access simulation

- `EvidenceSubjectBound` attaches one fictional character as the patient subject of an existing `classification="clinical"` record. In this offline proof, binding is privileged; actual patient/clinician authorization verification is not implemented.
- The linked clinical subject can issue a bounded `read` grant to a specific fictional grantee (`EvidenceAccessGranted`) and revoke it (`EvidenceAccessRevoked`). Private nonclinical evidence can be shared by its author.
- `EvidenceViewed` requires the viewer to be active and authorized at its logical tick; it creates a non-content read audit row. A grant expires, and a revoked grant cannot be reused. This is **not a clinical data protection product**: original legacy `EvidenceRecorded` events still store summary strings directly inside the replayable ledger, so **do not use real patient data**.
- `evidence_visible_to()` is a convenience query, not the enforcement layer of a production document service. The special `system` fixture remains trusted only inside this lab.

### Physical multi-stop freight

- `ConvoyDispatched` validates 2–8 consecutive actual route edges, no cycles, a registered source/destination depot or regional hub, qualified quartermaster presence, capacity, fuel, and source stock. The stock is removed from origin and explicitly held in an in-transit convoy; nothing credits the destination on dispatch.
- `ConvoyLegArrived` checks ETA, route passability and carrier state; records one hop and changes actual carrier position to the completed waypoint. Intermediate arrival leaves cargo in-transit. Only **final** arrival credits actual destination stock or a regional food/water ledger **once**.
- `ConvoyLegDeparted` spends per-leg fuel at a staging waypoint and schedules the next ETA. A blocked route cannot complete. `ConvoyRerouted` replaces the remainder of a physically blocked trip, preserving previous completed hops and **without refunding** fuel spent on the interrupted leg.
- Motion is **node-to-node**, not meter-by-meter. The route graph's distances and tick multipliers are abstract simulation values rather than verified real-world freight physics or a complete road-traffic model.
- The V0.2 single-leg shipment model still exists for replay compatibility. Return journeys from arbitrarily distant convoy destinations have not been generalized into a complete return-to-depot scheduler.

### World-state invariants

1. Exactly one authoritative in-world material quantity exists across source stock, in-transit cargo, and destination stock.
2. No shipment can be delivered twice; no carrier simultaneously undertakes two jobs.
3. Every accepted new action is one hash-bound event and an atomic SQLite commit.
4. A dead character cannot return through the medical scheduler.
5. A grant cannot outlive revocation or its declared expiry.
6. A route closure stops travel without destroying off-world gates' local hospitals, water and power automatically.
7. Replaying the complete event history creates the identical local materialized-state hash.

## Command-line interface

```sh
python -m unittest discover -s tests -v
python -m worldstate v03-demo --out output/v03
python -m worldstate v03-stress --out output/v03_stress --seed 20261029 --rounds 150
python -m worldstate verify output/v03/events_v03.jsonl
```

The `v03-demo` and `v03-stress` commands overwrite their own named output database/JSON/JSONL files. Run in a copy of the extracted package when preserving reference fixtures.

## Upstream design context

- Eloden 18: mortality and account-versus-character continuity
- Eloden 19: bounded care, biology and survival
- Eloden 20: community law and adversarial player interaction
- Eloden 21: physical stock economy
- Eloden 23: invariant verification
- Eloden 24–25: V0.1/V0.2 verified code checkpoints

This source belongs to the isolated **SEVERANCE** world-state preproduction track. No Godot, Cloudflare, Railway, GitHub or public franchise content has been edited.
