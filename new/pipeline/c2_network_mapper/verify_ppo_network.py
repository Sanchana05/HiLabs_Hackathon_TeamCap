"""Evidence-backed C2 classification of California commercial group PPO plan-file edges."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import pandas as pd

from pipeline.config import (
    EVIDENCE_REGISTER_PATHS,
    FILE_MIXED,
    FILE_PPO_ONLY,
    FILE_UNKNOWN,
    NET_CONFIRMED,
    NET_UNKNOWN,
    OUTPUTS_PPO_DIR,
    REGEX_CUSPPO,
    REGEX_EOA,
    REGEX_EPO,
    REGEX_HMO,
    REGEX_POS,
    REGEX_PPO,
    REGEX_RETIREE,
    STATUS_CONFIRMED_PPO,
    STATUS_EXCLUDED_NON_PPO,
    STATUS_OUT_OF_SCOPE,
    STATUS_PROVISIONAL_PPO,
    STATUS_UNRESOLVED,
    TARGET_SNAPSHOT_DATE,
)

logger = logging.getLogger(__name__)
RULE_VERSION = "2026.09-v3.0"
OFFICIAL_EOC_HOST = "www.healthnet.com"
REQUIRED_EVIDENCE_COLUMNS = {
    "evidence_id", "source_url", "document_type", "document_title",
    "exact_plan_name", "plan_year", "market", "state", "network_name", "decision",
}
REQUIRED_PLAN_COLUMNS = {
    "brand", "plan_name", "plan_id", "plan_id_type", "market_type",
    "issuer_name", "rate_file_url", "source_index", "last_updated_on",
}
REVIEW_COLUMNS = [
    "plan_name", "plan_id", "plan_id_type", "source_index", "rate_file_url",
    "product_status", "candidate_bucket", "anomaly_tags", "decision_reason",
    "evidence_needed",
]


def normalize_name(value: str) -> str:
    """Normalize case and whitespace only; never merge different benefit variants."""
    return " ".join(str(value).casefold().split())


def extract_state_from_url(url: str) -> Optional[str]:
    """Read an explicit state marker from a published TiC file URL."""
    path = urlsplit(str(url)).path.casefold()
    match = re.search(r"(?:healthnet|ambetter|centene|wellcare|fidelis|qualchoice)-([a-z]{2})(?:[-_.]|$)", path)
    return match.group(1).upper() if match else None


def _as_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


class PPOVerificationEngine:
    """Classify plan-file edges with explicit provenance and conservative file attribution."""

    def __init__(self, evidence_csv_path: Optional[Path] = None):
        self.evidence_path = self._resolve_evidence_path(evidence_csv_path)
        self.exact_plan_eoc_map = self._load_evidence_register(self.evidence_path)

    @staticmethod
    def _resolve_evidence_path(path: Optional[Path]) -> Path:
        if path is not None:
            target = Path(path)
            if not target.is_file():
                raise FileNotFoundError(f"C2 evidence register not found: {target}")
            return target
        for target in EVIDENCE_REGISTER_PATHS:
            if target.is_file():
                return target
        raise FileNotFoundError("C2 requires a versioned PPO evidence register")

    @staticmethod
    def _load_evidence_register(path: Path) -> Dict[str, Dict[str, str]]:
        rows = pd.read_csv(path, dtype=str, keep_default_na=False)
        missing = REQUIRED_EVIDENCE_COLUMNS - set(rows.columns)
        if missing or rows.empty:
            raise ValueError(f"Invalid C2 evidence register: missing={sorted(missing)}, empty={rows.empty}")
        by_name: Dict[str, Dict[str, str]] = {}
        ids = set()
        for record in rows.to_dict("records"):
            evidence_id = record["evidence_id"].strip()
            name = normalize_name(record["exact_plan_name"])
            url = urlsplit(record["source_url"].strip())
            if not evidence_id or evidence_id in ids or not name or name in by_name:
                raise ValueError(f"Duplicate or missing C2 evidence identity: {evidence_id}, {name}")
            if (
                record["plan_year"].strip() != "2026"
                or record["market"].strip().casefold() != "group"
                or record["state"].strip().upper() != "CA"
                or record["document_type"].strip().upper() != "EOC"
                or record["decision"].strip() != STATUS_CONFIRMED_PPO
                or "PPO" not in record["exact_plan_name"].upper()
                or normalize_name(record["document_title"]) != normalize_name("Full Network " + record["exact_plan_name"])
                or record["network_name"].strip() != "Full Network PPO"
                or url.scheme != "https"
                or url.netloc.casefold() != OFFICIAL_EOC_HOST
                or not url.path.endswith("-2026.pdf")
            ):
                raise ValueError(f"Unsupported or unverified C2 evidence entry: {evidence_id}")
            ids.add(evidence_id)
            by_name[name] = record
        logger.info("Loaded %d official 2026 PPO EOCs from %s", len(by_name), path)
        return by_name

    def evaluate_scope_gates(self, row: Dict) -> Tuple[bool, List[str], Dict]:
        brand = str(row.get("brand") or "").strip().casefold()
        market = str(row.get("market_type") or "").strip().casefold()
        name = str(row.get("plan_name") or "")
        url = str(row.get("rate_file_url") or "")
        source = str(row.get("source_index") or "").casefold()
        state = extract_state_from_url(url)
        updated = _as_iso_date(row.get("last_updated_on") or "")
        cutoff = date.fromisoformat(TARGET_SNAPSHOT_DATE)
        checks = {
            "centene_brand": brand in {"healthnet", "ambetter", "fidelis", "qualchoice", "centene_corporate"},
            "california_file": state == "CA",
            "commercial_group": market == "group" and not bool(re.search(r"medicare|medicaid|medi-cal|exchange", name, re.I)),
            "source_index_present": bool(source and source.endswith("_index.json")),
            "snapshot_on_or_before_cutoff": updated is not None and updated <= cutoff,
        }
        failures = [key.upper() for key, passed in checks.items() if not passed]
        return not failures, failures, {"url_state": state or "", "index_date": updated.isoformat() if updated else "", **checks}

    @staticmethod
    def generate_candidate_bucket(plan_name: str) -> Tuple[str, List[str]]:
        name = str(plan_name)
        ppo = bool(REGEX_PPO.search(name) or REGEX_CUSPPO.search(name))
        hmo = bool(REGEX_HMO.search(name))
        epo = bool(REGEX_EPO.search(name))
        pos = bool(REGEX_POS.search(name))
        eoa = bool(REGEX_EOA.search(name))
        retiree = bool(REGEX_RETIREE.search(name))
        tags = []
        if REGEX_CUSPPO.search(name):
            tags.append("COLLAPSED_TOKEN_CUSPPO")
        if eoa:
            tags.append("EOA_OVERLAP_SENSITIVITY")
        if retiree:
            tags.append("RETIREE_OR_PUBLIC_WORD")
        if ppo and (hmo or epo or pos or eoa):
            tags.append("PPO_MIXED_WITH_OTHER_NETWORK")
            return "CONFLICT_REVIEW", tags
        if retiree:
            return "RETIREE_REVIEW", tags
        if eoa or hmo or epo or pos:
            return "NON_PPO_CANDIDATE", tags
        if ppo:
            return "PPO_CANDIDATE", tags
        return "UNLABELED_REVIEW", tags

    def classify_and_verify_plan(self, row: Dict) -> Dict:
        name = str(row.get("plan_name") or "").strip()
        plan_id = str(row.get("plan_id") or "").strip()
        id_type = str(row.get("plan_id_type") or "").strip().casefold()
        source = str(row.get("source_index") or "")
        url = str(row.get("rate_file_url") or "")
        scope, failures, _ = self.evaluate_scope_gates(row)
        bucket, tags = self.generate_candidate_bucket(name)
        if id_type == "ein" and not re.fullmatch(r"[0-9]{9}", plan_id):
            tags.append("INVALID_EIN_FORMAT")
        if id_type not in {"ein", "hios"}:
            tags.append("UNKNOWN_PLAN_ID_TYPE")

        decision = {
            "plan_name": name, "plan_id": plan_id, "plan_id_type": id_type,
            "source_index": source, "rate_file_url": url,
            "product_status": STATUS_UNRESOLVED, "network_status": NET_UNKNOWN,
            "network_name": "", "service_area": "",
            "candidate_bucket": bucket, "decision_reason": "",
            "evidence_ids": "", "evidence_source_url": "", "evidence_match_basis": "",
            "evidence_needed": "", "anomaly_tags": ";".join(tags), "rule_version": RULE_VERSION,
        }
        if not scope:
            decision.update(product_status=STATUS_OUT_OF_SCOPE, candidate_bucket="OUT_OF_SCOPE",
                            decision_reason="Failed scope gates: " + ";".join(failures))
            return decision
        if bucket == "CONFLICT_REVIEW":
            decision.update(decision_reason="Plan name contains PPO and another network type; inspect plan-specific EOC.",
                            evidence_needed="Plan-specific 2026 EOC resolving PPO/HMO/EPO/POS overlap")
            return decision
        if bucket == "RETIREE_REVIEW":
            decision.update(decision_reason="Retiree or public-program token requires active commercial-group eligibility review.",
                            evidence_needed="Employer eligibility and plan-specific 2026 EOC")
            return decision
        if bucket == "NON_PPO_CANDIDATE":
            decision.update(product_status=STATUS_EXCLUDED_NON_PPO,
                            decision_reason="Explicit HMO, EPO, POS, or EOA label; excluded from pure PPO candidate set.")
            return decision

        evidence = self.exact_plan_eoc_map.get(normalize_name(name))
        # An EIN identifies a sponsor, not a product. With an official exact-name
        # EOC, it corroborates product type but never provider membership.
        source_is_healthnet = "healthnet_index.json" in source.casefold()
        issuer_is_healthnet = "healthnet" in str(row.get("issuer_name") or "").casefold().replace(" ", "")
        evidence_id_type = evidence.get("plan_id_type", "").strip().casefold() if evidence else ""
        evidence_plan_id = evidence.get("plan_id", "").strip() if evidence else ""
        identity_matches = (
            (id_type == "ein" and not evidence_plan_id)
            or (id_type == "hios" and evidence_id_type == "hios" and evidence_plan_id == plan_id)
            or (id_type == "ein" and evidence_id_type == "ein" and evidence_plan_id == plan_id)
        )
        if evidence and source_is_healthnet and issuer_is_healthnet and identity_matches:
            basis = "EXACT_NAME_2026_EOC;INDEX_EIN_NOT_PRODUCT_ID" if id_type == "ein" else "EXACT_NAME_AND_HIOS_ID_2026_EOC"
            decision.update(
                product_status=STATUS_CONFIRMED_PPO,
                network_status=NET_CONFIRMED,
                network_name=evidence["network_name"],
                service_area="CA (documented product; provider footprint unverified)",
                decision_reason=("Exact plan title in Health Net official 2026 small-group PPO EOC; "
                                 "index EIN is sponsor-level, not a product ID." if id_type == "ein"
                                 else "Exact plan title and HIOS product ID in Health Net official 2026 small-group PPO EOC."),
                evidence_ids=evidence["evidence_id"],
                evidence_source_url=evidence["source_url"],
                evidence_match_basis=basis,
            )
            return decision
        if bucket == "PPO_CANDIDATE":
            reasons = ["Explicit PPO token in an in-scope California group index"]
            if evidence and not (identity_matches and source_is_healthnet and issuer_is_healthnet):
                reasons.append("official EOC title exists but index issuer, source, or identifier does not match")
            else:
                reasons.append("no exact applicable official 2026 EOC")
            decision.update(
                product_status=STATUS_PROVISIONAL_PPO,
                decision_reason="; ".join(reasons) + ".",
                evidence_needed="Plan-specific 2026 EOC or certificate with matching product identity and network",
            )
            return decision
        decision.update(decision_reason="No unambiguous PPO product evidence or network token.",
                        evidence_needed="Plan-specific 2026 EOC or certificate")
        return decision

    @staticmethod
    def build_file_manifest(decisions: pd.DataFrame) -> pd.DataFrame:
        """One row per URL; this says which plans reference a file, not which providers join a network."""
        columns = [
            "rate_file_url", "rate_file_name", "file_classification", "plan_attribution_limitation",
            "total_linked_plans", "confirmed_ppo_plans", "provisional_ppo_plans",
            "excluded_non_ppo_plans", "out_of_scope_plans", "unresolved_plans", "sample_ppo_plans",
        ]
        files = []
        for url, group in decisions.groupby("rate_file_url", sort=True):
            if not url:
                continue
            counts = group["product_status"].value_counts()
            confirmed = int(counts.get(STATUS_CONFIRMED_PPO, 0))
            provisional = int(counts.get(STATUS_PROVISIONAL_PPO, 0))
            excluded = int(counts.get(STATUS_EXCLUDED_NON_PPO, 0))
            out_scope = int(counts.get(STATUS_OUT_OF_SCOPE, 0))
            unresolved = int(counts.get(STATUS_UNRESOLVED, 0))
            if confirmed + provisional and excluded + out_scope:
                classification = FILE_MIXED
            elif confirmed and not provisional and not unresolved:
                classification = FILE_PPO_ONLY
            else:
                classification = FILE_UNKNOWN
            files.append({
                "rate_file_url": url,
                "rate_file_name": Path(unquote(urlsplit(url).path)).name,
                "file_classification": classification,
                "plan_attribution_limitation": (
                    "SHARED_FILE_UNRESOLVED" if classification == FILE_MIXED
                    else "PROVIDER_NETWORK_MEMBERSHIP_UNVERIFIED"
                ),
                "total_linked_plans": len(group),
                "confirmed_ppo_plans": confirmed,
                "provisional_ppo_plans": provisional,
                "excluded_non_ppo_plans": excluded,
                "out_of_scope_plans": out_scope,
                "unresolved_plans": unresolved,
                "sample_ppo_plans": json.dumps(group[group["product_status"].isin(
                    [STATUS_CONFIRMED_PPO, STATUS_PROVISIONAL_PPO]
                )]["plan_name"].head(5).tolist()),
            })
        return pd.DataFrame(files, columns=columns)

    @staticmethod
    def select_ppo_files(manifest: pd.DataFrame) -> pd.DataFrame:
        return manifest[(manifest["confirmed_ppo_plans"] > 0) |
                        (manifest["provisional_ppo_plans"] > 0)].copy()

    def verify_all_plans(self, plans_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
        missing = REQUIRED_PLAN_COLUMNS - set(plans_df.columns)
        if missing:
            raise ValueError(f"C2 requires C1 provenance columns: {sorted(missing)}")
        if plans_df.empty:
            raise ValueError("C2 received no plan-file edges")
        if plans_df[list(REQUIRED_PLAN_COLUMNS)].isna().any().any():
            raise ValueError("C2 input contains null values in required columns")
        decisions = pd.DataFrame([
            {**row, **self.classify_and_verify_plan(row)}
            for row in plans_df.to_dict("records")
        ])
        manifest = self.build_file_manifest(decisions)
        review = decisions[decisions["product_status"].isin(
            [STATUS_PROVISIONAL_PPO, STATUS_UNRESOLVED]
        )][REVIEW_COLUMNS].copy()
        counts = decisions["product_status"].value_counts()
        summary = {
            "total_plan_file_edges_audited": len(decisions),
            "confirmed_ppo_count": int(counts.get(STATUS_CONFIRMED_PPO, 0)),
            "provisional_ppo_count": int(counts.get(STATUS_PROVISIONAL_PPO, 0)),
            "excluded_non_ppo_count": int(counts.get(STATUS_EXCLUDED_NON_PPO, 0)),
            "out_of_scope_count": int(counts.get(STATUS_OUT_OF_SCOPE, 0)),
            "unresolved_count": int(counts.get(STATUS_UNRESOLVED, 0)),
            "review_queue_count": len(review),
            "unique_rate_files_count": len(manifest),
            "mixed_rate_files_count": int((manifest["file_classification"] == FILE_MIXED).sum()),
            "ppo_only_rate_files_count": int((manifest["file_classification"] == FILE_PPO_ONLY).sum()),
            "invalid_ein_format_count": int(decisions["anomaly_tags"].str.contains("INVALID_EIN_FORMAT", regex=False).sum()),
            "collapsed_ppo_token_count": int(decisions["anomaly_tags"].str.contains("COLLAPSED_TOKEN_CUSPPO", regex=False).sum()),
            "retiree_review_count": int(decisions["candidate_bucket"].eq("RETIREE_REVIEW").sum()),
            "conflict_review_count": int(decisions["candidate_bucket"].eq("CONFLICT_REVIEW").sum()),
            "rule_version": RULE_VERSION,
            "evidence_register": self.evidence_path.name,
            "evidence_sha256": hashlib.sha256(self.evidence_path.read_bytes()).hexdigest(),
        }
        return decisions, manifest, review, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence-backed C2 PPO classifier")
    parser.add_argument("--plans", type=Path, required=True, help="C1 deduplicated plan-file CSV")
    parser.add_argument("--evidence", type=Path, default=None, help="Official plan-specific EOC register")
    parser.add_argument("--output", type=Path, default=OUTPUTS_PPO_DIR, help="Output directory")
    args = parser.parse_args()
    engine = PPOVerificationEngine(args.evidence)
    plans = pd.read_csv(args.plans, dtype=str, keep_default_na=False)
    decisions, manifest, review, summary = engine.verify_all_plans(plans)
    args.output.mkdir(parents=True, exist_ok=True)
    decisions.to_csv(args.output / "plan_decisions.csv", index=False)
    engine.select_ppo_files(manifest).to_csv(args.output / "file_manifest.csv", index=False)
    manifest.to_csv(args.output / "all_file_inventory.csv", index=False)
    review.to_csv(args.output / "review_queue.csv", index=False)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
