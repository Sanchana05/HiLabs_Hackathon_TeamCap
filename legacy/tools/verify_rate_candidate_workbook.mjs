// Read-only artifact-tool verification of the generated Excel deliverable.
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [workbookPath, previewDir] = process.argv.slice(2);
if (!workbookPath || !previewDir) throw new Error("Usage: node verify_rate_candidate_workbook.mjs XLSX PREVIEW_DIR");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
await fs.mkdir(previewDir, { recursive: true });
for (const [name, range, output] of [
  ["Rate candidates", "A1:F8", "rates.png"],
  ["Evidence", "A1:G8", "evidence.png"],
  ["Scope and sources", "A1:B13", "scope.png"],
]) {
  const result = await workbook.inspect({ kind: "table", range: `${name}!${range}`,
    include: "values,formulas", tableMaxRows: 13, tableMaxCols: 10 });
  console.log(result.ndjson);
  const preview = await workbook.render({ sheetName: name, range, scale: 1.5, format: "png" });
  await fs.writeFile(path.join(previewDir, output), new Uint8Array(await preview.arrayBuffer()));
}
