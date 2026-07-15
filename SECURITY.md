# Security policy

## Supported surface

The default project uses anonymous public HTTP sources and does not require a
paid API key. Optional local collectors that depend on browser sessions are
disabled in GitHub mode.

## Reporting

Please open a private security advisory in the GitHub repository rather than a
public issue when reporting a credential leak, unsafe collector, or publishing
boundary bypass.

## Release checks

Before publishing or deploying:

1. run `python3 -m unittest discover -s tests -v`;
2. run `python3 scripts/quality_gate.py`;
3. run `python3 scripts/build_public.py`;
4. confirm that only `.github/`, collectors, scorer, scripts, tests, web,
   documentation, generic defaults, and `public-data/` are staged;
5. never push hidden refs, bundles, raw data, or a mirror of the local Git
   directory.
