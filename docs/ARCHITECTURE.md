# Need Radar architecture

## Product contract

Need Radar answers three different questions without mixing their evidence:

1. **Needs** — who is paying a recurring cost, in what situation, and why an
   alternative may be worth paying for.
2. **Important changes** — what changed recently enough to affect a product or
   technical decision. A trend is not demand proof.
3. **Builders** — what curated builders shipped, learned, or changed. A popular
   post is not automatically an important builder signal.

The home page is an editor, not an infinite feed. Items must pass a per-kind
score threshold and freshness window. There is no minimum quota for a kind, so
an empty day is valid. Per-kind maximums prevent one feed from monopolizing the
five `now` slots.

## Daily flow

```text
portable public collectors             local browser collectors
          |                                      |
          +------------ normalized signals ------+
                                 |
                   deterministic demand gate
                                 |
              needs / changes / builders (separate)
                                 |
             freshness + threshold + kind caps
                                 |
                 private local personalization
                                 |
          sanitized public data + compact history
                                 |
                         GitHub Pages
```

`NEED_RADAR_MODE=github` excludes browser-session collectors both from execution
and from raw-file scoring. This second boundary is important: stale local raw
files must never leak into a public CI result.

## Quality and learning

- Demand clustering is conservative: matching intent, at least three strong
  shared keywords for a same-source merge, and four for a cross-source merge.
- A need uses the newest evidence timestamp; generated time is never substituted
  for source time.
- Quality gate rejects stale `now` items, invalid links, duplicate stable IDs,
  mismatched run timestamps, failed refreshes, and attention-budget overflow.
- Browser feedback is explicit and bounded. It can move one item later, mark it
  as noise, or add a small useful boost. Source and kind learning are capped.
- `scripts/analyze_feedback.py` converts an export into review-only suggestions;
  it never edits a profile, scoring rule, or source code.

## Failure semantics

Collector state is one of `success`, `empty`, `failed`, or `skipped`.

- `success`: exited zero and wrote a fresh, non-empty raw file;
- `empty`: exited zero and wrote a fresh zero-item raw file;
- `failed`: non-zero, timeout, malformed/missing output, or stale output;
- `skipped`: intentionally unavailable in the current mode.

The overall refresh is `failed` when scoring fails or no source produced data,
`degraded` when a required source is missing, and `success` otherwise. Optional
empty sources remain visible without pretending to be successful sources.
