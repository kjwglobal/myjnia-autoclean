from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def main() -> None:
    path = Path(sys.argv[1])
    with zipfile.ZipFile(path, "r") as zf:
        root = ET.fromstring(zf.read("xl/theme/theme1.xml"))
    scheme = root.find(".//a:clrScheme", NS)
    rows = []
    if scheme is not None:
        for index, child in enumerate(list(scheme)):
            srgb = child.find(".//a:srgbClr", NS)
            sysclr = child.find(".//a:sysClr", NS)
            rows.append(
                {
                    "index": index,
                    "name": child.tag.split("}")[-1],
                    "color": srgb.get("val") if srgb is not None else sysclr.get("lastClr") if sysclr is not None else None,
                }
            )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
