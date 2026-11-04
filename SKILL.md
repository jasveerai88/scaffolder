---
name: scaffolder
description: Plan and apply SAFE batch renames in one media folder. `plan DIR --scheme slug|date-title|episode` is a pure dry run — the exact rename map plus any collisions, writing nothing. `apply` regenerates and re-verifies the plan, refuses EVERYTHING (exit 1, folder byte-identical) on any collision, renames in two phases through temporary names so nothing is ever overwritten, and writes `.scaffolder-undo.json`. `undo` reverses the last apply exactly, pre-checked as a whole (a missing renamed file or a re-taken original name refuses it, exit 1). Schemes: slug (lowercase-hyphen, extension lowercased), date-title (the file's own mtime date + slug), episode (SxxEyy in natural sort order, title kept, --season/--start offsets). Only regular files directly in DIR — subfolders are never entered, hidden files and symlinks never touched; collision checks are case-insensitive. Use when tidying camera dumps, downloads or episode asset folders. Exit 1 is a refusal with a fix list, not a failure.
---

# scaffolder — agent skill

## Purpose

Batch renaming is where files get lost: two names map to
one target and the second rename overwrites the first.
scaffolder makes the rename boring on purpose — a dry-run
plan, an all-or-nothing apply verified twice, a two-phase
rename that cannot overwrite, and an undo log that reverses
the apply exactly. Pure Python standard library; local
only; one folder at a time, top level only.

**The safety core of this tool:** `plan` writes nothing at
all. `apply` with any collision renames nothing at all.
`undo` that cannot fully restore renames nothing at all.
Every refusal is a complete, exact fix list — the names
involved — never a partial result to clean up.

## When to use / not use

Use when:
- A folder of media (camera dump, downloads, episode
  assets) needs consistent names: `plan` to see the map,
  `apply` to do it, `undo` if the result is wrong.
- A pipeline needs a yes/no before renaming: `plan` exit 0
  with an empty `collisions` list means the apply will go
  through as shown; exit 1 names every collision.

Do NOT use when:
- The tree is nested and you want recursion — scaffolder is
  top-level only, by design. Run it once per folder.
- A target name the tool reports as a collision is "fine by
  you" — the tool will still refuse, correctly. Rename or
  remove the blocking file yourself, then re-run. Never
  rename files around the tool to defeat a collision it
  reported; that is exactly the accident it exists to
  prevent.
- You need file moves between folders, copying, or content
  changes — renames within one folder only.

## Commands

```bash
# Dry run — the exact map + collisions; writes nothing
python3 src/scaffolder.py plan DIR --scheme SCHEME \
    [--season N] [--start N]

# Rename — re-verified; any collision refuses everything;
# writes DIR/.scaffolder-undo.json
python3 src/scaffolder.py apply DIR --scheme SCHEME \
    [--season N] [--start N]

# Reverse the last apply exactly, from the undo log
python3 src/scaffolder.py undo DIR
```

Every command supports `--json`. `--season` / `--start`
(defaults 1 / 1) affect only the `episode` scheme and must
be ≥ 1.

## Schemes (exact)

- **slug** — stem lowercased, every run of characters
  outside `[a-z0-9]` becomes one hyphen, edge hyphens
  stripped; an empty result becomes `file`. The extension
  is slugified the same way (`Photo.JPEG` → `photo.jpeg`,
  `archive.tar.gz` → `archive-tar.gz`).
- **date-title** — `<YYYY-MM-DD>-<slug>`; the date is the
  file's modification time in local time. A slug already
  starting with that same date is left unchanged; a
  different leading date is kept and the file's own date is
  prepended (`2020-01-01-party.jpg`, mtime 2026-11-04 →
  `2026-11-04-2020-01-01-party.jpg`).
- **episode** — entries ordered by natural sort of current
  names (case-insensitive; digit runs numeric, so `ep2`
  before `ep10`), numbered `S<season:02d>E<n:02d>` from
  `--start`. The title is the old stem with underscores →
  spaces, whitespace collapsed, edge separators stripped; a
  leading `SxxEyy` token from an earlier numbering is
  stripped, and an empty title becomes `untitled`.

## Scope rules (exact)

- Eligible: regular files directly in DIR whose names do
  not start with `.`. Everything else — subfolders, hidden
  files (including `.scaffolder-undo.json` itself),
  symlinks — is counted in `skipped` and never touched.
  Symlinks are never followed; a symlink's target is out of
  bounds even when it points inside DIR.
- Collisions are judged **case-insensitively**: two sources
  mapping to one target; a target that already exists and
  is not itself being renamed away (a name being renamed
  away frees its name — a case-only rename like `IMG.jpg` →
  `img.jpg` is legal); a target equal to a subfolder's
  name. Any collision refuses the whole apply.
- `apply` executes through temporary names
  (`.scaffolder-tmp-N`) in the same folder; a leftover temp
  file from an interrupted run is an exit-2 error naming
  it, never something the tool deletes silently.
- A mid-apply OS error rolls every moved file back to its
  original name before the error is reported; a failed
  undo-log write does the same.
- `apply` that renames nothing writes NO undo log (an
  earlier apply stays undoable). A successful apply
  replaces the previous log: undo is one apply deep.
- `undo` pre-checks the whole set: every `new` file must
  exist; every `old` name must be free or held by another
  entry of the same undo set. Any problem refuses the whole
  undo. A successful undo deletes the log.

## Output JSON schema (`--json`)

Common fields: `tool` (`"scaffolder"`), `version`,
`command`, `dir`.

`plan` / `apply`: `scheme`, `files` (eligible count),
`entries` — the rename map `[{old, new}]` in natural sort
order; `unchanged` — names already fitting the scheme;
`collisions` — `[{target, sources, reasons}]`;
`skipped` — `{subfolders, hidden, symlinks}`; `ok` — true
when there are no collisions. `apply` on success adds
`applied` (the entries renamed) and `undo_log`
(`".scaffolder-undo.json"`); on refusal it returns the plan
object with `ok: false`, exit 1.

`undo`: `ok`; on success `restored` —
`[{from, to}]` in log order; on refusal `problems` — the
exact list ("`<new>` is missing — cannot restore `<old>`",
"`<old>` is taken — a file with the original name exists
again", or the no-log message), exit 1.

On error, stdout is a single object: `{"error": "<message>"}`
with exit code 2 — including argparse usage errors in
`--json` mode. Never plain text, never a traceback.

## Exit codes

- `0` — command succeeded. For `plan`, the map is
  collision-free; for `apply`, the renames happened (or
  there was nothing to rename).
- `1` — a finding / refusal: a plan with collisions, an
  apply refused, an undo refused, or no undo log. The
  folder is unchanged in every exit-1 case. Not a crash —
  the collisions/problems list is the fix list.
- `2` — ERROR: folder missing or not a folder, a corrupt
  undo log, a leftover temp file, `--season`/`--start`
  below 1, an invalid flag. No output facts may be quoted
  from a failed run.

## Limits & honesty rules the agent must respect

- **Never report a rename as done from a `plan`.** Plan is
  a proposal; only an `apply` exit 0 with the entries in
  `applied` means files moved, and only an `undo` exit 0
  means they moved back.
- **A refusal is the tool working.** Report the exact
  collisions/problems; do not work around them by renaming
  or deleting files yourself unless the user directs it —
  the blocking name may be the user's only copy.
- **Undo is one apply deep and log-based.** If the undo log
  is gone (deleted, or replaced by a later apply), the
  earlier apply cannot be reversed by this tool — say so,
  never reconstruct a "probable" reversal.
- **Stay in the folder.** The tool's scope is one folder,
  top level. Do not loop it over a tree silently and report
  the tree as renamed; each folder is its own plan, apply
  and undo.
- Local only: the tool reads names and mtimes in the one
  folder named on the command line, and sends nothing
  anywhere.
