# scaffolder

**The renaming is easy. Not losing a file to the renaming
is the job.**

Every creator's folders look the same after a shoot:
`IMG_4021.jpg`, `my trip to the Lake!!.mp4`,
`Podcast Ep 3 - final FINAL.mp3`. Renaming a folderful of
that by hand is slow — and renaming it with a careless
script is how two files end up with one name and one of
them quietly stops existing.

`scaffolder` does batch renames the safe way. `plan` prints
the exact rename map and writes *nothing*. `apply`
re-verifies the plan before it touches a file: if any two
files would land on the same name, or a target name is
already taken, it refuses *everything* and the folder stays
exactly as it was. A successful apply runs in two phases
through temporary names — no rename can ever overwrite
another file, not even mid-apply — and writes an undo log,
so `undo` can reverse the whole apply exactly.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your files never leave your machine
- Script-friendly exit codes: `0` = ok, `1` = a finding /
  refusal (folder unchanged), `2` = error

## The three schemes

| Scheme | What it does | Example |
|---|---|---|
| `slug` | lowercase-hyphen names; extension lowercased | `My Video FINAL (2).MP4` → `my-video-final-2.mp4` |
| `date-title` | the file's own modification date + its slug | `IMG_4021.jpg` (modified 2026-10-31) → `2026-10-31-img-4021.jpg` |
| `episode` | `SxxEyy` numbering in natural sorted order, title kept | `IMG_4021.jpg` → `S01E02 - IMG 4021.jpg` |

The name maths, exactly:

- **slug** — the stem is lowercased, every run of characters
  outside `[a-z0-9]` becomes one hyphen, edge hyphens are
  stripped; an empty result becomes `file`. The extension is
  slugified the same way.
- **date-title** — `<YYYY-MM-DD>-<slug>`, the date being the
  file's modification date in local time. If the slug
  already starts with that same date, the name is left
  alone; a *different* leading date is kept, with the file's
  own date prepended in front of it.
- **episode** — files are ordered by a natural sort of their
  current names (case-insensitive, digit runs compared as
  numbers, so `ep2` sorts before `ep10`) and numbered from
  `--start` (default 1) in season `--season` (default 1).
  The title is the old stem with underscores turned into
  spaces and whitespace collapsed; a leading `SxxEyy` token
  from an earlier numbering is stripped so re-running never
  doubles it, and an empty title becomes `untitled`.

## Scope — deliberately narrow

Only **regular files directly in the folder you name** are
renamed. Subfolders are counted and reported, never entered
and never renamed. Hidden files (leading dot) are left
alone — that includes the undo log itself. Symlinks are
counted, never followed and never renamed: a symlink's
target may live outside the folder, and outside the folder
is out of bounds. Every plan and apply tells you what it
did not touch.

## Collisions refuse everything

Collision checks are **case-insensitive**, because the
filesystems most creators use (macOS, Windows) are. An
apply is refused — all of it, exit 1, folder byte-identical
to before — when:

