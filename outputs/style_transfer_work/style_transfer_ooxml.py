from __future__ import annotations

import copy
import hashlib
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


TARGET = Path("/Users/kjw1/Desktop/Monitoring/332044_proj3_popr.xlsx")
WORK_DIR = Path("/Users/kjw1/Documents/New project/outputs/style_transfer_work")
OUTPUT_COPY = WORK_DIR / "332044_proj3_popr_styled.xlsx"

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
X14AC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
XR2_NS = "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2"
XR3_NS = "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3"

ET.register_namespace("", NS)
ET.register_namespace("r", REL_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("x14ac", X14AC_NS)
ET.register_namespace("xr", XR_NS)
ET.register_namespace("xr2", XR2_NS)
ET.register_namespace("xr3", XR3_NS)

Q = f"{{{NS}}}"
X14AC = f"{{{X14AC_NS}}}"


def rgb(hex_color: str) -> str:
    hex_color = hex_color.strip().replace("#", "").upper()
    return hex_color if len(hex_color) == 8 else f"FF{hex_color}"


COL_RE = re.compile(r"([A-Z]+)([0-9]+)")


def col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def num_to_col(num: int) -> str:
    out = ""
    while num:
        num, rem = divmod(num - 1, 26)
        out = chr(65 + rem) + out
    return out


def split_addr(addr: str) -> tuple[int, int]:
    m = COL_RE.fullmatch(addr)
    if not m:
        raise ValueError(f"Bad address: {addr}")
    return int(m.group(2)), col_to_num(m.group(1))


def iter_range(a1: str):
    start, end = (a1.split(":") + [a1])[:2]
    r1, c1 = split_addr(start)
    r2, c2 = split_addr(end)
    for row in range(min(r1, r2), max(r1, r2) + 1):
        for col in range(min(c1, c2), max(c1, c2) + 1):
            yield row, col, f"{num_to_col(col)}{row}"


def parse_xml(data: bytes) -> ET.ElementTree:
    return ET.ElementTree(ET.fromstring(data))


def formula_fingerprint(z: zipfile.ZipFile) -> str:
    items: list[str] = []
    for name in sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")):
        root = ET.fromstring(z.read(name))
        for cell in root.findall(f".//{Q}c"):
            formula = cell.find(f"{Q}f")
            if formula is None:
                continue
            attrs = " ".join(f"{k}={v}" for k, v in sorted(formula.attrib.items()))
            items.append(f"{name}!{cell.get('r')}|{attrs}|{formula.text or ''}")
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()


class StyleBook:
    def __init__(self, tree: ET.ElementTree):
        self.tree = tree
        self.root = tree.getroot()
        self.fonts = self.root.find(f"{Q}fonts")
        self.fills = self.root.find(f"{Q}fills")
        self.cell_xfs = self.root.find(f"{Q}cellXfs")
        if self.fonts is None or self.fills is None or self.cell_xfs is None:
            raise RuntimeError("styles.xml is missing fonts/fills/cellXfs")
        self.fill_cache: dict[str, str] = {}
        self.font_cache: dict[tuple[bool, str | None], str] = {}
        self.xf_cache: dict[tuple[str, str | None, str | None, str | None, bool], str] = {}

    def ensure_fill(self, color: str | None) -> str | None:
        if color is None:
            return None
        color = rgb(color)
        if color in self.fill_cache:
            return self.fill_cache[color]
        for i, fill in enumerate(self.fills):
            fg = fill.find(f".//{Q}fgColor")
            if fg is not None and fg.get("rgb", "").upper() == color:
                self.fill_cache[color] = str(i)
                return str(i)
        fill = ET.Element(f"{Q}fill")
        pattern = ET.SubElement(fill, f"{Q}patternFill", {"patternType": "solid"})
        ET.SubElement(pattern, f"{Q}fgColor", {"rgb": color})
        ET.SubElement(pattern, f"{Q}bgColor", {"indexed": "64"})
        self.fills.append(fill)
        idx = str(len(self.fills) - 1)
        self.fills.set("count", str(len(self.fills)))
        self.fill_cache[color] = idx
        return idx

    def ensure_font(self, bold: bool = False, color: str | None = None) -> str:
        key = (bold, rgb(color) if color else None)
        if key in self.font_cache:
            return self.font_cache[key]
        font = ET.Element(f"{Q}font")
        if bold:
            ET.SubElement(font, f"{Q}b")
        ET.SubElement(font, f"{Q}sz", {"val": "11"})
        if color:
            ET.SubElement(font, f"{Q}color", {"rgb": rgb(color)})
        else:
            ET.SubElement(font, f"{Q}color", {"theme": "1"})
        ET.SubElement(font, f"{Q}name", {"val": "Calibri"})
        ET.SubElement(font, f"{Q}family", {"val": "2"})
        self.fonts.append(font)
        idx = str(len(self.fonts) - 1)
        self.fonts.set("count", str(len(self.fonts)))
        self.font_cache[key] = idx
        return idx

    def style_variant(
        self,
        base_style: str,
        fill: str | None = None,
        font: tuple[bool, str | None] | None = None,
        align: str | None = "center",
        wrap: bool = False,
    ) -> str:
        key = (base_style, rgb(fill) if fill else None, str(font) if font else None, align, wrap)
        if key in self.xf_cache:
            return self.xf_cache[key]

        try:
            base = self.cell_xfs[int(base_style)]
        except (IndexError, ValueError):
            base = self.cell_xfs[0]
        xf = copy.deepcopy(base)

        fill_id = self.ensure_fill(fill)
        if fill_id is not None:
            xf.set("fillId", fill_id)
            xf.set("applyFill", "1")
        if font is not None:
            xf.set("fontId", self.ensure_font(*font))
            xf.set("applyFont", "1")
        if align is not None or wrap:
            old = xf.find(f"{Q}alignment")
            if old is not None:
                xf.remove(old)
            attrs = {"vertical": "center"}
            if align:
                attrs["horizontal"] = align
            if wrap:
                attrs["wrapText"] = "1"
            ET.SubElement(xf, f"{Q}alignment", attrs)
            xf.set("applyAlignment", "1")

        self.cell_xfs.append(xf)
        idx = str(len(self.cell_xfs) - 1)
        self.cell_xfs.set("count", str(len(self.cell_xfs)))
        self.xf_cache[key] = idx
        return idx


def worksheet_parts(root: ET.Element):
    sheet_data = root.find(f"{Q}sheetData")
    if sheet_data is None:
        raise RuntimeError("worksheet is missing sheetData")
    return sheet_data


def row_number(row: ET.Element) -> int:
    return int(row.get("r", "0"))


def get_or_create_row(sheet_data: ET.Element, row_idx: int) -> ET.Element:
    for row in sheet_data.findall(f"{Q}row"):
        r = row_number(row)
        if r == row_idx:
            return row
        if r > row_idx:
            new = ET.Element(f"{Q}row", {"r": str(row_idx), f"{X14AC}dyDescent": "0.2"})
            sheet_data.insert(list(sheet_data).index(row), new)
            return new
    new = ET.Element(f"{Q}row", {"r": str(row_idx), f"{X14AC}dyDescent": "0.2"})
    sheet_data.append(new)
    return new


def cell_col(cell: ET.Element) -> int:
    return split_addr(cell.get("r", "A1"))[1]


def get_or_create_cell(root: ET.Element, row_idx: int, col_idx: int) -> ET.Element:
    sheet_data = worksheet_parts(root)
    row = get_or_create_row(sheet_data, row_idx)
    addr = f"{num_to_col(col_idx)}{row_idx}"
    cells = row.findall(f"{Q}c")
    for cell in cells:
        c = cell_col(cell)
        if c == col_idx:
            return cell
        if c > col_idx:
            new = ET.Element(f"{Q}c", {"r": addr})
            row.insert(list(row).index(cell), new)
            update_spans(row)
            return new
    new = ET.Element(f"{Q}c", {"r": addr})
    row.append(new)
    update_spans(row)
    return new


def update_spans(row: ET.Element) -> None:
    cols = [cell_col(c) for c in row.findall(f"{Q}c")]
    if cols:
        row.set("spans", f"{min(cols)}:{max(cols)}")


def apply_range(
    root: ET.Element,
    styles: StyleBook,
    a1: str,
    fill: str | None = None,
    font: tuple[bool, str | None] | None = None,
    align: str | None = "center",
    wrap: bool = False,
    create_missing: bool = True,
):
    top_left = next(iter_range(a1))[2]
    top_left_style = "0"
    existing_top = root.find(f".//{Q}c[@r='{top_left}']")
    if existing_top is not None:
        top_left_style = existing_top.get("s", "0")

    for row_idx, col_idx, addr in iter_range(a1):
        cell = root.find(f".//{Q}c[@r='{addr}']")
        if cell is None:
            if not create_missing:
                continue
            cell = get_or_create_cell(root, row_idx, col_idx)
            base = top_left_style
        else:
            base = cell.get("s", top_left_style)
        cell.set("s", styles.style_variant(base, fill=fill, font=font, align=align, wrap=wrap))


def clear_blank_styles(root: ET.Element, a1: str) -> None:
    for _, _, addr in iter_range(a1):
        cell = root.find(f".//{Q}c[@r='{addr}']")
        if cell is None:
            continue
        has_content = any(cell.find(f"{Q}{tag}") is not None for tag in ("f", "v", "is"))
        if not has_content and cell.text is None:
            cell.set("s", "0")


def set_row_heights(root: ET.Element, rows: list[int], height: float) -> None:
    sheet_data = worksheet_parts(root)
    for idx in rows:
        row = get_or_create_row(sheet_data, idx)
        row.set("ht", str(height))
        row.set("customHeight", "1")


def set_cols(root: ET.Element, specs: list[tuple[str, str, float]]) -> None:
    old = root.find(f"{Q}cols")
    if old is not None:
        root.remove(old)
    cols = ET.Element(f"{Q}cols")
    for start, end, width in specs:
        ET.SubElement(
            cols,
            f"{Q}col",
            {
                "min": str(col_to_num(start)),
                "max": str(col_to_num(end)),
                "width": str(width),
                "customWidth": "1",
            },
        )
    sheet_data = worksheet_parts(root)
    root.insert(list(root).index(sheet_data), cols)


def set_dimension(root: ET.Element) -> None:
    cells = root.findall(f".//{Q}c")
    if not cells:
        return
    rows_cols = [split_addr(c.get("r")) for c in cells if c.get("r")]
    min_row = min(r for r, _ in rows_cols)
    max_row = max(r for r, _ in rows_cols)
    min_col = min(c for _, c in rows_cols)
    max_col = max(c for _, c in rows_cols)
    dim = root.find(f"{Q}dimension")
    if dim is None:
        dim = ET.Element(f"{Q}dimension")
        root.insert(0, dim)
    dim.set("ref", f"{num_to_col(min_col)}{min_row}:{num_to_col(max_col)}{max_row}")


def apply_dane(root: ET.Element, styles: StyleBook) -> None:
    set_cols(root, [
        ("A", "A", 5), ("B", "D", 10), ("E", "E", 12), ("F", "H", 10),
        ("I", "I", 12), ("J", "K", 5), ("L", "N", 12),
    ])
    set_row_heights(root, [3, 4], 18)
    apply_range(root, styles, "B2:C2", fill="D9EAF7", font=(True, None))
    apply_range(root, styles, "B3:I3", fill="3B0E0E", font=(True, "FFFFFF"))
    apply_range(root, styles, "B4:I4", fill="D99A99", font=(True, None))
    apply_range(root, styles, "L3:N3", fill="3B0E0E", font=(True, "FFFFFF"))
    apply_range(root, styles, "L4:N4", fill="3B0E0E", font=(True, "FFFFFF"))
    apply_range(root, styles, "L5:L13", fill="D99A99", font=(False, None))
    apply_range(root, styles, "L15:L16", fill="D99A99", font=(False, None))
    apply_range(root, styles, "M15:N16", fill=None, font=(False, None))


def apply_calc(root: ET.Element, styles: StyleBook) -> None:
    set_cols(root, [
        ("A", "A", 5), ("B", "D", 10), ("E", "E", 12), ("F", "G", 10),
        ("H", "M", 11), ("N", "P", 12), ("Q", "W", 11),
    ])
    set_row_heights(root, [3, 24, 25, 39, 40, 41], 18)
    apply_range(root, styles, "B3:M3", fill="3F3F3F", font=(True, "FFFFFF"))
    apply_range(root, styles, "N3:P3", fill="3F3F3F", font=(True, "FFFFFF"))
    apply_range(root, styles, "N4:P4", fill="D99A99", font=(True, None))
    apply_range(root, styles, "B25:T25", fill="3F3F3F", font=(True, "FFFFFF"))
    apply_range(root, styles, "B39:Q41", fill="3F3F3F", font=(False, "FFFFFF"))
    apply_range(root, styles, "S39:S41", fill="3F3F3F", font=(False, "FFFFFF"))


def apply_ident(root: ET.Element, styles: StyleBook) -> None:
    set_cols(root, [
        ("A", "A", 5), ("B", "P", 9), ("Q", "U", 5), ("V", "AP", 9),
        ("AQ", "AS", 9),
    ])
    header_ranges = [
        "B2:P2", "B25:P25", "V2:AP2", "V25:AP25",
        "B47:H47", "B53:C53", "E53:F53", "H53:I53", "K53:K53",
        "AQ2:AS2", "AQ25:AS25",
    ]
    for a1 in header_ranges:
        apply_range(root, styles, a1, fill="3F3F3F", font=(True, "FFFFFF"))
    apply_range(root, styles, "B22:P22", fill="1F4E78", font=(False, "FFFFFF"))
    apply_range(root, styles, "B45:P45", fill="1F4E78", font=(False, "FFFFFF"))


def apply_final(root: ET.Element, styles: StyleBook) -> None:
    set_cols(root, [
        ("A", "A", 5), ("B", "B", 10), ("C", "F", 12), ("G", "G", 5),
        ("H", "H", 5), ("I", "O", 13),
    ])
    set_row_heights(root, [1, 2, 3, 12, 13], 18)
    apply_range(root, styles, "C2:F2", fill="1F4E78", font=(True, "FFFFFF"))
    apply_range(root, styles, "C3:F3", fill="D99A99", font=(False, None))
    apply_range(root, styles, "B4:B21", fill="3B0E0E", font=(False, "FFFFFF"))
    apply_range(root, styles, "I2:O2", fill="D9EAD3", font=(True, None), wrap=True)
    apply_range(root, styles, "I3:O3", fill="D9EAD3", font=(True, None), wrap=True)
    apply_range(root, styles, "I12:L12", fill="1F4E78", font=(True, "FFFFFF"))
    apply_range(root, styles, "I13:L13", fill="D99A99", font=(False, None))
    apply_range(root, styles, "A13:G13", fill="FFFFFF", font=(False, None))
    clear_blank_styles(root, "M13:O28")
    apply_range(root, styles, "N1:O1", fill="FFF2CC", font=(True, None))


def write_zip_from_dir(src_dir: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as out:
        for item in sorted(src_dir.rglob("*")):
            if item.is_file():
                out.write(item, item.relative_to(src_dir).as_posix())


def main() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    backup = TARGET.with_name(f"{TARGET.stem}_backup_before_layout_style.xlsx")
    if not backup.exists():
        shutil.copy2(TARGET, backup)

    with zipfile.ZipFile(TARGET) as z:
        before_fp = formula_fingerprint(z)

    with tempfile.TemporaryDirectory(prefix="xlsx_style_transfer_") as td:
        tmp = Path(td)
        with zipfile.ZipFile(TARGET) as z:
            z.extractall(tmp)

        styles_path = tmp / "xl" / "styles.xml"
        styles_tree = parse_xml(styles_path.read_bytes())
        styles = StyleBook(styles_tree)

        sheet_actions = {
            "sheet1.xml": apply_dane,
            "sheet2.xml": apply_calc,
            "sheet3.xml": apply_calc,
            "sheet4.xml": apply_ident,
            "sheet5.xml": apply_calc,
            "sheet6.xml": apply_calc,
            "sheet7.xml": apply_final,
        }
        for sheet_file, action in sheet_actions.items():
            path = tmp / "xl" / "worksheets" / sheet_file
            tree = parse_xml(path.read_bytes())
            action(tree.getroot(), styles)
            set_dimension(tree.getroot())
            tree.write(path, encoding="UTF-8", xml_declaration=True)

        styles_tree.write(styles_path, encoding="UTF-8", xml_declaration=True)

        staged = WORK_DIR / "styled_staged.xlsx"
        write_zip_from_dir(tmp, staged)

    with zipfile.ZipFile(staged) as z:
        after_fp = formula_fingerprint(z)
    if before_fp != after_fp:
        raise RuntimeError("Formula fingerprint changed; refusing to replace target workbook.")

    shutil.copy2(staged, TARGET)
    shutil.copy2(staged, OUTPUT_COPY)
    print(f"Backup: {backup}")
    print(f"Updated target: {TARGET}")
    print(f"Output copy: {OUTPUT_COPY}")
    print(f"Formula fingerprint: {after_fp}")


if __name__ == "__main__":
    main()
