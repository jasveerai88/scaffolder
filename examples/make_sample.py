#!/usr/bin/env python3
"""Create the bundled messy sample folder for scaffolder.

Usage:
    python3 examples/make_sample.py [TARGET_DIR]

Default TARGET_DIR is `messy-folder/` beside this script.
The folder is a camera-dump / downloads mess of the kind
scaffolder exists for:

    IMG_4021.jpg                    camera name, mtime 2026-10-31
    my trip to the Lake!!.mp4       spaces + punctuation, 2026-10-31
    Podcast Ep 3 - final FINAL.mp3  shouty working title, 2026-11-01
    notes (draft).txt               parentheses, 2026-11-02
    already-clean-name.jpg          already slug-clean, 2026-11-02
    .hidden-notes.txt               hidden — never touched
    raw/RAW_keep_me.dng             subfolder — never entered

Modification times are set explicitly (midday local time)
so the `date-title` scheme has something real to work with.
File contents are tiny stand-in bytes — this is a naming
demo, not real media.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

FILES = [
    ("IMG_4021.jpg", "stand-in bytes for a camera photo\n",
     (2026, 10, 31)),
    ("my trip to the Lake!!.mp4", "stand-in bytes for a video\n",
     (2026, 10, 31)),
    ("Podcast Ep 3 - final FINAL.mp3",
     "stand-in bytes for an audio file\n", (2026, 11, 1)),
    ("notes (draft).txt", "shoot notes, draft\n", (2026, 11, 2)),
    ("already-clean-name.jpg", "already tidy\n", (2026, 11, 2)),
    (".hidden-notes.txt", "hidden — scaffolder leaves me alone\n",
     (2026, 11, 2)),
]


def main():
    if len(sys.argv) > 2:
        print("usage: make_sample.py [TARGET_DIR]")
        return 2
    target = (Path(sys.argv[1]) if len(sys.argv) == 2
              else Path(__file__).parent / "messy-folder")
    target.mkdir(parents=True, exist_ok=True)
    for name, text, (y, m, d) in FILES:
        p = target / name
        p.write_text(text, encoding="utf-8")
        ts = datetime(y, m, d, 12, 0, 0).timestamp()
        os.utime(p, (ts, ts))
    raw = target / "raw"
    raw.mkdir(exist_ok=True)
    (raw / "RAW_keep_me.dng").write_text(
        "stand-in bytes for a raw file in a subfolder\n",
        encoding="utf-8")
    print(f"Created {target} with {len(FILES)} files "
          f"(+ 1 subfolder `raw/`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