- two files would be renamed to the same target, or
- a target already exists and is not itself being renamed
  away (an unchanged file, a subfolder's name, anything), or
- for `undo`: a renamed file has gone missing, or a file
  with an original name exists again.

There is no partial apply. Fix the names the refusal lists,
and run again.

## Usage

```bash
# 0. Build the bundled sample folder (or use your own)
python3 examples/make_sample.py /tmp/scaffolder-demo

# 1. Dry run — prints the map, writes nothing
python3 src/scaffolder.py plan /tmp/scaffolder-demo --scheme slug

# 2. Apply a scheme — verified first, undo log written
python3 src/scaffolder.py apply /tmp/scaffolder-demo --scheme episode

# 3. Change your mind — reverse the last apply exactly
python3 src/scaffolder.py undo /tmp/scaffolder-demo

# 4. Drive it from a script
python3 src/scaffolder.py plan DIR --scheme slug --json
python3 src/scaffolder.py apply DIR --scheme episode --season 2 --start 7
```

The undo log is `.scaffolder-undo.json` inside the folder —
plain JSON, one `{old, new}` pair per rename. A later apply
replaces it, so `undo` always reverses the *last* apply. If
an apply renames nothing (every name already fits), no log
is written and an earlier undo stays possible.

## Use with AI agents

Every command takes `--json`: one JSON object with the same
facts and exit codes as the text view (errors come back as
`{"error": ...}`, argparse usage errors included):

```bash
python3 src/scaffolder.py plan DIR --scheme slug --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the
full JSON schemas, exit codes, and the safety rules (a
refusal is a result, not a failure; never rename around the
tool to "fix" a collision it reported).

## Real run (verbatim)

The bundled sample is one messy downloads/camera folder.
Building it and taking the slug plan:

```text
$ python3 examples/make_sample.py /tmp/scaffolder-demo
Created /tmp/scaffolder-demo with 6 files (+ 1 subfolder `raw/`)
(exit code: 0)

$ python3 src/scaffolder.py plan /tmp/scaffolder-demo --scheme slug
scaffolder v0.1.0 — plan · folder scaffolder-demo
scaffolder-demo · scheme: slug · 5 file(s) scanned

  IMG_4021.jpg  ->  img-4021.jpg
  my trip to the Lake!!.mp4  ->  my-trip-to-the-lake.mp4
  notes (draft).txt  ->  notes-draft.txt
  Podcast Ep 3 - final FINAL.mp3  ->  podcast-ep-3-final-final.mp3

Unchanged — already fits the scheme (1):
  already-clean-name.jpg

Not touched: 1 subfolder(s), 1 hidden file(s), 0 symlink(s) — scaffolder renames only regular files directly in the folder.

Plan only — nothing was renamed, no files were written. Run `apply` with the same scheme to do it.
(exit code: 0)
```

The same folder under `date-title` — each file gets its own
modification date (the generator sets them: 2026-10-31,
2026-11-01, 2026-11-02):

```text
$ python3 src/scaffolder.py plan /tmp/scaffolder-demo --scheme date-title
scaffolder v0.1.0 — plan · folder scaffolder-demo
scaffolder-demo · scheme: date-title · 5 file(s) scanned

  already-clean-name.jpg  ->  2026-11-02-already-clean-name.jpg
  IMG_4021.jpg  ->  2026-10-31-img-4021.jpg
  my trip to the Lake!!.mp4  ->  2026-10-31-my-trip-to-the-lake.mp4
  notes (draft).txt  ->  2026-11-02-notes-draft.txt
  Podcast Ep 3 - final FINAL.mp3  ->  2026-11-01-podcast-ep-3-final-final.mp3

Not touched: 1 subfolder(s), 1 hidden file(s), 0 symlink(s) — scaffolder renames only regular files directly in the folder.

Plan only — nothing was renamed, no files were written. Run `apply` with the same scheme to do it.
(exit code: 0)
```

Applying the `episode` scheme, and then undoing it:

```text
$ python3 src/scaffolder.py apply /tmp/scaffolder-demo --scheme episode
scaffolder v0.1.0 — apply · folder scaffolder-demo
scaffolder-demo · scheme: episode · 5 file(s) scanned

  already-clean-name.jpg  ->  S01E01 - already-clean-name.jpg
  IMG_4021.jpg  ->  S01E02 - IMG 4021.jpg
  my trip to the Lake!!.mp4  ->  S01E03 - my trip to the Lake!!.mp4
  notes (draft).txt  ->  S01E04 - notes (draft).txt
  Podcast Ep 3 - final FINAL.mp3  ->  S01E05 - Podcast Ep 3 - final FINAL.mp3

Applied 5 rename(s). Undo log written to .scaffolder-undo.json — `scaffolder undo` on this folder reverses exactly this apply.
(exit code: 0)

$ ls /tmp/scaffolder-demo
S01E01 - already-clean-name.jpg
S01E02 - IMG 4021.jpg
S01E03 - my trip to the Lake!!.mp4
S01E04 - notes (draft).txt
S01E05 - Podcast Ep 3 - final FINAL.mp3
raw

$ python3 src/scaffolder.py undo /tmp/scaffolder-demo
scaffolder v0.1.0 — undo · folder scaffolder-demo

  S01E01 - already-clean-name.jpg  ->  already-clean-name.jpg
  S01E02 - IMG 4021.jpg  ->  IMG 4021.jpg
  S01E03 - my trip to the Lake!!.mp4  ->  my trip to the Lake!!.mp4
  S01E04 - notes (draft).txt  ->  notes (draft).txt
  S01E05 - Podcast Ep 3 - final FINAL.mp3  ->  Podcast Ep 3 - final FINAL.mp3

Restored 5 file(s). Undo log removed.
(exit code: 0)
```

And a collision — two files that both slug to
`my-file.txt`. The plan names it (exit 1), the apply
refuses, and the folder is untouched:

```text
$ python3 src/scaffolder.py plan /tmp/scaffolder-clash --scheme slug
scaffolder v0.1.0 — plan · folder scaffolder-clash
scaffolder-clash · scheme: slug · 2 file(s) scanned

  my  file.txt  ->  my-file.txt
  My File.txt  ->  my-file.txt

COLLISIONS — applying this plan would be refused (1):
  my-file.txt — 2 files would be renamed to this name (from: my  file.txt, My File.txt)

Plan only — nothing was renamed, no files were written. Run `apply` with the same scheme to do it.
(exit code: 1)

$ python3 src/scaffolder.py apply /tmp/scaffolder-clash --scheme slug
scaffolder v0.1.0 — apply · folder scaffolder-clash
REFUSED — nothing was renamed (1 collision(s)):
  my-file.txt — 2 files would be renamed to this name (from: my  file.txt, My File.txt)
The folder is exactly as it was.
(exit code: 1)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 53 tests — OK
```

The suite covers both directions: all three scheme maps
against hand-computed expectations (including the bundled
sample's episode numbering, worked out by hand in the test
header); the boundaries — a target freed by its own rename
(case-only rename) applies, a target held by anything else
refuses; natural sort (`ep2` before `ep10`) and episode
numbers past 99; scope (subfolders never entered, hidden
files and symlinks never touched); and the safety core,
hash-verified — `plan` mutates nothing, a refused apply and
a refused undo leave the tree hash (every path + content,
subfolders included) exactly equal, and an apply → undo
round trip restores it exactly. Errors are clean: missing
folder, corrupt undo log and argparse misuse all exit 2 as
`{"error": ...}` under `--json`, never a traceback.

## Internal use

This tool does real jobs for its author: the author's
channels keep per-episode asset folders and a stock-footage
library, and both arrive as camera dumps and downloads with
names like the sample's. `episode` is how a season folder
gets numbered without a hand rename per file, `date-title`
is how raw footage gets sorted by shoot day, and the undo
log is why either is safe to run on the only copy.

## Known limits

- Top level only, deliberately. A nested library is renamed
  one folder at a time, by running the tool once per folder
  — it will never recurse on its own.
- One undo deep. The log holds the last apply only; a second
  apply replaces it.
- `date-title` reads modification times. Copying a folder
  can reset them (some tools preserve mtimes, some do not) —
  run `plan` first and read the dates before applying.
- Slug output is `[a-z0-9-]` only, so non-Latin names reduce
  hard (a stem with no Latin letters or digits becomes
  `file`). The plan shows every result before anything is
  applied — read it.
- Renames are filesystem renames on one volume; nothing is
  copied, converted or re-encoded.

## Privacy

What it touches: only the one folder you name, top level.
What it sends: nothing — there is no network code in this
tool.

## Support

If this saves one folder of footage from a bad batch
rename, consider sponsoring: **https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
