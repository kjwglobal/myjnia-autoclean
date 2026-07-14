import openpyxl

path = "/Users/kjw1/Desktop/Monitoring/332044_proj3_popr.xlsx"
wbv = openpyxl.load_workbook(path, data_only=True)
wbf = openpyxl.load_workbook(path, data_only=False)

for sheet in [
    "Wyrównanie wstępne - wyjściowy",
    "Wyrównanie wstępne - aktualny",
    "Baza - wyjściowy",
    "Baza - aktualny",
    "Identyfikacja",
]:
    print(f"\n--- {sheet} ---")
    ws_v = wbv[sheet]
    ws_f = wbf[sheet]
    for coord in ["AA131", "AB131", "AO190", "AP190", "AO191", "AP191", "Y112", "Z112", "AA112", "AR2", "AR25", "AS2", "AS25"]:
        print(coord, "value=", ws_v[coord].value, "formula=", ws_f[coord].value)
