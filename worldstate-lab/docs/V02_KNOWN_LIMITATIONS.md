# V0.2 known limitations and next engineering gates

## This is NOT a multiplayer server

No login authentication, trusted-session verification, websocket transport, rate limiting, anti-cheat, real player physics, Godot integration, WebGL rendering, remote service, Cloudflare deployment, distributed authority, or UI has been introduced. The `system` actor is an unauthenticated offline fixture. It must never be an API parameter supplied by users. A local SQLite write lock is not distributed consensus.

## Timed clinical states are fictional abstractions

- Injury deadlines are *not automatically scheduled* when wall-clock time passes. A trusted `MedicalCaseExpired` event must be emitted, and the sandbox has no scheduler or autonomous medical workers.
- A stabilized patient does not continue physiologically deteriorating during transport. This simplifies a complex issue and must be replaced or deliberately bounded before realistic survival claims.
- Multi-leg medical transports use graph nodes and a synthetic ETA coefficient. No actual ambulance, staff licensing, medical consent, bleeding, surgery, medication, triage, trauma-rehabilitation physiology or care cost is modeled.
- A transport becomes aborted when its responder dies, but no reassignment/recovery workflow is currently available; a case can remain stranded.
- A patient and medic are represented at the departure node until travel completes; there is no interpolated in-flight vehicle position and no congestion.
- `MedicalCaseRecovered` is a trusted fixture action. Production would require actual clinical qualifications, patient authorization and resource use. Death remains irreversible.

## Logistics remain a narrow first proof

- One physical depot per organization is supported. A geographically large organization needs multiple warehouse IDs and permissions, not one singleton depot.
- Freight requires a direct edge on departure; reroute can include up to six connected graph edges only after a guarded original route is blocked. Multi-leg routine deliveries and reroutes after an initial reroute remain unmodeled.
- Freight is effectively at the route's origin until delivery for bookkeeping. No partial progress, location-specific interception, fuel stops, vehicle collisions, accidents, congestion, spoilage or escort protection.
- Simulated carrier fuel is an abstract unit. Refueling from `fuel_cell` uses a made-up factor of 20 fuel units each. Real energy storage, battery temperature, grid power or freight weight are not modeled.
- Cargo stuck during transit remains in the persistent shipment table; automated salvage, return-to-sender, delayed customs, alternate carrier pickup and claims arbitration remain for later phases.
- Source `StockProvisioned` and `CarrierRegistered` are trusted fixture-only material injections for testing. They are **not** legal production services that players can request to create wealth.
- Regional food/water meters are aggregate resource counters using arbitrary production and consumption units. There is no actual food storage degradation, farms, populations aging, wages, labor markets or commodity price equilibrium.
- The old abstract `StockTransferred` event still exists when registered depot topology is absent, for legacy trace compatibility. Deploying V0.2 on a real server would require a phased migration policy.

## Persistence / integrity is a local demonstration

- V0.2 adds tables while retaining the V0.1 event encoding. A forward-compatible event-schema registry, unknown-event quarantine, snapshot versioning and migration rollback have **not** been designed.
- SQLite durability is measured with simulated in-process pre-commit exceptions and restarts, not filesystem loss, power outage, network partition, disk corruption, malicious administrator, multi-region failover, or untrusted concurrent external services.
- SHA-256 chaining verifies consistent event history against a known reference; a malicious database owner can rewrite the entire ledger and all hashes.
- A V0.1 snapshot's **materialized-state hash changes** when V0.2 adds empty tables; its V0.1 event chain hashes remain unchanged. Do not falsely compare the old/new state hash without a schema-aware comparison.
- Repeatable randomized stress measures offline transaction logic, not 1,000 connected users, concurrency at one hub, network throughput, device memory or hosting cost.

## Canon and publication

The planet Eloden, original neighborhoods, work units and gameplay rules are still working game ideas. The experiment does not decide the actual biological-intelligence incident, the exact year of play, the ethical status of any engineered organism, the legal road shutoff, or literary canon. No project source or private wiki material should be publicly merged just because tests pass.

## Next logical proof (V0.3)

1. Introduce real versioned events and explicit schema migrations while preserving V0.1/V0.2 traces.
2. Separate trusted server/system authority from untrusted client intents with permission-scoped certificates.
3. Model scheduler-driven biological/time-dependent deadlines, bounded idle time and safe reconnect.
4. Enable multi-depot, multi-leg freight with carrier/crew custody and realistic partial progress.
5. Add evidence/medical consent, civic territory rights and actual permissions to clinical and salvage workflows.
6. Run property-based fuzzing and interrupted file/recovery tests, then real client/server integration tests **only after** the user ends the production hold.
