#!/usr/bin/env python3
"""scaffolder — plan and apply SAFE batch renames in a media
folder, with an undo log.

Pure Python standard library. Local only: no network, no
uploads, no accounts. It never follows a symlink, never
enters a subfolder, and never touches anything outside the
one folder you name.

Creators and small channels waste real time renaming camera
dumps, downloads and episode assets by hand — and a careless
batch rename is how files get overwritten or lost. This
tool's whole product is the safety around the rename:

  plan DIR --scheme SCHEME
            dry run ONLY. Prints the exact rename map
            (old -> new) and any collisions. Writes
            nothing — no renames, no undo log, nothing.
  apply DIR --scheme SCHEME
            regenerates the plan, re-verifies it, and only
            then renames. Collisions = refuse EVERYTHING
            (exit 1, folder byte-identical to before). The
            renames run in two phases through temporary
            names, so a rename can never overwrite another
            file, not even mid-apply. A successful apply
            writes .scaffolder-undo.json into DIR with every
            old/new pair.
  undo DIR  reverses the last apply exactly, from the undo
            log. Pre-checked as a whole: if any renamed file
            is missing, or any original name has been taken
            again, undo refuses (exit 1) and changes nothing.

Schemes:
  slug        lowercase-hyphen names:
              "My Video FINAL (2).MP4" -> "my-video-final-2.mp4"
  date-title  the file's own modification date + its slug:
              "IMG_4021.jpg" (modified 2026-10-31)
              -> "2026-10-31-img-4021.jpg"
  episode     SxxEyy numbering in natural sorted order, the
              title kept ("--season 2 --start 7" to offset):
              "IMG_4021.jpg" -> "S01E02 - IMG 4021.jpg"

Scope, deliberately narrow: only regular files DIRECTLY in
DIR. Subfolders are counted and reported, never entered and
never renamed. Hidden files (leading dot) are left alone —
that includes the undo log itself. Symlinks are counted,
never followed and never renamed: a symlink's target may
live outside DIR, and outside DIR is out of bounds.

Name maths, exactly:
  slug: the stem is lowercased, every run of characters
    outside [a-z0-9] becomes one hyphen, edge hyphens are
    stripped; an empty result becomes "file". The extension
    is slugified the same way (so ".MP4" -> ".mp4").
  date-title: "<YYYY-MM-DD>-<slug>", the date being the
    file's modification date in local time. If the slug
    already starts with that same date, the name is left
    alone; a different leading date is kept and the file's
    own date is prepended in front of it.
  episode: files are ordered by a natural sort of their
    current names (case-insensitive, digit runs compared as
    numbers, so ep2 sorts before ep10) and numbered from
    --start. The title is the old stem with underscores
    turned into spaces and whitespace collapsed; a leading
    SxxEyy token from an earlier numbering is stripped, and
    an empty title becomes "untitled".

Collisions are judged case-insensitively, because the
filesystems most creators use (macOS, Windows) are: two
files mapping to one target, a target that already exists
and is not itself being renamed away, or a target equal to
a subfolder's name — all refuse the whole apply.

Exit codes: 0 = ok · 1 = a finding/refusal (collisions in a
plan or apply; undo refused or nothing to undo) — the folder
is unchanged · 2 = ERROR — clean message, never a traceback;
with --json the error is {"error": ...}. Every command
takes --json: one JSON object with the same facts and exit
codes as the text view.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

__version__ = "0.1.0"
TOOL = "scaffolder"
UNDO_LOG = ".scaffolder-undo.json"
SCHEMES = ("slug", "date-title", "episode")
_TMP_PREFIX = ".scaffolder-tmp-"


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# Name maths
# --------------------------------------------------------------------------

def split_name(name):
    """'Clip.MP4' -> ('Clip', 'MP4'); 'README' -> ('README', '')."""
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        return stem, ext
    return name, ""


def slugify(text):
    """Lowercase; runs of non-[a-z0-9] -> one hyphen; edges stripped."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def slug_name(name):
    stem, ext = split_name(name)
    base = slugify(stem) or "file"
    e = slugify(ext)
    return f"{base}.{e}" if e else base


