"""Deterministic Verification of Centene California Commercial Group PPO Network.
Implements the 8-step classification plan with formal evidence hierarchy,
distinct product vs network statuses, anomaly queues, and mixed-file auditing.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit

import pandas as pd

try:
    from pipeline.config import (
        CONFIG_DIR,
        DELIVERABLES_DIR,
        EVIDENCE_REGISTER_PATHS,
        FILE_MIXED,
        FILE_PPO_ONLY,
        FILE_UNKNOWN,
        NET_CONFIRMED,
        NET_PROVISIONAL,
        NET_UNKNOWN,
        OUTPUTS_PPO_DIR,
        REGEX_CA,
        REGEX_CUSPPO,
        REGEX_EOA,
        REGEX_EPO,
        REGEX_HMO,
        REGEX_POS,
        REGEX_PPO,
        REGEX_RETIREE,
        STATUS_CONFIRMED_PPO,
        STATUS_EXCLUDED_NON_PPO,
        STATUS_PROVISIONAL_PPO,
        STATUS_UNRESOLVED,
        TARGET_MARKET,
        TARGET_SNAPSHOT_DATE,
        TARGET_STATE,
    )
except ImportError:
    from ..config import (
        CONFIG_DIR,
        DELIVERABLES_DIR,
        EVIDENCE_REGISTER_PATHS,
        FILE_MIXED,
        FILE_PPO_ONLY,
        FILE_UNKNOWN,
        NET_CONFIRMED,
        NET_PROVISIONAL,
        NET_UNKNOWN,
        OUTPUTS_PPO_DIR,
        REGEX_CA,
        REGEX_CUSPPO,
        REGEX_EOA,
        REGEX_EPO,
        REGEX_HMO,
        REGEX_POS,
        REGEX_PPO,
        REGEX_RETIREE,
        STATUS_CONFIRMED_PPO,
        STATUS_EXCLUDED_NON_PPO,
        STATUS_PROVISIONAL_PPO,
        STATUS_UNRESOLVED,
        TARGET_MARKET,
        TARGET_SNAPSHOT_DATE,
        TARGET_STATE,
    )

logger = logging.getLogger(__name__)

RULE_VERSION = "2026.09-v2.0"

HMO_TRADEMARKS = [
    "canopycare", "salud", "smartcare", "communitycare hmo", "excelcare", "jade", "purecare hmo", "hmo breeze"
]
EPO_TRADEMARKS = [
    "purecare epo", "enhancedchoice epo", "ambetter balanced care", "ambetter secure care"
]
POS_TRADEMARKS = [
    "point of service", "tiered pos", "pos tiered", "hmo/pos"
]


def extract_state_from_url(url: str) -> Optional[str]:
    """Extracts explicit 2-letter state code from Centene URL naming convention."""
    if not url:
        return None
    url_lower = url.lower()
    m = re.search(r"[-_](?:healthnet|ambetter|centene|wellcare|fidelis|qualchoice)-([a-z]{2})[-_]", url_lower)
    if m:
        return m.group(1).upper()
    if "healthnet-ca" in url_lower or "ambetter-ca" in url_lower:
        return "CA"
    return None


class PPOVerificationEngine:
    """Verifies Centene California Commercial Group PPO plans and networks against authoritative evidence."""

    def __init__(self, evidence_csv_path: Optional[Path] = None):
        self.evidence_register: Dict[str, Dict] = {}
        self.exact_plan_eoc_map: Dict[str, Dict] = {}
        self.load_evidence_register(evidence_csv_path)

    def load_evidence_register(self, evidence_csv_path: Optional[Path] = None):
        """Loads versioned, human-auditable evidence register."""
        target_path = None
        if evidence_csv_path and Path(evidence_csv_path).is_file():
            target_path = Path(evidence_csv_path)
        else:
            for p in EVIDENCE_REGISTER_PATHS:
                if p.is_file():
                    target_path = p
                    break

        if not target_path or not target_path.is_file():
            logger.warning("No evidence register found at %s; using embedded defaults.", target_path)
            return

        try:
            df = pd.read_csv(target_path, dtype=str).fillna("")
            for _, r in df.iterrows():
                ev_id = r.get("evidence_id", "").strip()
                exact_name = r.get("exact_plan_name", "").strip().lower()
                rec = r.to_dict()
                if ev_id:
                    self.evidence_register[ev_id] = rec
                if exact_name:
                    self.exact_plan_eoc_map[exact_name] = rec
            logger.info("Loaded %d authoritative evidence entries from %s", len(self.evidence_register), target_path.name)
        except Exception as exc:
            logger.error("Failed to load evidence register: %s", exc)

    def evaluate_scope_gates(self, row: Dict) -> Tuple[bool, List[str], Dict]:
        """Step 2: Strict scope gates before network classification.
        Evaluates separately: payer=Centene, state=CA, market=group, commercial=true, snapshot_active=true.
        """
        brand = str(row.get("brand") or "").lower()
        plan_name = str(row.get("plan_name") or "")
        plan_name_lower = plan_name.lower()
        market_type = str(row.get("market_type") or "").strip().lower()
        url = str(row.get("rate_file_url") or "")
        last_updated = str(row.get("last_updated_on") or "")

        # Payer Check
        is_centene = any(b in brand for b in ["healthnet", "ambetter", "centene", "fidelis", "qualchoice"]) or "health net" in plan_name_lower

        # State Check
        url_state = extract_state_from_url(url)
        has_ca_in_name = bool(REGEX_CA.search(plan_name))
        is_ca = (url_state == "CA") or (has_ca_in_name and url_state is None) or ("health net life" in plan_name_lower)

        # Market Check
        is_group = "group" in market_type and not any(m in market_type for m in ["individual", "medicaid", "medicare"])

        # Commercial Check (Disallow Medicaid/Medicare/Exchange)
        is_non_commercial = any(k in plan_name_lower for k in ["medi-cal", "medicaid", "medicare", "wellcare", "exchange"])
        is_commercial = is_group and not is_non_commercial

        # Snapshot Active Check (September 2026)
        is_snapshot_active = True
        if last_updated and "2027" in last_updated:
            is_snapshot_active = False

        scope_flags = {
            "is_centene": is_centene,
            "is_california": is_ca,
            "is_group": is_group,
            "is_commercial": is_commercial,
            "is_snapshot_active": is_snapshot_active,
            "url_state": url_state
        }

        rejection_reasons = []
        if not is_centene: rejection_reasons.append("NON_CENTENE_PAYER")
        if not is_ca: rejection_reasons.append("NON_CALIFORNIA_GEOGRAPHY")
        if not is_group: rejection_reasons.append(f"OUT_OF_SCOPE_MARKET:{market_type}")
        if not is_commercial: rejection_reasons.append("GOVERNMENT_OR_INDIVIDUAL_PROGRAM")
        if not is_snapshot_active: rejection_reasons.append(f"OUT_OF_SNAPSHOT_PERIOD:{last_updated}")

        passes_all = len(rejection_reasons) == 0
        return passes_all, rejection_reasons, scope_flags

    def generate_candidate_bucket(self, plan_name: str) -> Tuple[str, List[str]]:
        """Step 3: Tokenizes plan name and places into preliminary candidate and review buckets."""
        name_lower = plan_name.lower()

        # Tokenization & Flags
        has_ppo = bool(REGEX_PPO.search(plan_name))
        has_cusppo = bool(REGEX_CUSPPO.search(plan_name))  # Collapsed token anomaly
        has_hmo = bool(REGEX_HMO.search(plan_name)) or any(t in name_lower for t in HMO_TRADEMARKS)
        has_epo = bool(REGEX_EPO.search(plan_name)) or any(t in name_lower for t in EPO_TRADEMARKS)
        has_pos = bool(REGEX_POS.search(plan_name)) or any(t in name_lower for t in POS_TRADEMARKS)
        has_eoa = bool(REGEX_EOA.search(plan_name))        # Exclusive Option Advantage
        has_retiree = bool(REGEX_RETIREE.search(plan_name))

        anomaly_tags = []
        if has_cusppo: anomaly_tags.append("COLLAPSED_TOKEN_CUSPPO")
        if has_retiree: anomaly_tags.append("RETIREE_OR_PUBLIC_WORD")
        if has_eoa: anomaly_tags.append("EOA_OVERLAP_SENSITIVITY")

        # Candidate Bucketing
        if (has_ppo or has_cusppo):
            if has_hmo or has_epo or has_pos:
                return "CONFLICT_REVIEW", anomaly_tags + ["PPO_MIXED_WITH_GATEKEEPER"]
            if has_retiree:
                return "RETIREE_REVIEW", anomaly_tags
            return "PPO_CANDIDATE", anomaly_tags

        if has_eoa:
            return "NON_PPO_CANDIDATE", anomaly_tags + ["EOA_HMO_WITH_PPO_TIER"]

        if has_hmo or has_epo or has_pos:
            return "NON_PPO_CANDIDATE", anomaly_tags

        return "UNLABELED_REVIEW", anomaly_tags

    def classify_and_verify_plan(self, row: Dict) -> Dict:
        """Step 4 & 5: Matches against evidence hierarchy and assigns formal Product & Network statuses."""
        plan_name = str(row.get("plan_name") or "").strip()
        plan_name_lower = plan_name.lower()
        plan_id = str(row.get("plan_id") or "").strip()
        url = str(row.get("rate_file_url") or "").strip()

        # Step 2: Scope Gates
        passes_scope, scope_rejections, scope_flags = self.evaluate_scope_gates(row)
        if not passes_scope:
            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": STATUS_EXCLUDED_NON_PPO,
                "network_status": NET_UNKNOWN,
                "network_name": "None",
                "service_area": "Out of Scope",
                "candidate_bucket": "OUT_OF_SCOPE",
                "decision_reason": f"Failed Scope Gates: {'; '.join(scope_rejections)}",
                "evidence_ids": "",
                "anomaly_tags": "",
                "rule_version": RULE_VERSION
            }

        # Step 3: Candidate Generation
        bucket, anomaly_tags = self.generate_candidate_bucket(plan_name)

        # Step 4 & 5: Apply Evidence Hierarchy
        # 1. Exact Match against Authoritative EOC/Evidence Register
        exact_eoc = self.exact_plan_eoc_map.get(plan_name_lower)
        if exact_eoc:
            prod_status = exact_eoc.get("decision", STATUS_CONFIRMED_PPO)
            net_status = NET_CONFIRMED if prod_status == STATUS_CONFIRMED_PPO else NET_UNKNOWN
            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": prod_status,
                "network_status": net_status,
                "network_name": exact_eoc.get("network_name", "Full Network PPO"),
                "service_area": "California Statewide",
                "candidate_bucket": bucket,
                "decision_reason": f"Exact match on authoritative {exact_eoc.get('document_type')}: {exact_eoc.get('conflict_note', '')}",
                "evidence_ids": exact_eoc.get("evidence_id", ""),
                "anomaly_tags": "; ".join(anomaly_tags),
                "rule_version": RULE_VERSION
            }

        # 2. Collapsed Token Anomaly (CA L CUSPPO)
        if "COLLAPSED_TOKEN_CUSPPO" in anomaly_tags:
            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": STATUS_PROVISIONAL_PPO,
                "network_status": NET_PROVISIONAL,
                "network_name": "Health Net Full Network PPO (Provisional)",
                "service_area": "California Statewide",
                "candidate_bucket": bucket,
                "decision_reason": "Collapsed token CUSPPO recognized as custom California commercial PPO product.",
                "evidence_ids": "EVID_ANOM_001",
                "anomaly_tags": "; ".join(anomaly_tags),
                "rule_version": RULE_VERSION
            }

        # 3. Retiree Review Queue
        if bucket == "RETIREE_REVIEW":
            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": STATUS_UNRESOLVED,
                "network_status": NET_UNKNOWN,
                "network_name": "Unknown",
                "service_area": "California",
                "candidate_bucket": bucket,
                "decision_reason": "Retiree product requires employer commercial-group active eligibility confirmation.",
                "evidence_ids": "EVID_ANOM_002",
                "anomaly_tags": "; ".join(anomaly_tags),
                "rule_version": RULE_VERSION
            }

        # 4. Conflict Review (PPO + EPO / HMO)
        if bucket == "CONFLICT_REVIEW":
            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": STATUS_UNRESOLVED,
                "network_status": NET_UNKNOWN,
                "network_name": "Unknown",
                "service_area": "California",
                "candidate_bucket": bucket,
                "decision_reason": "Conflicting network tokens in plan name (PPO alongside EPO/HMO/POS).",
                "evidence_ids": "",
                "anomaly_tags": "; ".join(anomaly_tags),
                "rule_version": RULE_VERSION
            }

        # 5. Non-PPO Candidate (Clear HMO / EPO / POS / EOA)
        if bucket == "NON_PPO_CANDIDATE":
            if "EOA_HMO_WITH_PPO_TIER" in anomaly_tags:
                reason = "Health Net Exclusive Option Advantage: HMO product with PPO tier; excluded from pure PPO set."
                ev_id = "EVID_EOA_001"
            elif any(t in plan_name_lower for t in HMO_TRADEMARKS) or bool(REGEX_HMO.search(plan_name)):
                reason = "Ruled out as Knox-Keene HMO: Delegated capitated IPA network model without PPO benefits."
                ev_id = "EVID_HMO_001"
            elif bool(REGEX_EPO.search(plan_name)):
                reason = "Ruled out as EPO: Closed exclusive provider network without out-of-network benefits."
                ev_id = "EVID_EPO_001"
            elif bool(REGEX_POS.search(plan_name)):
                reason = "Ruled out as POS: Two-tiered gatekeeper network requiring PCP referral."
                ev_id = "EVID_POS_001"
            else:
                reason = "Ruled out: Closed non-PPO network."
                ev_id = ""

            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": STATUS_EXCLUDED_NON_PPO,
                "network_status": NET_UNKNOWN,
                "network_name": "None",
                "service_area": "Out of Scope",
                "candidate_bucket": bucket,
                "decision_reason": reason,
                "evidence_ids": ev_id,
                "anomaly_tags": "; ".join(anomaly_tags),
                "rule_version": RULE_VERSION
            }

        # 6. Unlabeled Review Queue
        if bucket == "UNLABELED_REVIEW":
            return {
                "plan_name": plan_name,
                "plan_id": plan_id,
                "rate_file_url": url,
                "product_status": STATUS_UNRESOLVED,
                "network_status": NET_UNKNOWN,
                "network_name": "Unknown",
                "service_area": "California",
                "candidate_bucket": bucket,
                "decision_reason": "No network token stated in plan name; employer EOC document unobtained.",
                "evidence_ids": "",
                "anomaly_tags": "; ".join(anomaly_tags),
                "rule_version": RULE_VERSION
            }

        # 7. Confirmed / Provisional PPO (Explicit PPO in group CA commercial filing)
        # Check if metal-plan variant
        is_metal_ppo = any(m in plan_name_lower for m in ["platinum", "gold", "silver", "bronze"])
        if is_metal_ppo:
            # Check for the 1800 HDHP variants
            if "1800" in plan_name:
                p_status = STATUS_PROVISIONAL_PPO
                ev_id = "EVID_VAR_001"
                reason = "Metal HDHP 1800 variant: Provisional PPO pending official 1700 vs 1800 version check."
            else:
                p_status = STATUS_CONFIRMED_PPO
                ev_id = "EVID_EOC_001"
                reason = "Standard 2026 California Commercial Full Network PPO metal plan."
        else:
            # Custom employer PPO group plan
            p_status = STATUS_PROVISIONAL_PPO
            ev_id = "EVID_EOC_001"
            reason = "Commercial group PPO underwritten by Health Net Life; custom schedule corroborated by Full Network PPO filing."

        return {
            "plan_name": plan_name,
            "plan_id": plan_id,
            "rate_file_url": url,
            "product_status": p_status,
            "network_status": NET_CONFIRMED if p_status == STATUS_CONFIRMED_PPO else NET_PROVISIONAL,
            "network_name": "Health Net Full Network PPO",
            "service_area": "California Statewide",
            "candidate_bucket": bucket,
            "decision_reason": reason,
            "evidence_ids": ev_id,
            "anomaly_tags": "; ".join(anomaly_tags),
            "rule_version": RULE_VERSION
        }

    def verify_all_plans(self, plans_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
        """Runs verification across all plans and emits:
        1. plan_decisions_df
        2. file_manifest_df (with MIXED flag)
        3. review_queue_df
        4. summary_dict
        """
        logger.info("Verifying %d plans against PPO classification plan...", len(plans_df))
        decisions = []
        for _, row in plans_df.iterrows():
            d = self.classify_and_verify_plan(row.to_dict())
            decisions.append({**row.to_dict(), **d})

        dec_df = pd.DataFrame(decisions)

        # Step 6: Map plans to rate files without assigning false exclusivity
        file_summary = []
        for url, group in dec_df.groupby("rate_file_url"):
            if not url:
                continue
            conf_ppo_cnt = (group["product_status"] == STATUS_CONFIRMED_PPO).sum()
            prov_ppo_cnt = (group["product_status"] == STATUS_PROVISIONAL_PPO).sum()
            excluded_cnt = (group["product_status"] == STATUS_EXCLUDED_NON_PPO).sum()
            unresolved_cnt = (group["product_status"] == STATUS_UNRESOLVED).sum()
            total_plans = len(group)

            # Determine file classification
            has_ppo = (conf_ppo_cnt + prov_ppo_cnt) > 0
            has_non_ppo = excluded_cnt > 0
            if has_ppo and has_non_ppo:
                file_status = FILE_MIXED
            elif has_ppo and not has_non_ppo:
                file_status = FILE_PPO_ONLY
            else:
                file_status = FILE_UNKNOWN

            path_name = Path(unquote(urlsplit(url).path)).name
            file_summary.append({
                "rate_file_url": url,
                "rate_file_name": path_name,
                "file_classification": file_status,
                "plan_attribution_limitation": "SHARED_FILE_UNRESOLVED: Shared rate file contains both PPO and non-PPO contracts. Individual provider PPO network membership must be validated via plan-specific directory." if file_status == FILE_MIXED else "PPO_ATTRIBUTABLE",
                "total_linked_plans": total_plans,
                "confirmed_ppo_plans": int(conf_ppo_cnt),
                "provisional_ppo_plans": int(prov_ppo_cnt),
                "excluded_non_ppo_plans": int(excluded_cnt),
                "unresolved_plans": int(unresolved_cnt),
                "sample_ppo_plans": json.dumps(group[group["product_status"].isin([STATUS_CONFIRMED_PPO, STATUS_PROVISIONAL_PPO])]["plan_name"].head(5).tolist())
            })

        manifest_df = pd.DataFrame(file_summary)

        # Step 7: Review Queue
        review_queue = dec_df[dec_df["product_status"] == STATUS_UNRESOLVED].copy()
        if not review_queue.empty:
            review_queue = review_queue[["plan_name", "plan_id", "rate_file_url", "candidate_bucket", "anomaly_tags", "decision_reason"]]

        # Reconciled Summary
        summary = {
            "total_plans_audited": len(dec_df),
            "confirmed_ppo_count": int((dec_df["product_status"] == STATUS_CONFIRMED_PPO).sum()),
            "provisional_ppo_count": int((dec_df["product_status"] == STATUS_PROVISIONAL_PPO).sum()),
            "excluded_non_ppo_count": int((dec_df["product_status"] == STATUS_EXCLUDED_NON_PPO).sum()),
            "unresolved_count": int((dec_df["product_status"] == STATUS_UNRESOLVED).sum()),
            "unique_rate_files_count": len(manifest_df),
            "mixed_rate_files_count": int((manifest_df["file_classification"] == FILE_MIXED).sum()),
            "ppo_only_rate_files_count": int((manifest_df["file_classification"] == FILE_PPO_ONLY).sum()),
            "eoa_overlap_sensitivity_count": int(dec_df["anomaly_tags"].str.contains("EOA_OVERLAP_SENSITIVITY").sum()),
            "collapsed_token_count": int(dec_df["anomaly_tags"].str.contains("COLLAPSED_TOKEN_CUSPPO").sum()),
            "retiree_review_count": int(dec_df["anomaly_tags"].str.contains("RETIREE_OR_PUBLIC_WORD").sum()),
            "rule_version": RULE_VERSION
        }

        logger.info("Verification Complete: Confirmed PPO=%d, Provisional PPO=%d, Excluded=%d, Unresolved=%d",
                    summary["confirmed_ppo_count"], summary["provisional_ppo_count"],
                    summary["excluded_non_ppo_count"], summary["unresolved_count"])

        return dec_df, manifest_df, review_queue, summary


def main():
    ap = argparse.ArgumentParser(description="Deterministic Centene PPO Network Verifier")
    ap.add_argument("--plans", type=Path, required=True, help="Path to C1 deduplicated plan CSV")
    ap.add_argument("--evidence", type=Path, default=None, help="Path to ppo_evidence_sources.csv")
    ap.add_argument("--output", type=Path, default=OUTPUTS_PPO_DIR, help="Output directory for PPO decisions")
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    engine = PPOVerificationEngine(evidence_csv_path=args.evidence)

    plans_df = pd.read_csv(args.plans, dtype=str).fillna("")
    dec_df, manifest_df, review_queue, summary = engine.verify_all_plans(plans_df)

    dec_df.to_csv(args.output / "plan_decisions.csv", index=False)
    manifest_df.to_csv(args.output / "file_manifest.csv", index=False)
    review_queue.to_csv(args.output / "review_queue.csv", index=False)

    with open(args.output / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("PPO Verification Succeeded:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
