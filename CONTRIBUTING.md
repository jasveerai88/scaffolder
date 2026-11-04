# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** scaffolder's promise is
  "clone and run". Pull requests that add a third-party
  dependency will not be merged.
- **Local only.** No network calls, no telemetry, no uploads
  of user files. The tool reads names and mtimes in one
  folder and renames within it; it never sends anything
  anywhere.
- **Safety rules are the product — never weaken them.**
  `plan` must write nothing. `apply` must stay
  all-or-nothing: any collision refuses everything, and the
  folder must be provably unchanged (the suite hashes the
  whole tree around refused runs — keep those tests green).
  Renames must stay two-phase so no step can overwrite a
  file, and undo must stay whole-set pre-checked. A PR that
  adds an "apply the non-colliding ones anyway" mode will
  not be merged.
- **Scope stays narrow.** Top level of one folder only;
  subfolders never entered, hidden files and symlinks never
  touched. Recursion, cross-folder moves and following
  symlinks are out of scope by design, not missing features.
- **Scheme maths stay exact and documented.** The slug,
  date-title and episode rules are stated to the character
  in the README and SKILL.md, each pinned by tests against
  hand-computed names. Changing one needs the README, the
  changelog, the SKILL.md rules and the tests updated
  together.
- **Collision checks stay case-insensitive.** Most creator
  filesystems (macOS, Windows) are case-insensitive; a
  "fix" that makes the checks case-sensitive reintroduces
  the overwrite this tool exists to prevent.
- **Both directions tested.** A behaviour change needs a
  test where good input succeeds and bad input is refused
  cleanly — not just one side. Expected names need
  hand-computed values, not names copied from the tool's
  own output.

## Getting started

```bash
git clone https://github.com/jasveerai88/scaffolder
cd scaffolder
python3 -m unittest discover -s tests -v
python3 examples/make_sample.py /tmp/scaffolder-demo
python3 src/scaffolder.py plan /tmp/scaffolder-demo --scheme slug
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if
   the CLI output changes.
