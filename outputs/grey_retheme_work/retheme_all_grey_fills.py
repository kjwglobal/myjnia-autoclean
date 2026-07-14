from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPLACEMENTS = {
    b'<fgColor theme="2" tint="-9.9978637043366805E-2"/>': b'<fgColor rgb="FFDDEBF7"/>',
    b'<fgColor theme="2"/>': b'<fgColor rgb="FFEAF4FC"/>',
    b'<fgColor theme="2" tint="-0.249977111117893"/>': b'<fgColor rgb="FFBDD7EE"/>',
    b'<fgColor theme="2" tint="-0.49995422223578601"/>': b'<fgColor rgb="FF9DC3E6"/>',
}


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "xl/styles.xml":
                changed = data
                for old, new in REPLACEMENTS.items():
                    if old not in changed:
                        raise RuntimeError(f"Expected style color marker missing: {old!r}")
                    changed = changed.replace(old, new, 1)
                data = changed
            zout.writestr(info, data)


if __name__ == "__main__":
    main()
