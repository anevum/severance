# TRANSCOSMIC: SEVERANCE

SEVERANCE is a parked ANEVUM family creative project. The prototypes below are preserved for possible future work; there is no current release or active development commitment. It is not a finished game or public multiplayer service.

## Prototype 001

[Prototype 001](./prototype-001/README.md) is an isolated Godot graybox for testing movement, creature behavior and a private server. The server is unauthenticated and binds to loopback by default; do not expose it to the public Internet. Mobile controls, network security, art, audio and many other features remain unfinished.

## Offline world-state lab

[World-state lab V0.3](./worldstate-lab/README.md) is a separate Python and SQLite preproduction simulation. It explores rules and replay; it is **not integrated with the Godot prototype** and must not be used for real personal or medical records. Run its tests with `python -m unittest discover -s tests` from the lab directory.

## Source provenance

The Godot source snapshot comes from [anevum-web draft PR #788](https://github.com/anevum/anevum-web/pull/788), commit `bbf0579a88e6c7229cb1f2eb492812c3c2a473ea`. The original branch and its commit history remain in that repository; the snapshot does not reproduce those commits as ancestors. The prototype README and standalone verification workflows adapt repository-relative paths. The workflows do not deploy.

The lab source was recovered from the V0.3 development archive. Generated outputs, databases and the archive manifest are not included; the original archive remains the reference for those artifacts. Each project retains its MIT license. Review the relationship between these independent experiments before integrating them.

Session: `ANEVUM.OPS.PACKAGE.2026-10-30.002.COMPLETE-GITHUB-RESTRUCTURE`
