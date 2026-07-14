import openpyxl

path = "/Users/kjw1/Desktop/Monitoring/332044_proj3_popr.xlsx"
wb = openpyxl.load_workbook(path, data_only=False)

terms = ["m0", "baza", "kierunek", "współrzędne", "zidentyfik"]

for ws in wb.worksheets:
    hits = []
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if isinstance(value, str):
                low = value.lower()
                if any(term in low for term in terms):
                    hits.append((cell.coordinate, value))
    if hits:
        print(f"\n--- {ws.title} ---")
        for hit in hits[:120]:
            print(hit)
