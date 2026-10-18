"""Evidence-backed C5 provider/site resolution.

The SQLite work table keeps C4 and NPPES scans bounded in memory. Public
registries propose or corroborate sites; only an exact, dated payer record can
confirm participation in the requested commercial PPO.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .address_normalizer import AddressNormalizer

LOG = logging.getLogger(__name__)

PAIRS = ("npi", "tin_type", "tin")
LOCATION_FIELDS = (
    "npi", "tin_type", "tin", "entity_type", "provider_name", "address",
    "address_key", "specialty", "practice_site_status", "tin_link_status",
    "ppo_participation_status", "c4_source_file_ids", "source_ids",
    "observed_as_of", "last_confirmed", "reason_codes",
)
EVIDENCE_FIELDS = (
    "npi", "source", "source_ref", "source_date", "retrieved_on", "address",
    "address_key", "raw_address", "provider_name", "entity_type", "plan_name",
    "plan_year", "tin_type", "tin", "specialty", "status", "reason",
)


def _value(row: dict[str, str], *names: str) -> str:
    return next((str(row.get(name) or "").strip() for name in names if str(row.get(name) or "").strip()), "")


def _date(text: str) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%m/%d/%Y").date()
        except ValueError:
            return None


def _fresh(text: str, as_of: date, days: int) -> bool:
    parsed = _date(text)
    return parsed is not None and 0 <= (as_of - parsed).days <= days


def _npi(value: str) -> bool:
    return len(value) == 10 and value.isdigit() and value != "0000000000"


def _tin(value: str, kind: str) -> str:
    value = value.replace("-", "").strip()
    return value if (kind == "ein" and len(value) == 9 and value.isdigit()) or (kind == "npi" and _npi(value)) else ""


def _csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _indexed_rows(path: Path, wanted: tuple[str, ...]) -> Iterable[dict[str, str]]:
    """Read only named columns into Python objects from very wide NPPES CSVs."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        indexes = {name: header.index(name) for name in wanted if name in header}
        for cells in reader:
            yield {name: cells[index] if index < len(cells) else "" for name, index in indexes.items()}


def _address(row: dict[str, str], names: tuple[str, str, str, str, str]) -> dict | None:
    line1, line2, city, state, zipcode = (str(row.get(name) or "").strip() for name in names)
    if not line1 or not city or state.upper() != "CA" or not re.fullmatch(r"\d{5}(?:-?\d{4})?", zipcode):
        return None
    normalized = AddressNormalizer.format_canonical_address(line1, line2, city, state, zipcode)
    if normalized["is_po_box"] or not normalized["is_valid_ca_zip"]:
        return None
    normalized["raw_address"] = ", ".join(filter(None, (line1, line2, city, state, zipcode)))
    # The building key is used only to flag possible suite conflicts.
    normalized["building_key"] = re.sub(r"\s+(?:STE|SUITE|FL|FLOOR|RM|ROOM|UNIT|APT)\s*\S+.*$", "", normalized["street"], flags=re.I) + "|" + normalized["city"].upper() + "|" + normalized["zip"]
    return normalized


NPPES_MAIN_ADDR = (
    "Provider First Line Business Practice Location Address",
    "Provider Second Line Business Practice Location Address",
    "Provider Business Practice Location Address City Name",
    "Provider Business Practice Location Address State Name",
    "Provider Business Practice Location Address Postal Code",
)
NPPES_SECONDARY_ADDR = (
    "Provider Secondary Practice Location Address- Address Line 1",
    "Provider Secondary Practice Location Address-  Address Line 2",
    "Provider Secondary Practice Location Address - City Name",
    "Provider Secondary Practice Location Address - State Name",
    "Provider Secondary Practice Location Address - Postal Code",
)
GENERIC_ADDR = ("address_line1", "address_line2", "city", "state", "zip")


