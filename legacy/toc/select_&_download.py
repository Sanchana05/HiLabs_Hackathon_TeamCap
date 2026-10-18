import json, re, shutil, requests
from pathlib import Path
from urllib.parse import urlparse, unquote

INDEX_PATH = "./healthnet_index.json"
OUT_DIR = Path("healthnet_ratefiles")
TARGET_STATE = "ca"
PPO_RE = re.compile(r"\bPPO\b", re.I)
HEADERS = {"User-Agent": "Mozilla/5.0"}

def state_from_url(url):
    name = unquote(Path(urlparse(url).path).name).lower()
    m = re.search(r"_(?:healthnet|ambetter)-([a-z]{2})_", name)
    return m.group(1) if m else None

def main():
    data = json.load(open(INDEX_PATH))
    selected, skipped_state = {}, set()

    for block in data["reporting_structure"]:
        urls = [f["location"] for f in block.get("in_network_files", [])]
        urls_ca = [u for u in urls if state_from_url(u) == TARGET_STATE]
        if not urls_ca:
            skipped_state.update(urls)
            continue
        for p in block["reporting_plans"]:
            if (p.get("plan_market_type") or "").lower() != "group":
                continue
            if not PPO_RE.search(p.get("plan_name", "")):
                continue
            for u in urls_ca:
                selected.setdefault(u, []).append(p)

    OUT_DIR.mkdir(exist_ok=True)
    manifest = [{"url": u,
                 "ppo_plan_count": len(ps),
                 "sample_plans": [x["plan_name"] for x in ps[:10]]}
                for u, ps in selected.items()]
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print("Selected files:", len(selected))
    for m in manifest:
        print(" ", m["url"].rsplit("/", 1)[-1], "-", m["ppo_plan_count"], "PPO plans")
    print("Skipped (other state):", len(skipped_state))

    for url in selected:                      # in-network files only
        dest = OUT_DIR / unquote(Path(urlparse(url).path).name)
        server_size = 0
        try:
            h = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=60)
            server_size = int(h.headers.get("Content-Length", 0))
        except Exception:
            pass
        if dest.exists() and (not server_size or dest.stat().st_size == server_size):
            print("skip (complete)", dest.name)
            continue
        print("downloading", dest.name)
        with requests.get(url, stream=True, headers=HEADERS, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as out:
                shutil.copyfileobj(r.raw, out)

if __name__ == "__main__":
    main()