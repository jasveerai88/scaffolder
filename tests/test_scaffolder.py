#!/usr/bin/env python3
"""Tests for scaffolder. Stdlib unittest only, temp dirs only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

Every expected name below was worked out by hand from the
documented scheme rules, never copied from the tool's own
output.

Hand-computed scheme maps for the bundled sample folder
(examples/make_sample.py; hidden file and the raw/ subfolder
are never eligible). Eligible files in natural sort order
(casefold, digit runs as numbers):

    already-clean-name.jpg        mtime 2026-11-02
    IMG_4021.jpg                  mtime 2026-10-31
    my trip to the Lake!!.mp4     mtime 2026-10-31
    notes (draft).txt             mtime 2026-11-02
    Podcast Ep 3 - final FINAL.mp3  mtime 2026-11-01

slug (stem lowercased, non-[a-z0-9] runs -> one hyphen,
extension slugified):
    IMG_4021.jpg              -> img-4021.jpg
    already-clean-name.jpg    -> UNCHANGED
    my trip to the Lake!!.mp4 -> my-trip-to-the-lake.mp4
    notes (draft).txt         -> notes-draft.txt
    Podcast Ep 3 - final FINAL.mp3 -> podcast-ep-3-final-final.mp3

episode --season 1 --start 1 (title = stem with underscores
-> spaces, whitespace collapsed, SxxEyy prefix stripped):
    already-clean-name.jpg    -> S01E01 - already-clean-name.jpg
    IMG_4021.jpg              -> S01E02 - IMG 4021.jpg
    my trip to the Lake!!.mp4 -> S01E03 - my trip to the Lake!!.mp4
    notes (draft).txt         -> S01E04 - notes (draft).txt
    Podcast Ep 3 - final FINAL.mp3
                              -> S01E05 - Podcast Ep 3 - final FINAL.mp3

date-title (the file's own mtime date + slug):
    IMG_4021.jpg              -> 2026-10-31-img-4021.jpg
    already-clean-name.jpg    -> 2026-11-02-already-clean-name.jpg
    my trip to the Lake!!.mp4 -> 2026-10-31-my-trip-to-the-lake.mp4
    notes (draft).txt         -> 2026-11-02-notes-draft.txt
    Podcast Ep 3 - final FINAL.mp3
                              -> 2026-11-01-podcast-ep-3-final-final.mp3

Safety expectations are hash-based: a refused apply/undo and
a dry-run plan leave the tree hash (every relative path +
content, subfolders included) EXACTLY equal, and an
apply -> undo round trip restores it exactly (the undo log
is written by apply and removed by undo).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "scaffolder.py"
MAKE_SAMPLE = PACK_ROOT / "examples" / "make_sample.py"
sys.path.insert(0, str(PACK_ROOT / "src"))

import scaffolder as sc  # noqa: E402


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True, text=True, cwd=PACK_ROOT)


def write(folder, name, text="x\n", mtime=None):
    p = Path(folder) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mtime is not None:
        ts = datetime(*mtime, 12, 0, 0).timestamp()
        os.utime(p, (ts, ts))
    return p


def tree_hash(folder):
    """sha256 over every relative path + content, recursively."""
    h = hashlib.sha256()
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file() and not p.is_symlink():
            h.update(str(p.relative_to(folder)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def names(folder):
    return sorted(p.name for p in Path(folder).iterdir())


class SlugUnitTests(unittest.TestCase):
    def test_slug_basic(self):
        self.assertEqual(sc.slug_name("My Video FINAL (2).MP4"),
                         "my-video-final-2.mp4")

    def test_slug_camera_name(self):
        self.assertEqual(sc.slug_name("IMG_4021.jpg"),
                         "img-4021.jpg")

    def test_slug_runs_collapse_to_one_hyphen(self):
        self.assertEqual(sc.slug_name("a   b___c!!.txt"),
                         "a-b-c.txt")

    def test_slug_extension_lowercased(self):
        self.assertEqual(sc.slug_name("Photo.JPEG"), "photo.jpeg")

    def test_slug_no_extension(self):
        self.assertEqual(sc.slug_name("README"), "readme")

    def test_slug_empty_stem_falls_back_to_file(self):
        self.assertEqual(sc.slug_name("!!!.txt"), "file.txt")
        self.assertEqual(sc.slug_name("!!!"), "file")

    def test_slug_dotted_stem(self):
        self.assertEqual(sc.slug_name("archive.tar.gz"),
                         "archive-tar.gz")

    def test_tidy_title_strips_episode_prefix(self):
        self.assertEqual(sc.tidy_title("S01E09 - Old Title"),
                         "Old Title")
        self.assertEqual(sc.tidy_title("s2e03_clip"), "clip")

    def test_episode_name_fallback_title(self):
        self.assertEqual(sc.episode_name("S01E02.mp4", 0),
                         "S01E01 - untitled.mp4")

    def test_natural_key_orders_numbers(self):
        got = sorted(["ep10.mp4", "ep2.mp4", "ep1.mp4"],
                     key=sc.natural_key)
        self.assertEqual(got, ["ep1.mp4", "ep2.mp4", "ep10.mp4"])


class PlanSchemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "messy"
        self.d.mkdir()
        write(self.d, "IMG_4021.jpg", mtime=(2026, 10, 31))
        write(self.d, "already-clean-name.jpg", mtime=(2026, 11, 2))
        write(self.d, "my trip to the Lake!!.mp4",
              mtime=(2026, 10, 31))
        write(self.d, "notes (draft).txt", mtime=(2026, 11, 2))
        write(self.d, "Podcast Ep 3 - final FINAL.mp3",
              mtime=(2026, 11, 1))

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, scheme, **kw):
        return sc.build_plan(self.d, scheme, **kw)

    def test_slug_map_hand_verified(self):
        plan = self.plan("slug")
        got = {e["old"]: e["new"] for e in plan["entries"]}
        self.assertEqual(got, {
            "IMG_4021.jpg": "img-4021.jpg",
            "my trip to the Lake!!.mp4": "my-trip-to-the-lake.mp4",
            "notes (draft).txt": "notes-draft.txt",
            "Podcast Ep 3 - final FINAL.mp3":
                "podcast-ep-3-final-final.mp3",
        })
        self.assertEqual(plan["unchanged"],
                         ["already-clean-name.jpg"])
        self.assertEqual(plan["collisions"], [])

    def test_episode_map_hand_verified(self):
        plan = self.plan("episode")
        got = [(e["old"], e["new"]) for e in plan["entries"]]
        self.assertEqual(got, [
            ("already-clean-name.jpg",
             "S01E01 - already-clean-name.jpg"),
            ("IMG_4021.jpg", "S01E02 - IMG 4021.jpg"),
            ("my trip to the Lake!!.mp4",
             "S01E03 - my trip to the Lake!!.mp4"),
            ("notes (draft).txt", "S01E04 - notes (draft).txt"),
            ("Podcast Ep 3 - final FINAL.mp3",
             "S01E05 - Podcast Ep 3 - final FINAL.mp3"),
        ])

    def test_date_title_map_hand_verified(self):
        plan = self.plan("date-title")
        got = {e["old"]: e["new"] for e in plan["entries"]}
        self.assertEqual(got, {
            "IMG_4021.jpg": "2026-10-31-img-4021.jpg",
            "already-clean-name.jpg":
                "2026-11-02-already-clean-name.jpg",
            "my trip to the Lake!!.mp4":
                "2026-10-31-my-trip-to-the-lake.mp4",
            "notes (draft).txt": "2026-11-02-notes-draft.txt",
            "Podcast Ep 3 - final FINAL.mp3":
                "2026-11-01-podcast-ep-3-final-final.mp3",
        })

    def test_episode_season_and_start_offset(self):
        plan = self.plan("episode", season=2, start=7)
        self.assertEqual(plan["entries"][0]["new"],
                         "S02E07 - already-clean-name.jpg")
        self.assertEqual(plan["entries"][-1]["new"],
                         "S02E11 - Podcast Ep 3 - final FINAL.mp3")

    def test_episode_existing_prefix_not_doubled(self):
        write(self.d, "S01E09 - Old Title.mp4")
        plan = self.plan("episode")
        news = {e["old"]: e["new"] for e in plan["entries"]}
        self.assertIn(" - Old Title.mp4",
                      news["S01E09 - Old Title.mp4"])
        self.assertNotIn("S01E09",
                         news["S01E09 - Old Title.mp4"])

    def test_date_title_already_dated_unchanged(self):
        write(self.d, "2026-10-31-img-4021.jpg",
              mtime=(2026, 10, 31))
        plan = self.plan("date-title")
        self.assertIn("2026-10-31-img-4021.jpg",
                      plan["unchanged"])

    def test_date_title_other_date_is_kept_and_prepended(self):
        write(self.d, "2020-01-01-party.jpg", mtime=(2026, 11, 4))
        plan = self.plan("date-title")
        news = {e["old"]: e["new"] for e in plan["entries"]}
        self.assertEqual(news["2020-01-01-party.jpg"],
                         "2026-11-04-2020-01-01-party.jpg")

    def test_start_zero_is_clean_error(self):
        with self.assertRaises(sc.ToolError):
            self.plan("episode", start=0)
        with self.assertRaises(sc.ToolError):
            self.plan("episode", season=0)

    def test_episode_numbers_past_99(self):
        big = Path(self.tmp.name) / "big"
        big.mkdir()
        for i in range(105):
            write(big, f"clip {i:03d}.mp4")
        plan = sc.build_plan(big, "episode")
        news = [e["new"] for e in plan["entries"]]
        self.assertIn("S01E100 - clip 099.mp4", news)
        self.assertIn("S01E105 - clip 104.mp4", news)


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "messy"
        self.d.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_subfolder_never_entered_or_renamed(self):
        write(self.d, "Top File.mp4")
        inner = write(self.d, "raw/Inner File.dng")
        before = tree_hash(self.d)
        r = run_cli("apply", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(inner.exists())
        self.assertEqual((self.d / "raw").name, "raw")
        self.assertIn("top-file.mp4", names(self.d))
        # the only difference vs before: the top file + the log
        self.assertNotEqual(tree_hash(self.d), before)

    def test_hidden_files_skipped(self):
        write(self.d, ".hidden-notes.txt")
        write(self.d, "Visible File.txt")
        plan = sc.build_plan(self.d, "slug")
        self.assertEqual(plan["file_count"], 1)
        self.assertEqual(plan["skipped"]["hidden"], 1)
        r = run_cli("apply", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.d / ".hidden-notes.txt").exists())

    def test_symlink_never_followed_or_renamed(self):
        outside = write(self.tmp.name, "Outside File.txt",
                        text="precious\n")
        target = write(self.d, "Real File.txt")
        link = self.d / "Link File.txt"
        try:
            os.symlink(outside, link)
            os.symlink(target, self.d / "Local Link.txt")
        except OSError:
            self.skipTest("symlinks not available here")
        plan = sc.build_plan(self.d, "slug")
        self.assertEqual(plan["skipped"]["symlinks"], 2)
        self.assertEqual(plan["file_count"], 1)
        r = run_cli("apply", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(link.is_symlink())
        self.assertTrue((self.d / "Local Link.txt").is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"),
                         "precious\n")

    def test_skipped_counts_reported(self):
        write(self.d, "A File.txt")
        write(self.d, ".hidden")
        write(self.d, "sub/Inner.txt")
        r = run_cli("plan", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 subfolder(s), 1 hidden file(s)",
                      r.stdout)


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "messy"
        self.d.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_sources_one_target(self):
        write(self.d, "My File.txt")
        write(self.d, "my  file.txt")
        plan = sc.build_plan(self.d, "slug")
        self.assertEqual(len(plan["collisions"]), 1)
        self.assertEqual(plan["collisions"][0]["target"],
                         "my-file.txt")
        self.assertEqual(
            sorted(plan["collisions"][0]["sources"]),
            ["My File.txt", "my  file.txt"])

    def test_target_taken_by_unchanged_file(self):
        write(self.d, "My File.txt")
        write(self.d, "my-file.txt")
        plan = sc.build_plan(self.d, "slug")
        self.assertEqual(len(plan["collisions"]), 1)
        self.assertIn("already exists",
                      plan["collisions"][0]["reasons"][0])

    def test_target_taken_by_subfolder_name(self):
        write(self.d, "IMG_4021.jpg")
        (self.d / "img-4021.jpg").mkdir()
        plan = sc.build_plan(self.d, "slug")
        self.assertEqual(len(plan["collisions"]), 1)

    def test_case_only_difference_still_collides(self):
        write(self.d, "A B.txt")
        write(self.d, "a b.txt")
        plan = sc.build_plan(self.d, "slug")
        self.assertEqual(len(plan["collisions"]), 1)

    def test_plan_with_collisions_exits_1(self):
        write(self.d, "My File.txt")
        write(self.d, "my  file.txt")
        r = run_cli("plan", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 1)
        self.assertIn("COLLISIONS", r.stdout)

    def test_apply_refused_leaves_tree_identical(self):
        write(self.d, "My File.txt", text="one\n")
        write(self.d, "my  file.txt", text="two\n")
        write(self.d, "sub/Inner.txt", text="inner\n")
        before = tree_hash(self.d)
        r = run_cli("apply", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED", r.stdout)
        self.assertEqual(tree_hash(self.d), before)
        self.assertFalse((self.d / sc.UNDO_LOG).exists())


class ApplyUndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "messy"
        self.d.mkdir()
        write(self.d, "IMG_4021.jpg", text="photo\n",
              mtime=(2026, 10, 31))
        write(self.d, "my trip.mp4", text="video\n",
              mtime=(2026, 10, 31))
        write(self.d, "already-clean-name.jpg", text="tidy\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_does_not_mutate_anything(self):
        before = tree_hash(self.d)
        r = run_cli("plan", str(self.d), "--scheme", "episode")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing was renamed", r.stdout)
        self.assertEqual(tree_hash(self.d), before)
        self.assertFalse((self.d / sc.UNDO_LOG).exists())

    def test_apply_renames_and_writes_log(self):
        r = run_cli("apply", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(names(self.d),
                         [".scaffolder-undo.json",
                          "already-clean-name.jpg", "img-4021.jpg",
                          "my-trip.mp4"])
        log = json.loads((self.d / sc.UNDO_LOG).read_text())
        self.assertEqual(
            {(e["old"], e["new"]) for e in log["entries"]},
            {("IMG_4021.jpg", "img-4021.jpg"),
             ("my trip.mp4", "my-trip.mp4")})
        self.assertEqual((self.d / "img-4021.jpg").read_text(),
                         "photo\n")

    def test_case_only_rename_applies(self):
        solo = Path(self.tmp.name) / "solo"
        solo.mkdir()
        write(solo, "IMG.jpg", text="x\n")
        r = run_cli("apply", str(solo), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((solo / "img.jpg").exists())

    def test_apply_nothing_to_do_writes_no_log(self):
        solo = Path(self.tmp.name) / "tidy"
        solo.mkdir()
        write(solo, "already-clean.jpg")
        r = run_cli("apply", str(solo), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Nothing to rename", r.stdout)
        self.assertFalse((solo / sc.UNDO_LOG).exists())

    def test_second_apply_is_noop_and_keeps_first_log(self):
        run_cli("apply", str(self.d), "--scheme", "slug")
        log_before = (self.d / sc.UNDO_LOG).read_text()
        r = run_cli("apply", str(self.d), "--scheme", "slug")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.d / sc.UNDO_LOG).read_text(),
                         log_before)

    def test_apply_undo_round_trip_restores_tree(self):
        before = tree_hash(self.d)
        r = run_cli("apply", str(self.d), "--scheme", "episode")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(tree_hash(self.d), before)
        r = run_cli("undo", str(self.d))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(tree_hash(self.d), before)
        self.assertFalse((self.d / sc.UNDO_LOG).exists())

    def test_undo_without_log_exits_1(self):
        r = run_cli("undo", str(self.d))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Nothing to undo", r.stdout)

    def test_second_undo_exits_1(self):
        run_cli("apply", str(self.d), "--scheme", "slug")
        run_cli("undo", str(self.d))
        r = run_cli("undo", str(self.d))
        self.assertEqual(r.returncode, 1)

    def test_undo_refused_when_renamed_file_missing(self):
        run_cli("apply", str(self.d), "--scheme", "slug")
        (self.d / "my-trip.mp4").unlink()
        before = tree_hash(self.d)
        r = run_cli("undo", str(self.d))
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED", r.stdout)
        self.assertIn("my-trip.mp4 is missing", r.stdout)
        self.assertEqual(tree_hash(self.d), before)
        self.assertTrue((self.d / sc.UNDO_LOG).exists())

    def test_undo_refused_when_original_name_retaken(self):
        run_cli("apply", str(self.d), "--scheme", "slug")
        write(self.d, "my trip.mp4", text="impostor\n")
        before = tree_hash(self.d)
        r = run_cli("undo", str(self.d))
        self.assertEqual(r.returncode, 1)
        self.assertIn("my trip.mp4 is taken", r.stdout)
        self.assertEqual(tree_hash(self.d), before)

    def test_undo_corrupt_log_is_clean_error(self):
        (self.d / sc.UNDO_LOG).write_text("not json {",
                                          encoding="utf-8")
        r = run_cli("undo", str(self.d))
        self.assertEqual(r.returncode, 2)
        self.assertIn("corrupt", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_undo_log_never_renamed_by_later_apply(self):
        run_cli("apply", str(self.d), "--scheme", "slug")
        write(self.d, "Another File.txt")
        r = run_cli("apply", str(self.d), "--scheme", "date-title")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # the second apply replaced the log; undo now reverses
        # the date-title rename, and the log's own name survived
        self.assertTrue((self.d / sc.UNDO_LOG).exists())
        self.assertIn("Another File.txt",
                      [e["old"] for e in json.loads(
                          (self.d / sc.UNDO_LOG)
                          .read_text())["entries"]])


class CliShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "messy"
        self.d.mkdir()
        write(self.d, "My File.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def test_json_plan_shape(self):
        r = run_cli("plan", str(self.d), "--scheme", "slug",
                    "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["tool"], "scaffolder")
        self.assertEqual(data["command"], "plan")
        self.assertEqual(data["scheme"], "slug")
        self.assertTrue(data["ok"])
        self.assertEqual(data["entries"],
                         [{"old": "My File.txt",
                           "new": "my-file.txt"}])

    def test_json_apply_and_undo_shapes(self):
        r = run_cli("apply", str(self.d), "--scheme", "slug",
                    "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["applied"],
                         [{"old": "My File.txt",
                           "new": "my-file.txt"}])
        self.assertEqual(data["undo_log"], ".scaffolder-undo.json")
        r = run_cli("undo", str(self.d), "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["restored"],
                         [{"from": "my-file.txt",
                           "to": "My File.txt"}])

    def test_json_collision_apply_ok_false(self):
        write(self.d, "my  file.txt")
        r = run_cli("apply", str(self.d), "--scheme", "slug",
                    "--json")
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(len(data["collisions"]), 1)

    def test_json_error_for_missing_dir(self):
        missing = str(Path(self.tmp.name) / "nope")
        r = run_cli("plan", missing, "--scheme", "slug", "--json")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(set(json.loads(r.stdout)), {"error"})

    def test_missing_dir_text_error(self):
        missing = str(Path(self.tmp.name) / "nope")
        r = run_cli("plan", missing, "--scheme", "slug")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR: no such folder", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_file_as_dir_is_error(self):
        f = write(self.tmp.name, "afile.txt")
        r = run_cli("plan", str(f), "--scheme", "slug")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a folder", r.stdout)

    def test_argparse_error_json_shape(self):
        r = run_cli("plan", str(self.d), "--scheme", "bogus",
                    "--json")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(set(json.loads(r.stdout)), {"error"})
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_argparse_error_text_no_traceback(self):
        r = run_cli("plan", str(self.d), "--scheme", "bogus")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_no_command_exit_2(self):
        r = run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_start_zero_cli_exit_2(self):
        r = run_cli("plan", str(self.d), "--scheme", "episode",
                    "--start", "0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_unknown_flag_exit_2(self):
        r = run_cli("plan", str(self.d), "--scheme", "slug",
                    "--wat")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


class SampleTests(unittest.TestCase):
    def test_sample_episode_map_matches_hand_computation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "messy-folder"
            r = subprocess.run(
                [sys.executable, str(MAKE_SAMPLE), str(target)],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            plan = sc.build_plan(target, "episode")
            self.assertEqual(
                [(e["old"], e["new"]) for e in plan["entries"]],
                [("already-clean-name.jpg",
                  "S01E01 - already-clean-name.jpg"),
                 ("IMG_4021.jpg", "S01E02 - IMG 4021.jpg"),
                 ("my trip to the Lake!!.mp4",
                  "S01E03 - my trip to the Lake!!.mp4"),
                 ("notes (draft).txt",
                  "S01E04 - notes (draft).txt"),
                 ("Podcast Ep 3 - final FINAL.mp3",
                  "S01E05 - Podcast Ep 3 - final FINAL.mp3")])
            self.assertEqual(plan["skipped"],
                             {"subfolders": 1, "hidden": 1,
                              "symlinks": 0})
            self.assertEqual(plan["file_count"], 5)


if __name__ == "__main__":
    unittest.main()