class C5Resolver:
    def __init__(self, db_path: Path, *, as_of: date, ppo_plans: Iterable[str] = ()) -> None:
        self.db_path = db_path
        self.as_of = as_of
        self.ppo_plans = {x.strip().casefold() for x in ppo_plans if x.strip()}
        self.target_npis: set[str] = set()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS pairs (
                npi TEXT NOT NULL, tin_type TEXT NOT NULL, tin TEXT NOT NULL,
                source_file_id TEXT NOT NULL,
                PRIMARY KEY(npi,tin_type,tin,source_file_id)
            );
            CREATE INDEX IF NOT EXISTS pairs_npi ON pairs(npi);
            CREATE TABLE IF NOT EXISTS providers (
                npi TEXT PRIMARY KEY, entity_type TEXT, provider_name TEXT,
                taxonomy TEXT, specialty TEXT, record_updated_on TEXT,
                deactivated_on TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY, npi TEXT NOT NULL, source TEXT NOT NULL,
                source_ref TEXT NOT NULL, source_date TEXT, retrieved_on TEXT,
                address TEXT NOT NULL, address_key TEXT NOT NULL,
                building_key TEXT NOT NULL, raw_address TEXT,
                provider_name TEXT, entity_type TEXT, plan_name TEXT,
                plan_year TEXT, tin_type TEXT, tin TEXT, specialty TEXT,
                status TEXT, reason TEXT,
                UNIQUE(npi,source,source_ref,address_key,plan_name,tin_type,tin)
            );
            CREATE INDEX IF NOT EXISTS evidence_npi_address ON evidence(npi,address_key);
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def ingest_c4(self, selected_rates: Iterable[Path]) -> None:
        for path in selected_rates:
            count = 0
            with path.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                if not set(PAIRS).issubset(reader.fieldnames or ()):  # fail rather than invent keys
                    raise ValueError(f"C4 selected rates missing NPI/TIN columns: {path}")
                for row in reader:
                    npi, kind = row["npi"].strip(), row["tin_type"].strip().lower()
                    tin = _tin(row["tin"], kind)
                    if not _npi(npi) or not tin:
                        continue
                    source_id = row.get("source_file_id", "").strip() or path.parent.name
                    self.db.execute("INSERT OR IGNORE INTO pairs VALUES (?,?,?,?)", (npi, kind, tin, source_id))
                    self.target_npis.add(npi)
                    count += 1
                    if count % 100_000 == 0:
                        self.db.commit()
            self.db.commit()
        if not self.db.execute("SELECT 1 FROM pairs LIMIT 1").fetchone():
            raise ValueError("No valid C4 NPI/TIN pairs")

    def _wanted_npi(self, npi: str) -> bool:
        return npi in self.target_npis

    def ingest_nucc(self, path: Path | None) -> dict[str, str]:
        if not path:
            return {}
        return {row["Code"].strip(): (row.get("Display Name") or row.get("Classification") or "").strip()
                for row in _csv_rows(path) if row.get("Code")}

    def add_evidence(self, *, npi: str, source: str, source_ref: str, source_date: str,
                     address: dict | None, retrieved_on: str = "", provider_name: str = "",
                     entity_type: str = "", plan_name: str = "", plan_year: str = "",
                     tin_type: str = "", tin: str = "", specialty: str = "",
                     status: str = "", reason: str = "") -> None:
        if address is None or not self._wanted_npi(npi):
            return
        self.db.execute("""INSERT OR IGNORE INTO evidence
            (npi,source,source_ref,source_date,retrieved_on,address,address_key,building_key,
             raw_address,provider_name,entity_type,plan_name,plan_year,tin_type,tin,specialty,status,reason)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (npi, source, source_ref, source_date, retrieved_on or date.today().isoformat(),
             address["canonical_address"], address["address_hash"], address["building_key"],
             address["raw_address"], provider_name, entity_type, plan_name, plan_year,
             tin_type, tin, specialty, status, reason))

    def ingest_nppes(self, main: Path, secondary: Path, *, taxonomy: dict[str, str],
                     source_date: str, replace_updated: bool = False) -> set[str]:
        columns = ("NPI", "Entity Type Code", "Provider First Name", "Provider Last Name (Legal Name)",
                   "Provider Organization Name (Legal Business Name)", "Last Update Date",
                   "NPI Deactivation Date", "NPI Reactivation Date") + NPPES_MAIN_ADDR
        tax_cols = tuple(f"Healthcare Provider Taxonomy Code_{i}" for i in range(1, 16))
        switch_cols = tuple(f"Healthcare Provider Primary Taxonomy Switch_{i}" for i in range(1, 16))
        updated: set[str] = set()
        for row_number, row in enumerate(_indexed_rows(main, columns + tax_cols + switch_cols), 1):
            if row_number % 1_000_000 == 0:
                LOG.info("Scanned %s NPPES main rows from %s", f"{row_number:,}", main.name)
            npi = row.get("NPI", "").strip()
            if not self._wanted_npi(npi):
                continue
            if replace_updated:
                self.db.execute("DELETE FROM evidence WHERE npi=? AND source LIKE 'NPPES_%'", (npi,))
                updated.add(npi)
            entity = row.get("Entity Type Code", "")
            name = (row.get("Provider Organization Name (Legal Business Name)") or "") if entity == "2" else (
                (row.get("Provider First Name") or "") + " " + (row.get("Provider Last Name (Legal Name)") or ""))
            primary_code = next((row.get(f"Healthcare Provider Taxonomy Code_{i}", "") for i in range(1, 16)
                                 if row.get(f"Healthcare Provider Primary Taxonomy Switch_{i}", "").upper() == "Y"), "")
            primary_code = primary_code or next((row.get(c, "") for c in tax_cols if row.get(c)), "")
            deactivated = row.get("NPI Deactivation Date", "")
            reactivated = row.get("NPI Reactivation Date", "")
            if _date(reactivated) and _date(deactivated) and _date(reactivated) > _date(deactivated):
                deactivated = ""
            self.db.execute("""INSERT OR REPLACE INTO providers
                (npi,entity_type,provider_name,taxonomy,specialty,record_updated_on,deactivated_on)
                VALUES (?,?,?,?,?,?,?)""",
                (npi, entity, name.strip(), primary_code, taxonomy.get(primary_code, ""),
                 row.get("Last Update Date", ""), deactivated))
            address = _address(row, NPPES_MAIN_ADDR)
            self.add_evidence(npi=npi, source="NPPES_PRIMARY", source_ref=f"{main.name}:{npi}",
                              source_date=source_date, address=address, provider_name=name.strip(),
                              entity_type=entity, specialty=taxonomy.get(primary_code, ""),
                              reason="NPPES_RECORD_UPDATE_IS_NOT_ADDRESS_CONFIRMATION")
        self.db.commit()
        for row_number, row in enumerate(_indexed_rows(secondary, ("NPI",) + NPPES_SECONDARY_ADDR), 1):
            if row_number % 1_000_000 == 0:
                LOG.info("Scanned %s NPPES secondary rows from %s", f"{row_number:,}", secondary.name)
            npi = row.get("NPI", "").strip()
            if not self._wanted_npi(npi) or (replace_updated and npi not in updated):
                continue
            address = _address(row, NPPES_SECONDARY_ADDR)
            if address is None:
                continue
            ref = f"{secondary.name}:{npi}:{address['address_hash']}"
            self.add_evidence(npi=npi, source="NPPES_SECONDARY", source_ref=ref,
                              source_date=source_date, address=address,
                              reason="NPPES_NONPRIMARY_LOCATION")
        self.db.commit()
        return updated

    def ingest_deactivations(self, path: Path) -> None:
        if path.suffix.lower() == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(path, read_only=True, data_only=True)
            rows = workbook.active.values
            for row in rows:
                if row and _npi(str(row[0] or "")):
                    npi = str(row[0])
                    if self._wanted_npi(npi):
                        self.db.execute("UPDATE providers SET deactivated_on=? WHERE npi=?",
                                        (str(row[1] or ""), npi))
            workbook.close()
        else:
            for row in _csv_rows(path):
                npi = _value(row, "NPI", "npi")
                if self._wanted_npi(npi):
                    self.db.execute("UPDATE providers SET deactivated_on=? WHERE npi=?",
                                    (_value(row, "NPPES Deactivation Date", "deactivated_on"), npi))
        self.db.commit()

    def ingest_external(self, path: Path, source: str, *, default_source_date: str = "") -> None:
        if source not in {"CMS_CLINICIAN", "PAYER_DIRECTORY", "PROVIDER_ROSTER"}:
            raise ValueError(source)
        for row in _csv_rows(path):
            npi = _value(row, "npi", "NPI")
            if not self._wanted_npi(npi):
                continue
            fields = dict(row)
            if source == "CMS_CLINICIAN":
                fields["address_line1"] = _value(row, "adr_ln_1", "address_line1", "Address Line 1")
                fields["address_line2"] = _value(row, "adr_ln_2", "address_line2", "Address Line 2")
                fields["city"] = _value(row, "citytown", "cty", "city", "City")
                fields["state"] = _value(row, "state", "st", "State")
                fields["zip"] = _value(row, "zip_code", "zip", "ZIP")
            address = _address(fields, GENERIC_ADDR)
            if address is None:
                continue
            source_date = _value(row, "source_date", "as_of", "observed_at", "publication_date") or default_source_date
            plan_name = _value(row, "plan_name", "network_name") if source == "PAYER_DIRECTORY" else ""
            plan_year = _value(row, "plan_year") if source == "PAYER_DIRECTORY" else ""
            kind = _value(row, "tin_type").lower() if source != "CMS_CLINICIAN" else ""
            tin = _tin(_value(row, "tin"), kind)
            entity_type = _value(row, "entity_type") or ("1" if source == "CMS_CLINICIAN" else "")
            known = self.db.execute("SELECT entity_type FROM providers WHERE npi=?", (npi,)).fetchone()
            source_status = _value(row, "status")
            if known and entity_type in {"1", "2"} and known[0] in {"1", "2"} and entity_type != known[0]:
                source_status = "identity_conflict"
            record_url = _value(row, "record_url", "source_url")
            record_id = _value(row, "record_id")
            ref = f"{record_url}#{record_id}" if record_url and record_id else (
                record_url or record_id or _value(row, "source_ref"))
            if not ref:
                ref = f"{path.name}:{npi}:{address['address_hash']}"
            provider_name = _value(row, "provider_name", "name")
            if source == "CMS_CLINICIAN" and not provider_name:
                provider_name = " ".join(filter(None, (_value(row, "provider_first_name"),
                                                       _value(row, "provider_last_name"))))
            self.add_evidence(npi=npi, source=source, source_ref=ref, source_date=source_date,
                              address=address, provider_name=provider_name,
                              entity_type=entity_type, plan_name=plan_name,
                              plan_year=plan_year, tin_type=kind if tin else "", tin=tin,
                              specialty=_value(row, "specialty", "pri_spec"), status=source_status,
                              reason=_value(row, "reason"))
        self.db.commit()

    def _evidence_for(self, npi: str) -> list[dict]:
        self.db.row_factory = sqlite3.Row
        rows = [dict(r) for r in self.db.execute("SELECT * FROM evidence WHERE npi=? ORDER BY source,address_key,id", (npi,))]
        self.db.row_factory = None
        return rows

    def _decision(self, pair: tuple[str, str, str], items: list[dict], provider: tuple | None,
                  files: list[str], *, suite_conflict: bool = False) -> dict:
        npi, kind, tin = pair
        entity, name, specialty, deactivated = provider or ("", "", "", "")
        sources = {r["source"] for r in items}
        current_payer = [r for r in items if r["source"] == "PAYER_DIRECTORY" and
                         r["plan_name"].casefold() in self.ppo_plans and
                         r["plan_year"] == str(self.as_of.year) and
                         _fresh(r["source_date"], self.as_of, 180) and
                         r["status"].casefold() not in {"inactive", "closed", "terminated", "identity_conflict"}]
        current_provider = [r for r in items if r["source"] == "PROVIDER_ROSTER" and
                            _fresh(r["source_date"], self.as_of, 365) and
                            r["status"].casefold() not in {"inactive", "closed", "terminated", "identity_conflict"}]
        current_cms = "CMS_CLINICIAN" in sources and any(
            r["source"] == "CMS_CLINICIAN" and _fresh(r["source_date"], self.as_of, 548) for r in items)
        nppes = bool(sources & {"NPPES_PRIMARY", "NPPES_SECONDARY"})
        reasons = []
        if deactivated and _date(deactivated) and _date(deactivated) <= self.as_of:
            status = "unresolved"
            reasons.append("NPI_DEACTIVATED")
        elif any(r["status"].casefold() in {"inactive", "closed", "terminated", "identity_conflict"} for r in items):
            status = "conflicted"
            reasons.append("SOURCE_REPORTS_INACTIVE_SITE")
        elif suite_conflict and not current_payer and not current_provider and not (nppes and current_cms):
            status = "conflicted"
            reasons.append("SUITE_CONFLICT_REVIEW")
        elif current_payer or current_provider or (nppes and current_cms):
            status = "corroborated"
            reasons.append("DIRECT_OR_INDEPENDENT_SITE_EVIDENCE")
        else:
            status = "candidate"
            reasons.append("SINGLE_OR_STALE_SITE_SOURCE")
        exact_plan = bool(current_payer) and status == "corroborated"
        possible_plan = any(r["source"] == "PAYER_DIRECTORY" and
                            r["plan_name"].casefold() in self.ppo_plans for r in items)
        ppo = "confirmed" if exact_plan else "possible" if possible_plan and status != "unresolved" else "unknown"
        direct_tin = any(r["source"] in {"PAYER_DIRECTORY", "PROVIDER_ROSTER"} and
                         r["tin_type"] == kind and r["tin"] == tin and
                         _fresh(r["source_date"], self.as_of, 365) for r in items)
        tin_status = "proven" if direct_tin and status == "corroborated" else "unproven"
        if tin_status == "unproven":
            reasons.append("NO_DIRECT_TIN_SITE_LINK")
        if ppo != "confirmed":
            reasons.append("NO_EXACT_CURRENT_PPO_SITE_RECORD")
        if len(items) == 1 and items[0]["source"] == "NPPES_PRIMARY":
            reasons.append("NPPES_ONLY")
        confirmed_dates = [r["source_date"] for r in current_payer + current_provider if _date(r["source_date"])]
        return dict(zip(LOCATION_FIELDS, (
            npi, kind, tin, entity, name, items[0]["address"], items[0]["address_key"],
            specialty or next((r["specialty"] for r in items if r["specialty"]), ""),
            status, tin_status, ppo, ";".join(files),
            ";".join(str(r["id"]) for r in items), self.as_of.isoformat(),
            max(confirmed_dates, default=""), ";".join(reasons))))

    def write_outputs(self, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        location_path = output_dir / "c5_provider_locations.csv"
        evidence_path = output_dir / "c5_evidence.csv"
        review_path = output_dir / "c5_review_queue.csv"
        counts = defaultdict(int)
        npi_sets: dict[str, set[str]] = defaultdict(set)
        with evidence_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=("id",) + EVIDENCE_FIELDS)
            writer.writeheader()
            self.db.row_factory = sqlite3.Row
            for row in self.db.execute("SELECT * FROM evidence ORDER BY npi,id"):
                writer.writerow({field: row[field] for field in writer.fieldnames})
            self.db.row_factory = None
        with location_path.open("w", newline="", encoding="utf-8") as stream, review_path.open("w", newline="", encoding="utf-8") as review:
            writer = csv.DictWriter(stream, fieldnames=LOCATION_FIELDS)
            reviewer = csv.DictWriter(review, fieldnames=LOCATION_FIELDS)
            writer.writeheader()
            reviewer.writeheader()
            pairs = self.db.execute("SELECT DISTINCT npi,tin_type,tin FROM pairs ORDER BY npi,tin_type,tin")
            for pair in pairs:
                npi, kind, tin = pair
                counts["npi_tin_pairs"] += 1
                counts["type_1_pairs"] += bool((self.db.execute("SELECT entity_type FROM providers WHERE npi=?", (npi,)).fetchone() or ("",))[0] == "1")
                counts["type_2_pairs"] += bool((self.db.execute("SELECT entity_type FROM providers WHERE npi=?", (npi,)).fetchone() or ("",))[0] == "2")
                npi_sets["all"].add(npi)
                provider = self.db.execute("SELECT entity_type,provider_name,specialty,deactivated_on FROM providers WHERE npi=?", (npi,)).fetchone()
                files = [r[0] for r in self.db.execute("SELECT source_file_id FROM pairs WHERE npi=? AND tin_type=? AND tin=? ORDER BY source_file_id", pair)]
                evidence = self._evidence_for(npi)
                grouped: dict[str, list[dict]] = defaultdict(list)
                building_units: dict[str, set[str]] = defaultdict(set)
                for record in evidence:
                    grouped[record["address_key"]].append(record)
                    building_units[record["building_key"]].add(record["address_key"])
                if not grouped:
                    unresolved = {field: "" for field in LOCATION_FIELDS}
                    unresolved.update(npi=npi, tin_type=kind, tin=tin,
                                      entity_type=(provider or ("",))[0],
                                      provider_name=(provider or ("", ""))[1],
                                      specialty=(provider or ("", "", ""))[2],
                                      practice_site_status="unresolved", tin_link_status="unproven",
                                      ppo_participation_status="unknown", c4_source_file_ids=";".join(files),
                                      observed_as_of=self.as_of.isoformat(), reason_codes="NO_VALID_PHYSICAL_SITE")
                    reviewer.writerow(unresolved)
                    counts["unresolved_pairs"] += 1
                    continue
                for items in grouped.values():
                    decision = self._decision(pair, items, provider, files,
                                              suite_conflict=len(building_units[items[0]["building_key"]]) > 1)
                    writer.writerow(decision)
                    counts["location_rows"] += 1
                    site = decision["practice_site_status"]
                    ppo = decision["ppo_participation_status"]
                    npi_sets["physical_candidate"].add(npi)
                    if site == "corroborated":
                        npi_sets["corroborated"].add(npi)
                    if decision["tin_link_status"] == "proven":
                        npi_sets["tin_site_proven"].add(npi)
                    if ppo == "confirmed":
                        npi_sets["ppo_confirmed"].add(npi)
                    if site == "corroborated" and ppo == "confirmed" and decision["tin_link_status"] == "proven":
                        npi_sets["fully_verified"].add(npi)
                    if site != "corroborated" or ppo != "confirmed" or decision["tin_link_status"] != "proven":
                        reviewer.writerow(decision)
                    counts[f"{site}_locations"] += 1
        total = len(npi_sets["all"])
        summary = {
            "as_of": self.as_of.isoformat(), "unique_npis": total, **dict(counts),
            "unique_tins": self.db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT tin_type,tin FROM pairs)").fetchone()[0],
            "unique_physical_addresses": self.db.execute("SELECT COUNT(DISTINCT address_key) FROM evidence").fetchone()[0],
            "unique_npis_with_physical_candidate": len(npi_sets["physical_candidate"]),
            "unique_npis_with_corroborated_site": len(npi_sets["corroborated"]),
            "unique_npis_with_proven_tin_site": len(npi_sets["tin_site_proven"]),
            "unique_npis_with_confirmed_ppo_site": len(npi_sets["ppo_confirmed"]),
            "unique_npis_with_fully_verified_link": len(npi_sets["fully_verified"]),
            "share_npis_with_corroborated_site": round(100 * len(npi_sets["corroborated"]) / total, 2) if total else 0,
            "share_npis_with_confirmed_ppo_site": round(100 * len(npi_sets["ppo_confirmed"]) / total, 2) if total else 0,
            "share_npis_with_fully_verified_link": round(100 * len(npi_sets["fully_verified"]) / total, 2) if total else 0,
            "outputs": [p.name for p in (location_path, evidence_path, review_path)],
        }
        (output_dir / "c5_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary


def selected_paths(manifest: Path | None, explicit: list[Path]) -> list[Path]:
    paths = list(explicit)
    if manifest:
        for row in _csv_rows(manifest):
            raw = _value(row, "selected_rates_path")
            if not raw:
                raise ValueError(f"C4 manifest lacks selected_rates_path: {manifest}")
            paths.append((manifest.parent / raw).resolve())
    paths = list(dict.fromkeys(p.resolve() for p in paths))
    if not paths or any(not p.is_file() for p in paths):
        raise FileNotFoundError(f"Missing C4 selected-rates input: {paths}")
    return paths


def run_c5(*, selected_rates: list[Path], nppes_main: Path, nppes_secondary: Path,
           output_dir: Path, as_of: date, nucc: Path | None = None,
           cms: Path | None = None, payer_directory: Path | None = None,
           provider_roster: Path | None = None, deactivations: Path | None = None,
           cms_snapshot: date | None = None, payer_snapshot: date | None = None,
           roster_snapshot: date | None = None,
           weekly_main: Path | None = None, weekly_secondary: Path | None = None,
           monthly_through: date | None = None, weekly_through: date | None = None,
           ppo_plans: Iterable[str] = ()) -> dict:
    if not monthly_through:
        raise ValueError("Explicit monthly_through is required; NPPES record dates are not address confirmation dates")
    for path in (nppes_main, nppes_secondary, nucc, cms, payer_directory, provider_roster,
                 deactivations, weekly_main, weekly_secondary):
        if path is not None and not path.is_file():
            raise FileNotFoundError(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "c5_work.sqlite"
    if db_path.exists():
        db_path.unlink()  # derived, task-scoped scratch state only
    resolver = C5Resolver(db_path, as_of=as_of, ppo_plans=ppo_plans)
    try:
        if payer_directory and not resolver.ppo_plans:
            LOG.warning("Payer evidence supplied without --ppo-plan; PPO participation will remain unknown")
        resolver.ingest_c4(selected_rates)
        taxonomy = resolver.ingest_nucc(nucc)
        resolver.ingest_nppes(nppes_main, nppes_secondary, taxonomy=taxonomy,
                              source_date=monthly_through.isoformat())
        if weekly_main or weekly_secondary:
            if not weekly_main or not weekly_secondary or not monthly_through or not weekly_through:
                raise ValueError("Weekly NPPES requires both files and explicit monthly/weekly through dates")
            if weekly_through > monthly_through:
                resolver.ingest_nppes(weekly_main, weekly_secondary, taxonomy=taxonomy,
                                      source_date=weekly_through.isoformat(), replace_updated=True)
        if deactivations:
            resolver.ingest_deactivations(deactivations)
        for path, source, snapshot in ((cms, "CMS_CLINICIAN", cms_snapshot),
                                       (payer_directory, "PAYER_DIRECTORY", payer_snapshot),
                                       (provider_roster, "PROVIDER_ROSTER", roster_snapshot)):
            if path:
                resolver.ingest_external(path, source, default_source_date=snapshot.isoformat() if snapshot else "")
        summary = resolver.write_outputs(output_dir)
        input_paths = list(selected_rates) + [nppes_main, nppes_secondary] + [
            p for p in (weekly_main, weekly_secondary, deactivations, nucc, cms,
                        payer_directory, provider_roster) if p is not None]
        summary["inputs"] = [{"path": str(path.resolve()), "size_bytes": path.stat().st_size,
                              "modified_ns": path.stat().st_mtime_ns,
                              "sha256": _sha256(path) if path.stat().st_size < 200_000_000 else ""}
                             for path in input_paths]
        (output_dir / "c5_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        resolver.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Resolve C4 NPI/TIN pairs to sourced C5 practice sites")
    parser.add_argument("--c4-manifest", type=Path)
    parser.add_argument("--selected-rates", type=Path, action="append", default=[])
    parser.add_argument("--nppes-main", type=Path, required=True)
    parser.add_argument("--nppes-secondary", type=Path, required=True)
    parser.add_argument("--nppes-weekly-main", type=Path)
    parser.add_argument("--nppes-weekly-secondary", type=Path)
    parser.add_argument("--monthly-through", type=date.fromisoformat, required=True)
    parser.add_argument("--weekly-through", type=date.fromisoformat)
    parser.add_argument("--deactivations", type=Path)
    parser.add_argument("--nucc", type=Path)
    parser.add_argument("--cms", type=Path)
    parser.add_argument("--cms-snapshot", type=date.fromisoformat)
    parser.add_argument("--payer-directory", type=Path)
    parser.add_argument("--payer-snapshot", type=date.fromisoformat)
    parser.add_argument("--provider-roster", type=Path)
    parser.add_argument("--roster-snapshot", type=date.fromisoformat)
    parser.add_argument("--ppo-plan", action="append", default=[])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run_c5(selected_rates=selected_paths(args.c4_manifest, args.selected_rates),
                     nppes_main=args.nppes_main, nppes_secondary=args.nppes_secondary,
                     weekly_main=args.nppes_weekly_main, weekly_secondary=args.nppes_weekly_secondary,
                     monthly_through=args.monthly_through, weekly_through=args.weekly_through,
                     deactivations=args.deactivations, nucc=args.nucc, cms=args.cms,
                     payer_directory=args.payer_directory, provider_roster=args.provider_roster,
                     cms_snapshot=args.cms_snapshot, payer_snapshot=args.payer_snapshot,
                     roster_snapshot=args.roster_snapshot,
                     ppo_plans=args.ppo_plan, as_of=args.as_of, output_dir=args.output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
