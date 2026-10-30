# Executed verification report - World-State Lab V0.2

**Date:** 2026-10-29 (America/New_York); Python 3.13.5, SQLite via Python standard library; isolated local container. This is a rules prototype, not a network/client/Godot test.

## Baseline and new regression

`python -m unittest discover -s tests -v`: **85 tests pass**, including **43 unmodified V0.1 tests** and **42 additional V0.2 tests**. The V0.1 64-event trace replays under V0.2 and the pre-existing V0.1 SQLite database opens, migrates additively and passes ledger-vs-state audit.

Tests cover failure rollback, duplicate event suppression, mortal character transitions, private knowledge boundaries, medical deadlines, three-hop rescue, hospital rehabilitation, rescuer/patient death abort, item custody, regional production, freight capacity, physical depots, delivery ETA, fuel usage, failed refueling, bridge blockade and a justified freight diversion with extra fuel and distance.

## Integrated demonstration

`python -m worldstate expanded-demo --out output/expanded`:

- **76 committed events** and a complete replay audit.
- The original forest patient `d1` is stabilized by `b1`, evacuated across three physically connected routes, admitted to an operational hospital, and medically recovered as **the same still-living person**.
- Southplain aggregate food increases from **1,000 to 1,020** after an actual 20-unit food shipment arrives.
- A separate water shipment diverts around the obstructed Central Road Bridge along the **6.610 km lower-crossing route** rather than teleporting across the closed 2.017 km bridge.
- **10 water units** arrive once in the Civic Trust's stock ledger.
- State SHA-256 and reconstructed replay SHA-256 both: `bd009d407b2a15a5d27a50b146d0853e4dd45cbfddb7af084d8a21da50a04560`.

## Deterministic stress run

`python -m worldstate stress --out output/stress --seed 8619 --rounds 300`:

- **300 cargo shipments delivered**, **1,443 committed world events**.
- **8 actual SQLite connection closures/reopens** during the sequence.
- **18 invalid early deliveries** correctly rejected with no materialized-state mutation.
- **578 food + 486 water units** physically delivered to the regional ledger over the stress scenario.
- Invariant checked on every dispatch and receipt: source/destination stocks, in-transit cargo and regional reserves balance (no unexplained double-counted goods).
- Exact repeatable final state SHA-256 = replayed state SHA-256 = `7cf90721de6d8320d8b81c2b51be0fdd78ff4ab8699659aa8668beeb2b9591b1`.
- Three additional independent seeds (13, 2026, 8619), 180 rounds each, also independently passed with identical state and replay SHA-256 per run; see `output/multi_seed_results.json`.

## Validation boundaries

The 85 tests are local code tests. The **1,443 events are not connected players**. No WebSocket server, account login, distributed authority, avatar movement, real-time clinical simulation, browser renderer or crowd-load test is part of the evidence.

The old 64-event demo's event-chain hashes remain intact. The V0.1 `state_hash` changes in V0.2 because new empty tables are included in the materialized snapshot, not because old physical events were rewritten.

Fictional timed rescue requires a trusted event to trigger expiry; there is no autonomous real-time scheduler. The transport graph uses known Crown Valley waypoint links, **not** geometric vehicle navigation or executable medical care.

All business/world-state records in tests use fictional sample data. No private clinical records or unpublished manuscript excerpts are included.
