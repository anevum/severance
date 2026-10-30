# SEVERANCE — Offline World-State Laboratory V0.3

**Repository import:** Source and tests were recovered from the V0.3 development archive. The original archive contains reference outputs, SQLite databases and a package manifest; those generated artifacts are not included in this source import. Generate new outputs locally before running commands that refer to them.

Session: `ANEVUM.ANEVUM.BUILD.2026-10-29.001.SEVERANCE-WORLDSTATE-V03`

This is an executable, isolated Python/SQLite **preproduction rules laboratory** for the ANEVUM game **SEVERANCE**, set on the fictional planet Eloden in TRANSCOSMIC. It is **not** a multiplayer game, browser scene, Godot project, medical system, login service or live deployment. No Internet connection, proprietary SDK, paid host, or API key is needed.

V0.3 extends the original V0.1/V0.2 engines and includes **85 legacy test cases** and **40 V0.3 test cases**; two compatibility tests now generate fresh synthetic data with the preserved V0.1 engine rather than reading archived databases. It provides event schema tagging, transactional local migration, a bounded scheduled-work runner, synthetic consent-limited evidence access, and staged cargo convoys over physical Crown Valley route graphs.

## Quick start

Run these commands from the archive's extracted root (Python 3.13 verified):

```sh
python -m unittest discover -s tests -v
python -m worldstate demo --out output/old_demo_replayed
python -m worldstate expanded-demo --out output/old_expanded_replayed
python -m worldstate v03-demo --out output/v03_replayed
python -m worldstate v03-stress --out output/v03_stress_replayed --seed 20261029 --rounds 150
python -m worldstate verify output/v03_replayed/events_v03.jsonl
```

**Warning:** commands writing to `--out` overwrite their own named files. The package includes reference output histories that should not be replaced when doing forensic comparisons.

## Implemented systems

| V0.3 capability | Status and guarantee |
| --- | --- |
| Ledger-bound event versions | `__v=3` on new events only; legacy hashes unaffected |
| SQLite migration | Transactional registry revision 3; rollback-tested; legacy `user_version=2` retained for compatibility |
| Timed medical scheduler | Explicit plan, due trigger, conditional skip/cancel, crash rollback, persisted job state |
| Scoped evidence | Subject-approved synthetic clinical read grants, revocation, expiry, read audit; **not real privacy compliance** |
| Multi-stop freight | 2–8 edges, staged physical node-to-node movement, finite fuel and quantity, route blockage and diversion |
| World replay | Same final state after clean event-chain replay; independent state audit |
| Crash recovery | Single-event atomicity; tested SQLite close/reopen, interrupted operations and duplicate event IDs |

## Actual checks this release

- **125/125 unit and integration tests passed** (85 unmodified old tests + 40 V0.3 tests).
- Integrated scenario: **83 accepted events**, patient treated as the same mortal person, synthetic consent revoked, food convoy delivered over three legs after bridge diversion, Roads closed, local hospital operating. Final replay hash matched.
- Seeded stress: **150 convoys**, **1,099 committed events**, **seven SQLite restarts**, **22 deliberately invalid early-arrival operations rejected**, with identical replay checksum and no stock loss/duplication.
- Three other randomized seeds (13, 2026, 8619): **70 convoys**, 539 events, three SQLite restarts per run; all matched independently rebuilt state.
- V0.1 64-event and V0.2 76-event ledger **event hashes** verified unchanged. The derived *state* hashes differ from previous software because V0.3 has new empty state tables.

These numbers count local database operations, **not connected people, networked NPCs, FPS, full world size or gameplay capacity**.

## Files

- `worldstate/engine.py`: unchanged core event semantics, V0.3 dispatch and scheduled query integration
- `worldstate/expansion.py`: original V0.2 medical/one-hop freight implementation, preserved
- `worldstate/v03.py`: new schema, scheduled work, scoped evidence, staged multi-stop cargo
- `worldstate/demo_v03.py`: integrated synthetic scenario
- `worldstate/stress_v03.py`: deterministic randomized courier cycles and replay
- `worldstate/scenarios.py`: original Eloden map/character fixture
- `tests/test_worldstate.py`: V0.1 (43 cases), **unchanged**
- `tests/test_expanded.py`: V0.2 (42 cases), **unchanged**
- `tests/test_v03.py`: V0.3 (40 cases)
- `docs/V03_IMPLEMENTATION.md`: exact events, migration boundaries and invariants
- `docs/V03_LIMITATIONS.md`: what is still missing, particularly permissions and real scheduling
- `docs/V03_RESULTS.md`: independently measured test evidence
- `output/`: reference demos, SQLite databases, event traces, reports and results
- `manifest.json`: SHA-256 and sizes for every packaged file excluding itself

## Critical security warning

The simulator trusts `actor="system"` from the local test harness and stores synthetic records in a replayable event ledger. **Never deploy this as a public API or store real medical/personal records in it.** The design is intended to test game-system causal consistency before we commit to a networking implementation.

Source is MIT licensed. TRANSCOSMIC lore, novels, art, game content and future asset licenses are separate. The existing live ANEVUM site and game remain untouched.
