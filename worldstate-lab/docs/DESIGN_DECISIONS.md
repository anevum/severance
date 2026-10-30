# Design decisions and preproduction holds

| Decision | V0.1 working approach | Approval status |
| --- | --- | --- |
| Character mortality | Permanent actual character death; player returns as *different* survivor | Working proposal |
| Active character count | One living character per account in the rules experiment | Prototype-specific, not approved game rule |
| Medical response | Real co-located rescue, stabilization, rehabilitation; no resurrection | Canon-compatible proposal |
| Equipment after death | Physical items transfer to estate custody | Legal/UX rules still open |
| PvP | Possible conflict with local laws, no omniscient reputation | Exact violence/loot policy unresolved |
| Public asset repair | Verified inspection, roles, material debit, durable state | Work order rules need richer design |
| Public-dam sabotage | Generic one-click sabotage denied | Later incident rules must be developed |
| Browser performance | Not addressed by this laboratory | No device performance proof |
| One world | Ledger state does not auto-wipe; 13 local route edges | No server handoff proof |
| Eloden era | No absolute gameplay year chosen | Compare T+2, T+25, T+100 |
| Map size | Candidate 8 × 8 km Crown Valley | Not physically/technically locked |
| Creature ecology | Support resource ledger only | Physics, individual AI and lineage unresolved |
| Payment/business | None; standalone free, open-source lab | No live product checkout |
| Godot build / CI | Explicitly untouched | Existing prototype remains frozen |

## Minimum next authorized design/proof milestone

**P2a — executable domain model, now available:** 43 offline tests, deterministic replay, atomic event ledger, sample SQLite + event trace, 64-event demonstration.

**P2b — next design step:** pressure-test identity, damage and civic laws against longer lifetimes and more sophisticated material transfers. Add event stream versioning, secure actor credentials outside the trusted lab, session/reconnect windows and monotonic clock semantics in a separate technical research branch—not in the paused Godot gameplay project.

**P3 — first actual game vertical-slice design:** decide start date and character loop, identify the first 1 km² benchmark scene inside the Orrel Civic–Crown Research Corridor, prove browser rendering/hardware constraints, then explicitly authorize a Godot or other engine prototype. Do not deploy it as an unlocked public world before testing.
