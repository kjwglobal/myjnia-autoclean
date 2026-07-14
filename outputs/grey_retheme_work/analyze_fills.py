from __future__ import annotations

import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_THEME = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

INDEXED_COLORS = {
    0: "FF000000",
    1: "FFFFFFFF",
    2: "FFFF0000",
    3: "FF00FF00",
    4: "FF0000FF",
    5: "FFFFFF00",
    6: "FFFF00FF",
    7: "FF00FFFF",
    8: "FF000000",
    9: "FFFFFFFF",
    10: "FFFF0000",
    11: "FF00FF00",
    12: "FF0000FF",
    13: "FFFFFF00",
    14: "FFFF00FF",
    15: "FF00FFFF",
    16: "FF800000",
    17: "FF008000",
    18: "FF000080",
    19: "FF808000",
    20: "FF800080",
    21: "FF008080",
    22: "FFC0C0C0",
    23: "FF808080",
    24: "FF9999FF",
    25: "FF993366",
    26: "FFFFFFCC",
    27: "FFCCFFFF",
    28: "FF660066",
    29: "FFFF8080",
    30: "FF0066CC",
    31: "FFCCCCFF",
    32: "FF000080",
    33: "FFFF00FF",
    34: "FFFFFF00",
    35: "FF00FFFF",
    36: "FF800080",
    37: "FF800000",
    38: "FF008080",
    39: "FF0000FF",
    40: "FF00CCFF",
    41: "FFCCFFFF",
    42: "FFCCFFCC",
    43: "FFFFFF99",
    44: "FF99CCFF",
    45: "FFFF99CC",
    46: "FFCC99FF",
    47: "FFFFCC99",
    48: "FF3366FF",
    49: "FF33CCCC",
    50: "FF99CC00",
    51: "FFFFCC00",
    52: "FFFF9900",
    53: "FFFF6600",
    54: "FF666699",
    55: "FF969696",
    56: "FF003366",
    57: "FF339966",
    58: "FF003300",
    59: "FF333300",
    60: "FF993300",
    61: "FF993366",
    62: "FF333399",
    63: "FF333333",
}


