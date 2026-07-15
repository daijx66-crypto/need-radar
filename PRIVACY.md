# Privacy boundary

Need Radar is local-first. The public project publishes only source code,
generic defaults, sanitized derived rankings, a compact run status, and compact
ranking history.

The following data must stay local and is ignored by Git:

- raw collected responses and caches;
- internal evaluation sets and audit reports;
- `scorer/profile.json` and exported feedback;
- local paths, logs, browser state, cookies, tokens, and API keys.

The web interface stores explicit feedback (`useful`, `noise`, `later`) in the
browser's `localStorage`. It does not send feedback to a server. Users may
export that local feedback as JSON and delete it by clearing site data.

`scripts/build_public.py` creates public data from an explicit allowlist,
redacts email-like values, rejects local paths and common secret patterns, and
truncates third-party excerpts. Publishing raw `data/` or using `git push
--mirror` is outside the supported release process.
