# Changelog

## v0.1.0 — 2026-11-04

First release.

- **Safety is the product** — batch renames planned,
  verified and reversible:
  - **`plan DIR --scheme SCHEME`** — a pure dry run: the
    exact rename map plus any collisions, and a written
    promise in its own footer that nothing was renamed and
    no files were written. Exit 1 when the plan has
    collisions.
  - **`apply DIR --scheme SCHEME`** — regenerates the plan,
    re-verifies it, and only then renames. Any collision
    refuses EVERYTHING (exit 1) with the folder
    byte-identical to before — verified in the test suite by
    hashing the whole tree (every path + content,
    subfolders included) around refused runs. Renames run
    in two phases through temporary names, so a rename can
    never overwrite another file, not even mid-apply; a
    mid-apply OS error rolls every moved file back. A
    successful apply writes `.scaffolder-undo.json` with
    every old/new pair; an apply with nothing to rename
    writes no log, so an earlier apply stays undoable.
  - **`undo DIR`** — reverses the last apply exactly, from
    the undo log, pre-checked as a whole: a renamed file
    that has gone missing, or an original name that has
    been taken again, refuses the whole undo (exit 1,
    nothing changed). A successful undo removes the log. A
    corrupt log is a clean exit-2 error, never a silent
    "nothing to undo".
- **Three schemes**, with the name maths documented to the
  character: `slug` (stem lowercased, non-`[a-z0-9]` runs →
  one hyphen, empty stems → `file`, extension slugified the
  same way); `date-title` (the file's own modification
  date, local time, prepended to its slug; a slug already
  carrying that date is left alone, a different leading
  date is kept); `episode` (`SxxEyy` numbering over a
  natural sort — `ep2` before `ep10`, numbers past 99
  handled — with `--season`/`--start` offsets, the title
  kept with underscores → spaces, and a leading `SxxEyy`
  token from an earlier numbering stripped so re-runs never
  double it).
- **Narrow scope, stated on every run** — only regular
  files directly in the named folder. Subfolders are
  counted and reported, never entered or renamed; hidden
  files are left alone (the undo log included); symlinks
  are counted, never followed and never renamed, so nothing
  outside the folder can be touched.
- **Case-insensitive collision checks** — the filesystems
  most creators use are case-insensitive, so two targets
  differing only in case still collide; a target held by a
  file that is itself being renamed away is freed (a
  case-only rename like `IMG.jpg` → `img.jpg` applies
  cleanly).
- **`--json` on every command** — one JSON object with the
  same facts and exit codes as the text view; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`SKILL.md`** at the repo root for AI coding agents:
  commands, the scheme and scope rules at their exact
  edges, the JSON schemas, exit codes, and the honesty
  rules (a plan is not a rename; a refusal is the tool
  working, not a failure to route around).
- Bundled sample generator (`examples/make_sample.py`): a
  6-file messy folder (camera name, shouty podcast title,
  one already-clean name, a hidden file, a `raw/` subfolder)
  with explicit modification dates, every scheme map for it
  worked out by hand in the test-suite header.
- 53 stdlib-unittest tests, temp dirs only: the three
  scheme maps against hand-computed expectations, natural
  sort and 100+ episode numbering, scope rules (subfolders,
  hidden files, symlinks), collisions in all three forms,
  tree-hash proof that plans/refusals change nothing and
  that apply → undo restores the tree exactly, and the
  clean-error shape in both modes.
- Pure Python standard library; local only; no network
  code; MIT licence.