def parse_theme_colors(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/theme/theme1.xml"))
    except KeyError:
        return []

    scheme = root.find(".//a:clrScheme", NS_THEME)
    if scheme is None:
        return []

    # Excel style theme indexes are lt1, dk1, lt2, dk2, accent1..6, hlink, folHlink.
    order = [
        "lt1",
        "dk1",
        "lt2",
        "dk2",
        "accent1",
        "accent2",
        "accent3",
        "accent4",
        "accent5",
        "accent6",
        "hlink",
        "folHlink",
    ]
    colors: list[str] = []
    for name in order:
        node = scheme.find(f"a:{name}", NS_THEME)
        value = "000000"
        if node is not None:
            srgb = node.find(".//a:srgbClr", NS_THEME)
            sysclr = node.find(".//a:sysClr", NS_THEME)
            if srgb is not None and srgb.get("val"):
                value = srgb.get("val", "000000")
            elif sysclr is not None:
                value = sysclr.get("lastClr", sysclr.get("val", "000000"))
        colors.append("FF" + value.upper())
    return colors


def tint_channel(channel: int, tint: float) -> int:
    if tint < 0:
        return round(channel * (1 + tint))
    return round(channel * (1 - tint) + 255 * tint)


def apply_tint(argb: str, tint: float) -> str:
    rgb = argb[-6:]
    r = tint_channel(int(rgb[0:2], 16), tint)
    g = tint_channel(int(rgb[2:4], 16), tint)
    b = tint_channel(int(rgb[4:6], 16), tint)
    return f"FF{r:02X}{g:02X}{b:02X}"


def resolve_color(node: ET.Element | None, theme_colors: list[str]) -> str | None:
    if node is None:
        return None
    if "rgb" in node.attrib:
        value = node.attrib["rgb"].upper()
        if len(value) == 6:
            value = "FF" + value
        return value
    if "indexed" in node.attrib:
        try:
            return INDEXED_COLORS.get(int(node.attrib["indexed"]))
        except ValueError:
            return None
    if "theme" in node.attrib:
        try:
            base = theme_colors[int(node.attrib["theme"])]
        except (ValueError, IndexError):
            return None
        tint = float(node.attrib.get("tint", "0"))
        return apply_tint(base, tint)
    return None


def is_grey(argb: str | None) -> bool:
    if not argb:
        return False
    if argb[:2] == "00":
        return False
    rgb = argb[-6:]
    r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
    # Real grey fills in Excel are not always perfectly equal after theme tinting.
    return max(r, g, b) - min(r, g, b) <= 8 and 30 <= (r + g + b) / 3 <= 245


def sheet_name_map(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: "xl/" + rel.attrib["Target"].lstrip("/")
        for rel in rels.findall("r:Relationship", NS_REL)
    }
    mapping = {}
    for sheet in workbook.findall(".//x:sheet", NS_MAIN):
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        if rid and rid in rel_targets:
            mapping[rel_targets[rid]] = sheet.attrib.get("name", rel_targets[rid])
    return mapping


def main() -> None:
    path = Path(sys.argv[1])
    with zipfile.ZipFile(path, "r") as zf:
        theme_colors = parse_theme_colors(zf)
        styles_root = ET.fromstring(zf.read("xl/styles.xml"))
        fills = list(styles_root.find("x:fills", NS_MAIN) or [])
        cell_xfs = list(styles_root.find("x:cellXfs", NS_MAIN) or [])
        fill_by_xf = {
            idx: int(xf.attrib.get("fillId", "0"))
            for idx, xf in enumerate(cell_xfs)
            if xf.attrib.get("fillId", "0").isdigit()
        }

        grey_fills = {}
        all_fills = {}
        for idx, fill in enumerate(fills):
            pattern = fill.find("x:patternFill", NS_MAIN)
            fg = pattern.find("x:fgColor", NS_MAIN) if pattern is not None else None
            bg = pattern.find("x:bgColor", NS_MAIN) if pattern is not None else None
            color = resolve_color(fg, theme_colors) or resolve_color(bg, theme_colors)
            ptype = pattern.attrib.get("patternType") if pattern is not None else None
            all_fills[idx] = {"patternType": ptype, "resolvedColor": color, "xml": ET.tostring(fill, encoding="unicode")}
            if color and is_grey(color) and ptype not in (None, "none"):
                grey_fills[idx] = all_fills[idx]

        style_counts = Counter()
        style_refs_by_sheet = defaultdict(Counter)
        sheets = sheet_name_map(zf)
        for name in zf.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            sheet_root = ET.fromstring(zf.read(name))
            sheet_label = sheets.get(name, name)
            for cell in sheet_root.findall(".//x:c", NS_MAIN):
                s = cell.attrib.get("s")
                if s is None:
                    continue
                style_idx = int(s)
                fill_id = fill_by_xf.get(style_idx, 0)
                style_counts[fill_id] += 1
                style_refs_by_sheet[sheet_label][fill_id] += 1

        used_grey = {
            str(fill_id): {
                **grey_fills[fill_id],
                "cellCount": style_counts[fill_id],
                "bySheet": dict(style_refs_by_sheet_sheet for style_refs_by_sheet_sheet in []),
            }
            for fill_id in sorted(grey_fills)
            if style_counts[fill_id] > 0
        }
        for fill_id_str in used_grey:
            fill_id = int(fill_id_str)
            used_grey[fill_id_str]["bySheet"] = {
                sheet: count
                for sheet, counts in sorted(style_refs_by_sheet.items())
                if (count := counts[fill_id])
            }

        print(json.dumps({"path": str(path), "fillCount": len(fills), "greyFillsInUse": used_grey}, indent=2))


if __name__ == "__main__":
    main()
