import pandas as pd
import requests
from pathlib import Path

SRC = Path(r"healthnet_ratefiles\2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json")
URL = "https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json"

# Excel
for name, df in pd.read_excel("healthnet_toc_plans.xlsx", sheet_name=None).items():
    print(name, df.shape)
    print(df.head(3))

# CSV preview
print(pd.read_csv("rates.csv", nrows=5))

# Folder listing
for p in Path("healthnet_ratefiles").iterdir():
    print(p.name, round(p.stat().st_size / 1e6, 1), "MB")

# Local vs server size
try:
    r = requests.head(URL, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
    print("server GB:", int(r.headers.get("Content-Length", 0)) / 1e9,
          "| local GB:", SRC.stat().st_size / 1e9)
except Exception as e:
    print("HEAD failed:", e)

# File ending (should close with ] and })
with open(SRC, "rb") as f:
    f.seek(-200, 2)
    print(f.read().decode("utf-8", "ignore"))