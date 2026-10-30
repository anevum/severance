# TRANSCOSMIC: SEVERANCE

SEVERANCE is an ANEVUM game in development. This repository currently contains **Prototype 001**, an isolated Godot graybox for testing core movement, creature behavior, and a private server. It is not a finished game or a public multiplayer service.

## Prototype 001

The source is in [prototype-001](./prototype-001/README.md). Open that directory as a Godot project using the version specified in its README. It contains the original prototype, tests, and MIT license.

The headless server is unauthenticated and binds to loopback by default. Do not expose it to the public Internet. Mobile controls, network security, art, audio, and many other game features remain unfinished.

## Source provenance

This is a source snapshot from [anevum-web draft PR #788](https://github.com/anevum/anevum-web/pull/788), commit `bbf0579a88e6c7229cb1f2eb492812c3c2a473ea`. The original branch and its commit history remain in that repository. This snapshot does **not** reproduce the original commits as ancestors in this repository. The only content change within the imported prototype is replacing the old repository-relative path in its README. The standalone workflows adapt the original verification workflows to this directory and do not deploy.

The separately developed world-state lab has not yet been reconciled with this prototype. Preserve both until their relationship and current status are verified.

Session: `ANEVUM.OPS.PACKAGE.2026-10-30.002.COMPLETE-GITHUB-RESTRUCTURE`
