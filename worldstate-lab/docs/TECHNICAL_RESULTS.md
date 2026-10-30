# V0.1 verification certificate (offline only)

This certificate describes tests that were actually executed in the local Python container. It is not a client, server or formal security certification.

- Python interpreter: 3.13.5 in the build session; package runtime target Python >=3.10 (other versions not separately tested).
- Unit suite: 43 tests passed using Python `unittest`.
- Demonstration: 64 event records committed with SQLite atomic transactions.
- One initial site repair: accepted exactly once after inspection and material delivery.
- Duplicate repair: rejected as a new action; site and material state unchanged.
- Bridge graph: Westbank to Civic 2.017 km open, 6.610 km obstructed.
- Mortal character: deceased character stayed deceased; a new character from the same account entered with a different ID and no inherited private notebook.
- Two independent interworld Road events: both closed; local hospital remained operational.
- Active biohybrid support: energy/nutrient resources actually consumed.
- Replay: all 64 committed events reproduced an identical state SHA-256 hash in a fresh in-memory database.
- State audit: replay-derived materialized state matched the stored state.
- Crash rollback: an intentionally raised exception before COMMIT did not change stock or ledger; retry committed once.
- Concurrent SQLite repairs: two independent DB connections raced at one expected site version; one accepted, one rejected as stale, with a single debit.
- Tampering checks: manual ledger modification and unlogged materialized-state changes detected by separate tests.

The hash and exact event list can be independently checked using:

```sh
python -m worldstate verify output/demo_events.jsonl
```

The CLI prints a state SHA-256 checksum and the hash-chain tail. The accompanying `manifest.json` records SHA-256 checksums of every packaged file except the manifest itself.

## What was not executed

No Godot game build, real browser/game controller test, multiplayer network test, large-N load scenario, physiological or ecological real-world simulation, Internet hosting, signed audit service or authenticated client integration. Scenario S10 is a *nonclaim guard*, not a 1,000-player performance test.
