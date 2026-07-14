from __future__ import annotations

import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


def sheet_name_map(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: "xl/" + rel.attrib["Target"].lstrip("/")
        for rel in rels.findall("r:Relationship", NS_REL)
    }
    mapping: dict[str, str] = {}
    for sheet in workbook.findall(".//x:sheet", NS_MAIN):
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        if rid and rid in targets:
            mapping[targets[rid]] = sheet.attrib.get("name", targets[rid])
    return mapping


def main() -> None:
    path = Path(sys.argv[1])
    with zipfile.ZipFile(path, "r") as zf:
        styles = ET.fromstring(zf.read("xl/styles.xml"))
        fills_node = styles.find("x:fills", NS_MAIN)
        xfs_node = styles.find("x:cellXfs", NS_MAIN)
        fills = list(fills_node) if fills_node is not None else []
        xfs = list(xfs_node) if xfs_node is not None else []
        fill_by_xf = [int(xf.attrib.get("fillId", "0")) for xf in xfs]
        sheet_names = sheet_name_map(zf)

        counts_by_sheet: dict[str, Counter[int]] = defaultdict(Counter)
        refs_by_fill: dict[int, list[str]] = defaultdict(list)
        for name in zf.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            sheet = sheet_names.get(name, name)
            root = ET.fromstring(zf.read(name))
            for cell in root.findall(".//x:c", NS_MAIN):
                style = int(cell.attrib.get("s", "0"))
                fill_id = fill_by_xf[style] if style < len(fill_by_xf) else 0
                counts_by_sheet[sheet][fill_id] += 1
                if len(refs_by_fill[fill_id]) < 12:
                    refs_by_fill[fill_id].append(f"{sheet}!{cell.attrib.get('r', '')}")

        output = []
        all_counts = Counter()
        for counts in counts_by_sheet.values():
            all_counts.update(counts)
        for fill_id, cell_count in sorted(all_counts.items()):
            fill = fills[fill_id] if fill_id < len(fills) else None
            output.append(
                {
                    "fillId": fill_id,
                    "cellCount": cell_count,
                    "xml": ET.tostring(fill, encoding="unicode") if fill is not None else "",
                    "bySheet": {
                        sheet: counts[fill_id]
                        for sheet, counts in sorted(counts_by_sheet.items())
                        if counts[fill_id]
                    },
                    "sampleCells": refs_by_fill[fill_id],
                }
            )
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
