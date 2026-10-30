# SEVERANCE Engineering Boundaries — Prototype 001

## Architecture

The same Godot scene runs in three modes:

- **Solo:** standalone offline run. Immediate local authority, no server or shared progress.
- **Headless server:** authoritative physics, player intent validation, creature behavior, collection/death, snapshot relay, recovered-case file persistence.
- **Client:** sends only player movement intent and interaction requests, and renders server-authoritative snapshots.

RPC authority resides at /root/Main on all peers. Clients do not send world positions, damage, items or recovery records. The server caps horizontal axes, clamps yaw, rate-limits movement RPCs, checks collection range, and owns all death / respawn decisions. Physical navigation, server heartbeat and loaded-state persistence are **not** production hardened.

Transport: WebSocket on port 8910, default bind 127.0.0.1. The initial server has **no identity or authorization handshake**. It is suitable only for trusted private development. An Internet-facing WSS/reverse proxy and short-lived account-bound server ticket are planned later, with end-to-end isolation tests.

Snapshots run at roughly 13 Hz. Client interpolation is visually smoothed, but *not* predicted. This is adequate for verifying state replication; smooth high-tempo horror combat needs reconciliation and more careful bandwidth/lag testing before public use.

## Browser rendering

Compatibility renderer and GDScript keep WebGL 2 export possible. All prototype geometry is built from Godot BoxMesh/CapsuleMesh primitives and local materials. There are no external fetches, shader plugins or textures. Visual controls are platform-native; touchscreen and gamepad UX come after the physical-browser proof.

## Persistence boundaries

The world file contains only a version and the identifiers of already recovered evidence cases. It does not store actual personal/player identity. The file is written only by the authoritative dedicated server. Solo mode begins from its initial default state and performs no disk save. Production persistence must eventually use ANEVUM-approved authenticated world data, independent of private website/user storage.

## Canonical gameplay loop

1. Spawn in the laboratory entry.
2. Navigate to evidence cases inside/outside the compound.
3. An AI stalker detects survivors with physics line-of-sight.
4. Survivors can run and use light while the server handles movement and attacks.
5. Lethal damage returns the survivor to spawn.
6. Recovered cases remain recovered after **server restart**.

## Out of scope

Aesthetic finish, combat/weapons, inventory, friends, character creation, real user authentication, world streaming, reliable durable event ledger, multiplayer anti-cheat enforcement, MMO sharding, live deployment, game marketing, public website launch and mobile controller testing.

## Next implementation steps

- Get CI and desktop visual proof passing; fix engine warnings.
- Export single-threaded Web build; test actual browser hardware and WSS.
- Add server-correct collision/AI navigation, reliable player-event replay, and first survival objective.
- Bring in original modular environment art and animated creature rig; benchmark browser frame pacing.
- Integrate with ANEVUM behind explicit tested launch permissions, without touching mainline web infrastructure prematurely.
