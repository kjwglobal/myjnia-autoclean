import openpyxl

path = "/Users/kjw1/Desktop/Monitoring/332044_proj3_popr.xlsx"
wb = openpyxl.load_workbook(path, data_only=True)

errors = []
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("#"):
                errors.append((ws.title, cell.coordinate, cell.value))

print(f"errors={len(errors)}")
for item in errors[:100]:
    print(item)
