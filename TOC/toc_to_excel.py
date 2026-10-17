import json, re
import pandas as pd

data = json.load(open("healthnet_index.json"))
ppo = re.compile(r"\bPPO\b", re.I)
rows = []
for b in data["reporting_structure"]:
    url = b["in_network_files"][0]["location"]
    for p in b["reporting_plans"]:
        rows.append({
            "plan_name": p["plan_name"],
            "plan_id_type": p["plan_id_type"],
            "plan_id": p["plan_id"],
            "market": p["plan_market_type"],
            "is_ppo": bool(ppo.search(p["plan_name"])),
            "in_network_url": url,
        })

df = pd.DataFrame(rows)
with pd.ExcelWriter("healthnet_toc_plans.xlsx") as w:
    df.to_excel(w, sheet_name="all_plans", index=False)
    df[df.is_ppo & df.in_network_url.str.contains("healthnet-ca_")] \
      .to_excel(w, sheet_name="CA_PPO", index=False)