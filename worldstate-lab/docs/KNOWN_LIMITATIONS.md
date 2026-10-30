# Known limitations and truth-in-status checklist

## Not implemented at all

- Account authentication, access tokens, federation, game login, session authorization and cryptographic signing.
- Real dedicated game server, actual networking, two online human clients, latency, lag compensation or interest management.
- Godot integration, real WebGL 2 terrain/physics, animation, original creature visuals, UI, touch/gamepad/haptics or world streaming.
- Geographically partitioned authority, distributed exactly-once event transactions and seamless cell handoff.
- Character movement timing, route geometry collision, slopes/floods, fatigue, vehicles or high-resolution maps.
- Actual creature brains, genes, epigenetics, heritage, welfare, sensory learning, metabolism or ecology.
- Clinical medicine beyond a simplified health state machine; patient consent and privacy authorization beyond one simple evidence classification.
- Legal adjudication, crime investigation, witness reliability, moderation appeals and autonomous NPC responses.
- Production item economy (manufacturing, real stock shipments, vehicle cargo capacity, skilled labor time, wear, warranties, rehabilitation and estate claims).
- Realistic population economics, famine/migration, years of chronology or guaranteed server-updated dormant NPC state.
- Production backups, external trusted audit anchoring, schema migrations and operational monitoring.
- Real browser/console compatibility, 32/64/500/1,000-player capacity or production cloud-hosting costs.

## Implemented but intentionally simplified

- The trusted `system` actor is a fixture-only capability; **never use it as an actual public API role**.
- SHA-256 chaining is useful for verification against a trusted copy. It does not prevent a malicious database admin from rewriting the chain.
- SQLite `BEGIN IMMEDIATE` serializes one database's writers; it is not a distributed consensus protocol.
- `CharacterMoved` enforces route adjacency and bridge states but not walking time, actual path traversal, physical speed or multiplayer visibility.
- Stock transfers are abstract authorized custody changes with no warehouse location/transport-time enforcement.
- `CharacterDied` sends held items to estate custody. Probate, body access, medical consent and estate recovery are not modeled.
- The high-consequence hospital/dam restriction is a conservative gameplay *placeholder*, not a claim those facilities could never be damaged.
- Event `tick` is a monotonic ordering integer; it is not yet the canonical 26.4-hour Eloden civil clock.
- Regional production/consumption uses arbitrary resource units per 100 residents per tick for deterministic testing.
- Current rules allow one living survivor per account. This is an explicit experimental decision, not an approved gameplay obligation.
- The demo has 64 committed events—not 64 active players, 64 simulations, or 64 instances.
- The rule tests do not verify all possible concurrent database races or adversarial client behavior.

## Before calling it a game feature

Demonstrate real network admission, authorization, authoritative position validation, live client visibility, browser memory/performance, persistence after server crash, and real-player usability. Always distinguish *code implemented in isolated offline lab* from *integrated and deployed in the ANEVUM game*.
