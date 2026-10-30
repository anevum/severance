# V0.3 Executed Results and Test Evidence

Status: PASS for scoped **offline rules** verification. Date: 2026-10-29. The test host uses Python 3.13, SQLite and no external dependencies.

## Measured test outcomes

| Test | Verified result |
| --- | --- |
| Original V0.1 tests | 43 passed, source test file unchanged |
| Original V0.2 tests | 42 passed, source test file unchanged |
| New V0.3 tests | 40 passed |
| **Total** | **125 / 125 passed** |
| Integrated demo | 83 accepted events, 3-hop freight after blocked bridge, one actual person medically recovered, evidence consent revoked, both Roads closed, local hospital operational |
| Integrated demo state SHA-256 | `01bfd3bc8ca73a30f2361cfe3ef73b0c185715aa5333f3fc434f67eee9647f50` |
| Integrated demo event tail | `0600a837fb69e9d2af9aac275b5ba9805fafa76df3f7a5f9355911d430895df7` |
| Integrated demo replay hash | Identical state SHA-256 |
| Main randomized stress | 150 new staged convoys, 1,099 committed events, 7 SQLite close/reopens, 22 invalid premature-arrival attempts rejected, exact cargo conservation |
| Stress seed | `20261029` |
| Stress state SHA-256 | `89fb137de5b1e707f20f132a1940c3697b606eba4d434427e107db7197a58287` |
| Stress event tail | `0fff439924283aa9561994b0877135a39ce5a0ad1c6dff4ca334a2a2b35a9ba0` |
| Stress replay state hash | Identical |
| Alternative randomized trials | Seeds 13, 2026 and 8619 each completed 70 convoys, 539 events and three SQLite restarts; all replay checksums match |
| V0.1 preserved trace | 64 events, original ledger tail `91277dcd8135c98886b39d3d88c332983c83c9d0f43fc0bb5ebd8325b9d09fea` verified |
| V0.2 preserved trace | 76 events, original ledger tail `16af1b435c1bb88bb14966f2b3824af8e3f56daee4b08e135fe5f6bb6d03d4aa` verified |
| Migration rollback | Transactional SQLite DDL and revision row both rolled back on injected failure |
| Crash before commit | Scheduled fatal medical result and convoy material debit both rolled back, later clean retry applied once |

## Verification limits

- The **1,099 events** are locally committed data changes, not 1,099 networked clients.
- No 3D Godot scene or playable multiuser server is present.
- Both V0.1 and V0.2 ledger *tail hashes* remain original, but their replayed materialized *state hashes* naturally change under the V0.3 schema because the snapshot now includes six new empty tables.
- The scheduler is only run when the trusted caller invokes `World.run_due`; it does not run in the background.
- The evidence access system operates on explicitly **synthetic** data and is not a compliant production access system.
- Carrier motion is a discrete waypoint model, not a physics simulation, and the generated routes are from the planning atlas.

## Reproduce

```sh
python -m unittest discover -s tests -v
python -m worldstate v03-demo --out output/v03-check
python -m worldstate v03-stress --out output/v03-stress-check --seed 20261029 --rounds 150
python -m worldstate verify output/v03-check/events_v03.jsonl
python -m worldstate verify output/demo_events.jsonl
python -m worldstate verify output/expanded/expanded_events.jsonl
```

The demo and stress tests are deterministic when run with the included engine, test data and random seed. SQL behavior across operating systems/interpreter versions remains to be separately checked.
