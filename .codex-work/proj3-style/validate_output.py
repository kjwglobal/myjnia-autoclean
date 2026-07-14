import openpyxl

path = "/Users/kjw1/Documents/New project/outputs/proj3_style_20260612/332044_proj3_popr_styl_reference_uzupelniony.xlsx"
wb = openpyxl.load_workbook(path, data_only=False)

formula_bad = []
old_sheet_refs = []
visible_errors = []

for ws in wb.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if isinstance(value, str) and value.startswith("="):
                if any(token in value for token in ["#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#N/A"]):
                    formula_bad.append((ws.title, cell.coordinate, value[:120]))
                for old_name in [
                    "Wyrównanie wstępne - wyjściowy",
                    "Wyrównanie wstępne - aktualny",
                    "Identyfikacja",
                    "Baza - wyjściowy",
                    "Baza - aktualny",
                    "Przemieszczenia ",
                ]:
                    if f"{old_name}!" in value or f"'{old_name}'!" in value:
                        old_sheet_refs.append((ws.title, cell.coordinate, value[:120]))
            elif ws.sheet_state == "visible" and isinstance(value, str) and value.startswith("#"):
                visible_errors.append((ws.title, cell.coordinate, value))

print("formula_bad", len(formula_bad))
for item in formula_bad[:30]:
    print(item)
print("old_sheet_refs", len(old_sheet_refs))
for item in old_sheet_refs[:30]:
    print(item)
print("visible_errors", len(visible_errors))
for item in visible_errors[:30]:
    print(item)