def date_title_name(path):
    date = datetime.fromtimestamp(
        path.stat().st_mtime).strftime("%Y-%m-%d")
    stem, ext = split_name(path.name)
    base = slugify(stem) or "file"
    if base != date and not base.startswith(date + "-"):
        base = f"{date}-{base}"
    e = slugify(ext)
    return f"{base}.{e}" if e else base


_EP_PREFIX_RE = re.compile(r"^s\d{1,2}e\d{1,3}\b[ ._-]*", re.IGNORECASE)


def tidy_title(stem):
    """The episode title: underscores -> spaces, whitespace
    collapsed, edge separators stripped, and a leading SxxEyy
    token from an earlier numbering removed."""
    title = re.sub(r"\s+", " ", stem.replace("_", " ")).strip(" -")
    return _EP_PREFIX_RE.sub("", title).strip(" -")


def episode_name(name, index, season=1, start=1):
    stem, ext = split_name(name)
    title = tidy_title(stem) or "untitled"
    e = slugify(ext)
    base = f"S{season:02d}E{start + index:02d} - {title}"
    return f"{base}.{e}" if e else base


def natural_key(name):
    """Sort key: case-insensitive, digit runs as numbers
    (ep2 < ep10). re.split with a capture group alternates
    str/int positions, so lists compare safely."""
    return [int(p) if p.isdigit() else p
            for p in re.split(r"(\d+)", name.casefold())]


# --------------------------------------------------------------------------
# Scanning and planning
# --------------------------------------------------------------------------

def scan_dir(d):
    """(eligible file Paths, skipped counts) for DIR's top level.

    Eligible = regular file, not hidden, not a symlink.
    Subfolders, hidden files and symlinks are counted, never
    touched."""
    files, skipped = [], {"subfolders": 0, "hidden": 0, "symlinks": 0}
    for entry in os.scandir(d):
        if entry.is_symlink():
            skipped["symlinks"] += 1
        elif entry.is_dir(follow_symlinks=False):
            skipped["subfolders"] += 1
        elif entry.is_file(follow_symlinks=False):
            if entry.name.startswith("."):
                skipped["hidden"] += 1
            else:
                files.append(Path(entry.path))
    files.sort(key=lambda p: natural_key(p.name))
    return files, skipped


def build_plan(d, scheme, season=1, start=1):
    """The full plan for DIR under SCHEME: rename entries,
    unchanged names, collisions (case-insensitive), skipped
    counts. Pure: reads names and mtimes, writes nothing."""
    if season < 1:
        raise ToolError("--season must be 1 or more")
    if start < 1:
        raise ToolError("--start must be 1 or more")
    files, skipped = scan_dir(d)
    entries, unchanged = [], []
    targets = {}
    for i, p in enumerate(files):
        if scheme == "slug":
            new = slug_name(p.name)
        elif scheme == "date-title":
            new = date_title_name(p)
        else:
            new = episode_name(p.name, i, season, start)
        if new == p.name:
            unchanged.append(p.name)
        else:
            entries.append({"old": p.name, "new": new})
            targets.setdefault(new.casefold(), []).append(p.name)

    renamed_away = {e["old"].casefold() for e in entries}
    existing = {}
    for entry in os.scandir(d):
        if entry.name.casefold() not in renamed_away:
            existing[entry.name.casefold()] = entry.name

    collisions = {}
    for e in entries:
        key = e["new"].casefold()
        slot = collisions.setdefault(
            key, {"target": e["new"], "sources": [], "reasons": []})
        if e["old"] not in slot["sources"]:
            slot["sources"].append(e["old"])
        if len(targets[key]) > 1 and not any(
                "would be renamed" in r for r in slot["reasons"]):
            slot["reasons"].append(
                f"{len(targets[key])} files would be renamed "
                f"to this name")
        if key in existing and not any(
                "already exists" in r for r in slot["reasons"]):
            slot["reasons"].append(
                f"already exists and is not being renamed: "
                f"{existing[key]}")
    return {"scheme": scheme, "entries": entries,
            "unchanged": unchanged,
            "collisions": [collisions[k] for k in sorted(collisions)
                           if collisions[k]["reasons"]],
            "skipped": skipped, "file_count": len(files)}


