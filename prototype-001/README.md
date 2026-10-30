# TRANSCOSMIC: SEVERANCE — Prototype 001

**Date:** 2026-10-28  
**Session:** ANEVUM.ANEVUM.BUILD.2026-10-28.001.SEVERANCE-PLAYABLE-FOUNDATION  
**Status:** Development source on a separate game branch; not an approved browser release or public online service.

This is the first deliberately narrow Godot 4.7.2/GDScript game project for the ANEVUM horror world. It does not replace the ANEVUM website. It shares no production account session, storage, D1 database, payment processor or privileged site API.

## Contents

- A navigable first-person industrial lab, courtyard, floodlights and original modular primitive geometry.
- One creature with server-driven visual detection, patrol, chase, attack and survivor respawn.
- Three recoverable data cases; collection and damage are decided by the server in multiplayer.
- One-player offline test and up to four private network players through Godot WebSocketMultiplayerPeer.
- Headless authoritative dedicated server; snapshots travel from server to clients.
- Durable recovered-case state on the **server only**, under its user data folder. Offline solo runs intentionally start fresh.
- Read-only HUD, flashlight, mouse look, sprint, and a private server connection panel.
- A smoke test and an isolated GitHub Actions source / headless-network workflow.

**No gameplay artwork, weapons, character accounts, mobile touch controls, audio, network authentication, secure WSS proxy, prediction, lag compensation or public deployment is claimed.** This build is meant to test the technical core before production art and massive-world ambitions.

## Open in Godot

Install the official **Godot 4.7.2 standard build**, then import this directory (containing project.godot) as a project.

Run the project for the title screen and choose SOLO TEST. The scene is currently an intentionally simple graybox, not representative of the final visual target.

Controls:
- WASD: move
- Mouse: look
- Shift: sprint
- E: recover nearby evidence
- F: flashlight
- Escape: release mouse; click scene to recapture.

## Private multiplayer, desktop

Start a dedicated server in a terminal:

    godot --headless --path prototype-001 -- --server --port=8910

For local connections, the server binds to 127.0.0.1 by default. Then run the project in a second Godot process and connect to ws://127.0.0.1:8910. Repeat for additional clients, up to four.

For a LAN-only experiment (behind trusted network rules) add --bind=0.0.0.0 to the server command. **Do not expose an unauthenticated prototype server to the public Internet.**

Run a noninteractive connection probe from another process:

    godot --headless --path prototype-001 -- --probe-client --port=8910

The client logs SEVERANCE_PROBE_PASS after it receives at least four authoritative world snapshots and its own survivor. This is not a substitute for browser/device playtesting.

## Browser constraint

Godot web export uses WebAssembly + WebGL 2 Compatibility rendering. Use the standard GDScript runtime. Actual browser export and physical Safari/iPhone testing remain *pending*. Hosted HTTPS pages must connect via wss:// to a separately configured secure game gateway. Do not redirect or expose ANEVUM member cookies to the game server.

## First milestone gates

1. Godot engine import / GDScript parse / solo smoke PASS.
2. Dedicated headless server + independent client four-snapshot probe PASS.
3. Desktop visual / movement / AI playthrough PASS.
4. Browser export and Chrome + Safari real-device testing PASS.
5. Only then create an isolated private game-launch route; never auto-enable public PLAY.

The first four gates are independent of the existing ANEVUM website release process.

## Open source

All source in this prototype is MIT-licensed. The geometry and code were authored for this project; there are no externally sourced game assets. Later third-party assets, licensed audio, trademarks and canon must be reviewed separately before distribution.
