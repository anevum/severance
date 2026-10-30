# Scenario-to-implementation matrix

All listed tests were run as **offline executable rules tests**, not end-user playtests. Each `test_sNN` name maps to a `unittest` function in `tests/test_worldstate.py`.

| Story scenario | Exact test | Observed offline result | Not yet verified |
| --- | --- | --- | --- |
| S01: mortal character dies, new survivor begins | `test_s01_mortal_death_new_character_no_knowledge_transfer` | Old character remains terminal, estate preserved, new identity has no hidden knowledge | Final respawn UX and immigration logic |
| S02: real physical medical rescue | `test_s02_rescue_same_physical_character` | Co-located responder consumes kit, same character stabilizes/recovers | Actual in-world medicine/transport/time |
| S03: disconnect during travel | `test_s03_disconnect_reconnect_keeps_identity_and_location` | Identity and coordinates/graph location persist; disconnected action denied | Network outages, timers, combat logging |
| S04: player abuse cannot reset by dying | `test_s04_account_sanction_outlives_character` | Account sanction survives character death, blocks new entry | Real authentication, moderation, appeals |
| S05: protected source records | `test_s05_private_clinical_evidence_not_public` | Private source hidden; clinical classification cannot be casually published | Production data privacy and consent management |
| S06: two organizations attempt one repair | `test_s06_two_repair_attempts_only_one_state` | Repair debits once, stale duplicate fails | UI, vehicle deliveries, player groups |
| S07: wilderness theft without omniscient conviction | `test_s07_item_theft_needs_physical_custody_no_global_conviction` | Unattended item transfers only if co-located, legal owner retained, claim starts from a report | Full item ownership law and forensics |
| S08: attacks on public dam/hospital | `test_s08_dam_and_hospital_not_one_click_targets` | Generic obstruction disallowed even when physically present | Real coordinated security/sabotage simulation |
| S09: aged bioadaptive work-unit | `test_s09_biohybrid_requires_energy_and_nutrients` | Cannot run without physical support resources | Actual powered hardware/biological processes |
| S10: 1,000-user convergence | `test_s10_hotspot_1000_players_is_not_claimed` | Explicitly checks that no graphical/large-load API is claimed | **NO multiplayer load test executed** |
| S11: off-screen community stock | `test_s11_dormant_population_supply_ledger` | Bounded aggregate step advances food/water, rejects oversized jumps | Food ecology, real calendar, migration |
| S12: player offline, organization continues | `test_s12_offline_org_asset_not_deleted` | Public organization and worksite remain after disconnect | Real claims maintenance/anti-raid scheduling |

**Beyond S1–S12:** the other tests cover bridge rerouting, contract exactly-once payment, in-town protections, material limits, role restrictions, item movement, rollback before commit, ledger and materialized-state corruption detection, deterministic replay, persistent SQLite reopen and **two independent SQLite writer connections racing to repair the same public asset**. The latter test accepts one repair and rejects the stale concurrent writer; it is NOT a distributed multi-server consistency test.

Do not report '12/12 multiplayer scenarios passing'—the precise claim is that *12 documented scenario checks exist in a set of 43 offline tests, with S10 explicitly asserting lack of load testing*. The code is a rules proof, not an online product.
