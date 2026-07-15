# Project audit — 2026-07-15

## Verdict before this iteration

The product concept was strong, but the repository was not ready to be public
or trusted as a daily system.

What was already good:

- raw signal, demand, watchlist, attention, and history were separate concepts;
- original demand score was kept separate from personalized attention score;
- deterministic gating, stable IDs, atomic snapshots, source links, stale/empty
  UI states, and a meaningful test base already existed;
- the interface protected attention better than a conventional card wall.

What blocked release:

- there was no GitHub workflow, ignore policy, license, or public-data boundary;
- a collector could catch an error, write zero items, exit zero, and look green;
- scoring failure did not necessarily fail the whole refresh;
- GitHub-incompatible collectors were skipped at execution time but their stale
  local raw files could still be scored;
- important changes, builder posts, and needs competed on incompatible score
  scales, while a minimum-kind quota could force weak content into `now`;
- evidence age was replaced by generation time for needs, so old content could
  look new;
- two-keyword clustering merged unrelated topics;
- no explicit feedback loop or reproducible precision/recall gate existed;
- raw, caches, reports, local profiles, and derived public data had no enforced
  publishing boundary.

## Changes made

- Added an honest `success / empty / failed / skipped` collector model and
  `success / degraded / failed` run model.
- Added a reproducible GitHub mode and excluded local/session sources at both
  execution and scoring boundaries.
- Integrated AI HOT selected items, current hot topics, fingerprint/version
  checks, permalink-first links, and attribution using the public contract.
- Integrated Follow Builders X, blog, and podcast feeds, with short-reply and
  promotion filtering.
- Added evidence timestamps, freshness windows, conservative clustering,
  per-kind thresholds, and maximum kind caps with no minimum quotas.
- Added browser-local feedback with bounded local re-ranking, export, and a
  review-only analysis script.
- Added a versioned deterministic evaluation set, quality gate, sanitizer,
  compact public history, GitHub Pages build, daily workflow, license, privacy,
  security, attribution, and publishing documentation.

## Current evidence

- Unit and contract tests cover semantic gating, clustering, freshness,
  attention budgets, source parsing, refresh status, public sanitization,
  feedback bounds, and quality-gate failure cases.
- The versioned demand-gate fixture reports precision and recall and blocks the
  daily workflow below the configured floor.
- A real GitHub-mode refresh is required after scoring-policy changes; the final
  run status and `public-data/status.json` are the authoritative record.

## Remaining risks

- Public endpoints can change or throttle; degraded state is observable but
  cannot guarantee a third party's availability.
- Synthetic evaluation precision is a regression guard, not proof of real-world
  Top-5 precision. Real feedback exports should be reviewed and added as
  sanitized cases over time.
- GitHub scheduled workflows may run late and public schedules can be disabled
  after repository inactivity.
- The repository has not been remotely created, pushed, or deployed. Those are
  intentionally pending an explicit final publication confirmation.
