import ijson, csv
import pandas as pd

SRC = r"healthnet_ratefiles\2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json"
CODES = {"99213", "99214"}      # set to None for all codes (huge output)

# Pass 1: provider references (if the file has them)
refs = {}
with open(SRC, "rb") as f:
    for pr in ijson.items(f, "provider_references.item"):
        refs[pr["provider_group_id"]] = pr.get("provider_groups", [])

# Pass 2: negotiated rates to CSV
with open(SRC, "rb") as f, open("rates.csv", "w", newline="", encoding="utf-8") as out:
    w = csv.writer(out)
    w.writerow(["billing_code_type", "billing_code", "description",
                "tin", "npi_count", "negotiated_type", "negotiated_rate",
                "billing_class", "service_code", "expiration_date"])
    for item in ijson.items(f, "in_network.item"):
        if CODES and item["billing_code"] not in CODES:
            continue
        for nr in item.get("negotiated_rates", []):
            groups = list(nr.get("provider_groups", []))
            for rid in nr.get("provider_references", []):
                groups += refs.get(rid, [])
            for g in groups:
                tin = g.get("tin", {}).get("value", "")
                for pr in nr["negotiated_prices"]:
                    w.writerow([item["billing_code_type"], item["billing_code"],
                                item.get("description", ""), tin,
                                len(g.get("npi", [])),
                                pr["negotiated_type"], pr["negotiated_rate"],
                                pr.get("billing_class", ""),
                                "|".join(pr.get("service_code", [])),
                                pr.get("expiration_date", "")])

# Optional: Excel only if it fits (limit 1,048,576 rows)
df = pd.read_csv("rates.csv", dtype=str)
print("rows:", len(df))
if len(df) < 1_000_000:
    df.to_excel("rates.xlsx", index=False)
else:
    df.to_parquet("rates.parquet")   # needs: pip install pyarrow