from __future__ import annotations

import difflib
import sys
import zipfile
from pathlib import Path


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    with zipfile.ZipFile(src, "r") as zs, zipfile.ZipFile(dst, "r") as zd:
        src_names = set(zs.namelist())
        dst_names = set(zd.namelist())
        changed = []
        for name in sorted(src_names & dst_names):
            if zs.read(name) != zd.read(name):
                changed.append(name)

        print("changed_entries:", changed)
        print("missing_entries:", sorted(src_names - dst_names))
        print("extra_entries:", sorted(dst_names - src_names))

        original = zs.read("xl/styles.xml").decode("utf-8")
        modified = zd.read("xl/styles.xml").decode("utf-8")
        for line in difflib.unified_diff(
            [original],
            [modified],
            fromfile="original xl/styles.xml",
            tofile="modified xl/styles.xml",
            lineterm="",
        ):
            print(line)


if __name__ == "__main__":
    main()
