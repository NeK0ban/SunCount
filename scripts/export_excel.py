"""Собирает все CSV из data/ и results/ в один Excel-файл для просмотра: SunCount_data.xlsx.

CSV остаются основным форматом (их читает код); xlsx — только для удобного просмотра,
его можно в любой момент пересоздать этим скриптом.
"""
from pathlib import Path

import pandas as pd
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SunCount_data.xlsx"

csv_files = sorted((ROOT / "data").glob("*.csv")) + sorted((ROOT / "results").glob("*.csv"))

with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    for path in csv_files:
        df = pd.read_csv(path, encoding="utf-8-sig")
        sheet = path.stem[:31]  # ограничение Excel на длину имени листа
        df.to_excel(xw, sheet_name=sheet, index=False)
        ws = xw.sheets[sheet]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, col in enumerate(df.columns, start=1):
            width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)])
            ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 60)
        print(f"{sheet}: {len(df)} строк")

print("Готово:", OUT)
