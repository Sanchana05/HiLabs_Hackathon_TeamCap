// Convert the C6 research-candidate CSV and evidence into a reviewable Excel file.
// Run with @oai/artifact-tool available in node_modules; see README.
import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const [sourceDir, outputPath] = process.argv.slice(2);
if (!sourceDir || !outputPath) {
  throw new Error("Usage: node build_rate_candidate_workbook.mjs C6_OUTPUT_DIR OUTPUT_XLSX");
}
const summary = JSON.parse(await fs.readFile(path.join(sourceDir, "c6_candidate_summary.json"), "utf8"));
const evidence = JSON.parse(await fs.readFile(path.join(sourceDir, "c6_candidate_evidence.json"), "utf8"));
const csv = await fs.readFile(path.join(sourceDir, "c6_supported_rate_candidates.csv"), "utf8");
let qualityText = "See file_quality_scorecard.csv";
try {
  const grades = JSON.parse(await fs.readFile(path.join(sourceDir, "..", "file_quality_details.json"), "utf8"));
  const grade = grades.find(r => r.source_url === evidence[0]?.["Rate Source URL"]);
  if (grade) qualityText = `${grade.grade}, ${grade.composite_fqs}/100; ${grade.quality_status}`;
} catch { /* C3 detail is optional for standalone candidate export. */ }
const workbook = await Workbook.fromCSV(csv, { sheetName: "Rate candidates" });
const rates = workbook.worksheets.getItem("Rate candidates");
rates.showGridLines = false;
rates.tabColor = "#17365D";
rates.freezePanes.freezeRows(1);
rates.getRange("A1:F1").format = {
  fill: "#17365D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  rowHeight: 27, verticalAlignment: "center",
};
rates.getRange("A:A").format.columnWidth = 16;
rates.getRange("B:B").format.columnWidth = 15;
rates.getRange("C:C").format.columnWidth = 54;
rates.getRange("D:D").format.columnWidth = 17;
rates.getRange("E:E").format.columnWidth = 49;
rates.getRange("F:F").format.columnWidth = 15;
if (evidence.length) {
  const rateValues = rates.getRange(`F2:F${evidence.length + 1}`).values;
  rates.getRange(`F2:F${evidence.length + 1}`).values = rateValues.map(([v]) => [Number(v)]);
  rates.getRange(`F2:F${evidence.length + 1}`).setNumberFormat('"$"#,##0.00');
  rates.getRange(`A2:B${evidence.length + 1}`).setNumberFormat("@");
}

const audit = workbook.worksheets.add("Evidence");
audit.showGridLines = false;
const auditHeaders = ["NPI", "TIN", "Address", "Billing Code", "Address status", "TIN/site",
  "PPO/site", "Address observations", "MRF URL", "Source locators"];
audit.getRange("A1:J1").values = [auditHeaders];
audit.getRange("A1:J1").format = {
  fill: "#355C7D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  rowHeight: 27, verticalAlignment: "center",
};
audit.freezePanes.freezeRows(1);
if (evidence.length) {
  const rows = evidence.map(r => [r.NPI, r.TIN, r.Address, r["Billing Code"],
    r["Address Status"], r["TIN/Site Status"], r["PPO/Site Status"],
    r["Address Evidence"], r["Rate Source URL"], r["Rate Source Locators"]]);
  audit.getRangeByIndexes(1, 0, rows.length, auditHeaders.length).values = rows;
  audit.getRange(`A2:B${rows.length + 1}`).setNumberFormat("@");
}
for (const [column, width] of Object.entries({ A: 16, B: 15, C: 54, D: 17, E: 18,
  F: 17, G: 17, H: 72, I: 65, J: 54 })) {
  audit.getRange(`${column}:${column}`).format.columnWidth = width;
}

const notes = workbook.worksheets.add("Scope and sources");
notes.showGridLines = false;
notes.tabColor = "#8A9BA8";
notes.getRange("A1").values = [["Centene California PPO rate candidates"]];
notes.getRange("A1").format.font = { name: "Arial", size: 14, bold: true, color: "#17365D" };
notes.getRange("A3:B13").values = [
  ["Status", "Research candidates; verify before contracting use"],
  ["Candidate rows", summary.counts.exported_candidate_rows || 0],
  ["Rate scope", "Direct professional FFS prices from a published MRF linked to confirmed Health Net CA group PPO plans."],
  ["Shared file", "Also linked to non-PPO plans. CMS permits common negotiated data in one file; PPO/site participation remains unconfirmed."],
  ["Address rule", "One California site independently corroborated by NPPES and CMS clinician data; alternate sites and multiple TINs were withheld."],
  ["TIN/site", "Inferred from the MRF NPI/TIN pair and a single corroborated NPI site; no direct TIN/site roster was supplied."],
  ["PPO/site", "No dated, exact-plan Health Net provider directory or contracted roster was supplied."],
  ["MRF", "https://www.centene.com/price-transparency-files.html"],
  ["CMS clinicians", "https://data.cms.gov/provider-data/dataset/mj5m-pzi6 (source modified 2026-10-02)"],
  ["NPPES", "https://download.cms.gov/nppes/NPI_Files.html (snapshot through 2026-10-11)"],
  ["File quality", qualityText],
];
notes.getRange("A3:A13").format.font = { name: "Arial", size: 10, bold: true, color: "#17365D" };
notes.getRange("A:A").format.columnWidth = 23;
notes.getRange("B:B").format.columnWidth = 115;
notes.getRange("B3:B13").format.font = { name: "Arial", size: 10, color: "#1F2937" };
notes.getRange("B4").setNumberFormat("#,##0");
notes.getRange("A3:B3").format.fill = "#FFF0C2";

workbook.recalculate();
const check = await workbook.inspect({ kind: "table", range: "Rate candidates!A1:F8",
  include: "values,formulas", tableMaxRows: 8, tableMaxCols: 6 });
console.log(check.ndjson);
const errorCheck = await workbook.inspect({ kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 20 }, summary: "final formula error scan" });
console.log(errorCheck.ndjson);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const blob = await SpreadsheetFile.exportXlsx(workbook);
await blob.save(outputPath);
console.log(JSON.stringify({ output: outputPath, rows: evidence.length }));
