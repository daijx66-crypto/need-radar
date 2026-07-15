# GitHub publishing checklist

The repository is locally prepared for the approved public boundary A. This
document does not authorize creating a remote or pushing it.

## Public allowlist

- `.github/workflows/daily-radar.yml`;
- `collectors/`, except ignored local/session artifacts;
- `scorer/score.py`, `scorer/attention.py`, `profile.default.json`, and `persona_rubric.default.json`;
- `scripts/` Python and shell tools, except the local LaunchAgent plist;
- `tests/`, `web/`, `docs/`, `README.md`;
- `LICENSE`, `PRIVACY.md`, `SECURITY.md`, `THIRD_PARTY.md`;
- sanitized generated `public-data/`.

## Must not be public

- `data/raw/`, `data/cache/`, `data/eval/`, internal `data/history/`;
- `data/needs.json`, `data/last_run.json`;
- `reports/`, screenshots, `.trash/`, `.gstack/`, `demo/out/`;
- `scorer/profile.json`, `scorer/persona_rubric.json`, feedback exports;
- local scheduling files, browser state, logs, tokens, cookies, or local paths;
- hidden local Git refs or a Git mirror/bundle.

## First-time GitHub setup

After the owner approves the exact staged file list:

1. create an empty GitHub repository without generated README/license files;
2. push only the current branch — never `git push --mirror`;
3. in **Settings → Pages**, choose **GitHub Actions** as the source;
4. in **Settings → Actions → General**, allow workflows to read and write the
   repository so derived `public-data/` can be committed;
5. run **Daily Need Radar** manually once and inspect its test, refresh, quality,
   sanitizer, commit, and deploy steps;
6. open the resulting Pages URL on desktop and mobile before treating it as
   live.

## Time contract

User intent is every day at **08:37 Beijing time** (`Asia/Shanghai`). The
workflow submits `cron: "37 8 * * *"` with `timezone: "Asia/Shanghai"`; there is
no UTC conversion in the file. Scheduled GitHub runs can be delayed by runner
load, so `public-data/status.json` is the authoritative actual completion time.

## Local release verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
NEED_RADAR_MODE=github python3 scripts/refresh.py
python3 scripts/quality_gate.py
python3 scripts/build_public.py
python3 -m http.server 8910 --directory dist
```

Before push, inspect `git status --short` and the staged manifest again. The
first remote creation/push remains a separate, explicit confirmation step.