# --------------------------------------------------------------------------
# Applying and undoing (two-phase: nothing is ever overwritten)
# --------------------------------------------------------------------------

def _two_phase_rename(d, pairs):
    """Rename (src_name -> dst_name) pairs inside DIR via
    temporary names, so no step can overwrite a file. On any
    OS error, everything already moved is rolled back to its
    original name (best effort) and ToolError is raised with
    the folder restored."""
    temps = [d / f"{_TMP_PREFIX}{i}" for i in range(len(pairs))]
    for t in temps:
        if os.path.lexists(t):
            raise ToolError(
                f"leftover temporary file {t.name} is in the "
                f"way — move or delete it, then run again")
    at = ["old"] * len(pairs)   # per pair: old -> tmp -> new
    try:
        for i, (src, _dst) in enumerate(pairs):
            os.rename(d / src, temps[i])
            at[i] = "tmp"
        for i, (_src, dst) in enumerate(pairs):
            os.rename(temps[i], d / dst)
            at[i] = "new"
    except OSError as exc:
        for i, (src, dst) in enumerate(pairs):
            if at[i] == "old":
                continue
            current = temps[i] if at[i] == "tmp" else d / dst
            try:
                os.rename(current, d / src)
            except OSError:
                pass
        raise ToolError(
            f"rename failed partway ({exc}); every file was "
            f"rolled back to its original name")


