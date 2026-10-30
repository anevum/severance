# V0.2 - Rules architecture and event semantics

## Scope

This is an additive evolution of the SQLite event-state proof (V0.1), *not* a replacement. V0.1's original 64-event JSONL file and SQLite database remain readable. The local schema is marked with `PRAGMA user_version=2` and creates additive tables; the original event hash encoding and order are untouched. **This is not a versioned event API migration framework**, which remains a future project.

Each event has a unique event ID, a nondecreasing *logical* tick, an actor label, a kind, and canonical JSON payload. In `World.apply`, one SQLite `BEGIN IMMEDIATE` transaction mutates materialized rows and commits one hash-chain event, or rolls back both. Identical event-ID replay is a no-op; conflicting reuses are rejected. A clean state is reconstructed by replaying accepted events in order. Global `audit_state()` checks the hash chain and reconstructed state.

The special actor `system` is only a locally trusted test fixture, **not** a network permission or end-user claim. Do not expose it directly to a game client.

## Additive tables

- `medical_cases`: one active case per survivor (partial uniqueness); deadline, status, hospital and milestone ticks. Recovered cases may be followed by new episodes.
- `medical_transports`: explicit graph hop with medic, patient case, ETA, and completed/aborted status. Multiple hops may belong to one case.
- `depots`: one registered physical location for an organization holder in V0.2.
- `region_hubs`: map nodes for receiving region resources.
- `carriers`: physical cargo carrier position, owner, finite capacity/fuel and ready/in-transit status.
- `shipments`: cargo debited from source stock upon departure and credited **only upon confirmed physical arrival**.
- `carrier_moves`: empty carrier's return travel with fuel cost, ETA and movement status.
- `shipment_reroutes`: recorded replacement itinerary when the originally guarded route is obstructed; additional fuel and ETA apply.

## New medical transitions

`MedicalCaseOpened`: a trusted dispatcher associates an incapacitated survivor with an operating hospital and a bounded rescue deadline (no more than 120 later logical ticks).

`MedicalCaseStabilized`: an actual colocated responder spends a field kit by the deadline, and the patient becomes stabilized. A second stabilization cannot pay a second reward or duplicate supplies.

`MedicalCaseExpired`: a trusted event after the deadline terminally ends an **unstabilized** life, moves carried items into estate custody, and prevents later rescue.

`MedicalTransportStarted`: a responder with a transport kit and a stabilized colocated patient starts a concrete graph edge. It has a minimum ETA computed from graph distance.

`MedicalTransportCompleted`: only a trusted post-ETA event that verifies route, responder and patient state moves both people and carried items. At an operating hospital, status becomes `admitted`; otherwise it becomes `stabilized` for another hop.

`MedicalCaseRecovered`: trusted completion after at least ten post-admission ticks, at an operating hospital, restores **that same still-living** survivor. No resurrection.

A `CharacterDied` event closes an open case and aborts a traveling medical transport involving the deceased patient or responder. A new *other* human may join through the existing account mechanism.

## Physical supplies and logistics

`DepotRegistered`, `RegionHubRegistered`, `CarrierRegistered` establish the fictional economic topology. All coordinates are the known Crown Valley *route graph*, not 3D collision coordinates.

`ShipmentDispatched`: requires a quartermaster physically at the source registered depot, a ready carrier owned by that organization, an authorized destination depot/region hub and a direct open route. Stock is debited once, fuel is consumed and the cargo exists in an explicit in-transit record.

`ShipmentDelivered`: requires logical ETA elapsed, carrier consistency and the route (or an accepted alternate route) still traversable. The receiver's stock or food/water ledger gets the quantity exactly once.

`CarrierReturnStarted` and `CarrierReturnCompleted`: physically move an empty carrier back to its original owner's depot, consuming finite fuel and elapsed logical time. `CarrierRefueled` requires a colocated authorized quartermaster and available fuel cells.

`ShipmentRerouted`: only when the old guarded route is currently obstructed and there is a connected, acyclic, currently open alternate itinerary. A new ETA and additional fuel debit are recorded. The illustrative Westbank-to-Civic alternative is **6.610 km** via Lower Crossing instead of **2.017 km** across the central bridge. No teleports.

`RegionProductionChanged`: a trusted fixture may adjust nonnegative regional food/water production rates. `RegionAdvanced` retains V0.1's deliberately coarse bounded aggregate consumption.

`StockTransferred`: remains for backwards-compatible V0.1 abstract transfers when no physical depot topology exists. Between two distinct *registered physical organization depots*, it is now disallowed. Such commerce must use shipping. This avoids instant intercity materials after the freight system has been adopted.

## Invariants and corner cases

- No negative stock, regional reserves, biological support, cargo quantity or carrier fuel.
- One carrier cannot simultaneously carry two shipments or return and ship at the same time.
- A failed dispatch, delivery, reroute, early hospital recovery or simulated crash leaves no partial committed state.
- A transport route requires actual connected graph edges and cannot pass a blocked guarded bridge.
- A critically ill patient cannot use ordinary self-movement to bypass active medical transport restrictions.
- Recovery is an event in the existing world, not a respawn or player-specific branch.
- Evidence and anonymous accusations are not globally omniscient.
- The existing V0.1 world trace, including its event hashes, can be replayed with additive V0.2 empty extension tables.

## Timings are *logical ticks*, not medical protocols

The `tick` is a nondecreasing integer used for event ordering. The simulation does not claim that each tick equals one minute, a real heartbeat, a travel second, a weather step, or Eloden's 26.4-hour civil day. Medical deadlines and route-duration coefficients are invented test thresholds, **not a clinical recommendation or actual walking-speed model**. Clock synchronization, passage of inactive time, credible travel, injury physiology and treatment staff permissions remain future work.

## Why cargo matters

V0.1 proved atomic stock bookkeeping but could transfer inventory instantly across arbitrary organizations. The V0.2 physical depot and carrier path introduces separation between a source stock, in-transit cargo, and the receiving ledger. Test accounts verify conservation across those components. An interrupted bridge causes *a real shipment to remain undelivered* until the crossing reopens or a more expensive alternate path is accepted.
