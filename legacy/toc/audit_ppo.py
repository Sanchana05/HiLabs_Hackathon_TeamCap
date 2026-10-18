import json, re

data = json.load(open("./healthnet_index.json"))
ppo = re.compile(r"\bPPO\b", re.I)
epo = re.compile(r"\bEPO\b", re.I)

ca = [b for b in data["reporting_structure"]
      if "healthnet-ca_" in b["in_network_files"][0]["location"]][0]

plans = [p for p in ca["reporting_plans"] if p["plan_market_type"] == "group"]
ppo_plans = [p for p in plans if ppo.search(p["plan_name"])]
mixed = [p["plan_name"] for p in ppo_plans if epo.search(p["plan_name"])]

print("CA group plans:", len(plans))
print("PPO matches:", len(ppo_plans))
print("Unique PPO plan names:", len({p["plan_name"] for p in ppo_plans}))
print("Unique EINs among PPO plans:", len({p["plan_id"] for p in ppo_plans}))
print("PPO names that also say EPO:", mixed)