def do_apply(d, plan):
    """Execute a verified plan and write the undo log. The
    caller has already checked: no collisions, entries exist."""
    pairs = [(e["old"], e["new"]) for e in plan["entries"]]
    _two_phase_rename(d, pairs)
    log = {"tool": TOOL, "version": __version__,
           "scheme": plan["scheme"],
           "applied_at": datetime.now().isoformat(timespec="seconds"),
           "entries": plan["entries"]}
    try:
        (d / UNDO_LOG).write_text(
            json.dumps(log, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        _two_phase_rename(d, [(new, old) for old, new in pairs])
        raise ToolError(
            f"could not write the undo log ({exc}); the "
            f"renames were rolled back")


def load_undo_log(d):
    """None when there is no undo log; the entries list when
    there is. A corrupt log is an ERROR (exit 2), never a
    silent 'nothing to undo'."""
    path = d / UNDO_LOG
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["entries"]
        if not isinstance(entries, list) or not all(
                isinstance(e, dict)
                and isinstance(e.get("old"), str)
                and isinstance(e.get("new"), str)
                for e in entries):
            raise ValueError("entries is not a list of "
                             "{old, new} pairs")
    except (ValueError, KeyError, TypeError,
            UnicodeDecodeError) as exc:
        raise ToolError(f"undo log {UNDO_LOG} is corrupt: {exc}")
    olds = [e["old"] for e in entries]
    news = [e["new"] for e in entries]
    if len(set(olds)) != len(olds) or len(set(news)) != len(news):
        raise ToolError(f"undo log {UNDO_LOG} is corrupt: "
                        f"duplicate names in its entries")
    return entries


def undo_problems(d, entries):
    """Whole-set pre-check for undo: every renamed file must
    still be there, and every original name must be free (or
    held by another file in the same undo set, which the
    two-phase rename vacates)."""
    vacating = {e["new"].casefold() for e in entries}
    problems = []
    for e in entries:
        if not os.path.lexists(d / e["new"]):
            problems.append(
                f"{e['new']} is missing — cannot restore "
                f"{e['old']}")
        if (os.path.lexists(d / e["old"])
                and e["old"].casefold() not in vacating):
            problems.append(
                f"{e['old']} is taken — a file with the "
                f"original name exists again")
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json
    mode ({"error": ...} on stdout, same exit code 2) — an agent
    driving this tool with --json never gets plain text or a
    traceback. The flag lives on the class so subparsers share
    it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _json_arg(p):
    p.add_argument("--json", action="store_true",
                   help="print one JSON object instead of text")


def require_dir(raw):
    d = Path(raw)
    if not d.exists():
        raise ToolError(f"no such folder: {raw}")
    if not d.is_dir():
        raise ToolError(f"not a folder: {raw}")
    return d


def _plan_result(command, d, plan):
    return {"tool": TOOL, "version": __version__,
            "command": command, "dir": str(d),
            "scheme": plan["scheme"],
            "files": plan["file_count"],
            "entries": plan["entries"],
            "unchanged": plan["unchanged"],
            "collisions": plan["collisions"],
            "skipped": plan["skipped"],
            "ok": not plan["collisions"]}


def _skipped_line(skipped):
    return (f"Not touched: {skipped['subfolders']} subfolder(s), "
            f"{skipped['hidden']} hidden file(s), "
            f"{skipped['symlinks']} symlink(s) — scaffolder "
            f"renames only regular files directly in the folder.")


def _collisions_text(collisions):
    lines = []
    for c in collisions:
        lines.append(f"  {c['target']} — "
                     f"{'; '.join(c['reasons'])} "
                     f"(from: {', '.join(c['sources'])})")
    return lines


def cmd_plan(a):
    d = require_dir(a.dir)
    plan = build_plan(d, a.scheme, a.season, a.start)
    if a.json:
        print(json.dumps(_plan_result("plan", d, plan), indent=2))
        return 0 if not plan["collisions"] else 1
    print(f"{TOOL} v{__version__} — plan · folder {d.name}")
    print(f"{d.name} · scheme: {plan['scheme']} · "
          f"{plan['file_count']} file(s) scanned")
    print()
    if plan["entries"]:
        for e in plan["entries"]:
            print(f"  {e['old']}  ->  {e['new']}")
    else:
        print("  (nothing to rename — every name already "
              "fits the scheme)")
    if plan["unchanged"]:
        print()
        print(f"Unchanged — already fits the scheme "
              f"({len(plan['unchanged'])}):")
        for name in plan["unchanged"]:
            print(f"  {name}")
    if any(plan["skipped"].values()):
        print()
        print(_skipped_line(plan["skipped"]))
    if plan["collisions"]:
        print()
        print(f"COLLISIONS — applying this plan would be "
              f"refused ({len(plan['collisions'])}):")
        for line in _collisions_text(plan["collisions"]):
            print(line)
    print()
    print("Plan only — nothing was renamed, no files were "
          "written. Run `apply` with the same scheme to do it.")
    return 0 if not plan["collisions"] else 1


def cmd_apply(a):
    d = require_dir(a.dir)
    plan = build_plan(d, a.scheme, a.season, a.start)
    if plan["collisions"]:
        if a.json:
            print(json.dumps(_plan_result("apply", d, plan),
                             indent=2))
        else:
            print(f"{TOOL} v{__version__} — apply · folder {d.name}")
            print(f"REFUSED — nothing was renamed "
                  f"({len(plan['collisions'])} collision(s)):")
            for line in _collisions_text(plan["collisions"]):
                print(line)
            print("The folder is exactly as it was.")
        return 1
    if not plan["entries"]:
        if a.json:
            result = _plan_result("apply", d, plan)
            result["applied"] = []
            print(json.dumps(result, indent=2))
        else:
            print(f"{TOOL} v{__version__} — apply · folder {d.name}")
            print("Nothing to rename — every name already "
                  "fits the scheme. No undo log written.")
        return 0
    do_apply(d, plan)
    if a.json:
        result = _plan_result("apply", d, plan)
        result["applied"] = plan["entries"]
        result["undo_log"] = UNDO_LOG
        print(json.dumps(result, indent=2))
    else:
        print(f"{TOOL} v{__version__} — apply · folder {d.name}")
        print(f"{d.name} · scheme: {plan['scheme']} · "
              f"{plan['file_count']} file(s) scanned")
        print()
        for e in plan["entries"]:
            print(f"  {e['old']}  ->  {e['new']}")
        print()
        print(f"Applied {len(plan['entries'])} rename(s). "
              f"Undo log written to {UNDO_LOG} — "
              f"`scaffolder undo` on this folder reverses "
              f"exactly this apply.")
    return 0


def cmd_undo(a):
    d = require_dir(a.dir)
    entries = load_undo_log(d)
    if entries is None:
        msg = (f"no undo log ({UNDO_LOG}) in this folder — "
               f"nothing to undo")
        if a.json:
            print(json.dumps(
                {"tool": TOOL, "version": __version__,
                 "command": "undo", "dir": str(d), "ok": False,
                 "problems": [msg]}, indent=2))
        else:
            print(f"{TOOL} v{__version__} — undo · folder {d.name}")
            print(f"Nothing to undo — {msg}.")
        return 1
    problems = undo_problems(d, entries)
    if problems:
        if a.json:
            print(json.dumps(
                {"tool": TOOL, "version": __version__,
                 "command": "undo", "dir": str(d), "ok": False,
                 "problems": problems}, indent=2))
        else:
            print(f"{TOOL} v{__version__} — undo · folder {d.name}")
            print(f"REFUSED — nothing was renamed "
                  f"({len(problems)} problem(s)):")
            for p in problems:
                print(f"  - {p}")
            print("The folder is exactly as it was.")
        return 1
    pairs = [(e["new"], e["old"]) for e in entries]
    _two_phase_rename(d, pairs)
    try:
        (d / UNDO_LOG).unlink()
    except OSError:
        pass
    restored = [{"from": e["new"], "to": e["old"]} for e in entries]
    if a.json:
        print(json.dumps(
            {"tool": TOOL, "version": __version__,
             "command": "undo", "dir": str(d), "ok": True,
             "restored": restored}, indent=2))
    else:
        print(f"{TOOL} v{__version__} — undo · folder {d.name}")
        print()
        for r in restored:
            print(f"  {r['from']}  ->  {r['to']}")
        print()
        print(f"Restored {len(restored)} file(s). Undo log "
              f"removed.")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Plan and apply SAFE batch renames in a "
                    "media folder: plan writes nothing, apply "
                    "refuses on any collision and writes an "
                    "undo log, undo reverses the last apply "
                    "exactly. (stdlib only, local only).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    def scheme_args(p):
        p.add_argument("dir", help="the folder to work in "
                                   "(top level only)")
        p.add_argument("--scheme", choices=SCHEMES, required=True,
                       help="slug | date-title | episode")
        p.add_argument("--season", type=int, default=1,
                       help="episode scheme: season number "
                            "(default 1)")
        p.add_argument("--start", type=int, default=1,
                       help="episode scheme: first episode "
                            "number (default 1)")
        _json_arg(p)

    p_plan = sub.add_parser(
        "plan", help="dry run: print the exact rename map "
                     "and any collisions; writes nothing")
    scheme_args(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser(
        "apply", help="rename, after re-verifying the plan; "
                      "any collision refuses everything; "
                      "writes the undo log")
    scheme_args(p_apply)
    p_apply.set_defaults(func=cmd_apply)

    p_undo = sub.add_parser(
        "undo", help="reverse the last apply exactly, from "
                     "the undo log")
    p_undo.add_argument("dir", help="the folder to work in "
                                    "(top level only)")
    _json_arg(p_undo)
    p_undo.set_defaults(func=cmd_undo)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
