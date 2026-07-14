import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const referencePath = "/Users/kjw1/Desktop/Monitoring/Proj3/332044_id3_proj3.xlsx";
const targetPath = "/Users/kjw1/Desktop/Monitoring/332044_proj3_popr.xlsx";
const workDir = "/Users/kjw1/Documents/New project/outputs/style_transfer_work";

async function inspectWorkbook(filePath, label) {
  const blob = await FileBlob.load(filePath);
  const workbook = await SpreadsheetFile.importXlsx(blob);
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 10000,
    tableMaxRows: 5,
    tableMaxCols: 8,
    tableMaxCellChars: 80,
  });
  const formulas = await workbook.inspect({
    kind: "formula",
    maxChars: 20000,
    options: { maxResults: 1000 },
    summary: `${label} formula inventory`,
  });
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: `${label} formula error scan`,
  });

  return {
    label,
    summary: summary.ndjson,
    formulas: formulas.ndjson,
    errors: errors.ndjson,
  };
}

async function renderWorkbook(filePath, label) {
  const blob = await FileBlob.load(filePath);
  const workbook = await SpreadsheetFile.importXlsx(blob);
  const sheets = [
    ["Dane", "A1:N40"],
    [label === "reference" ? "Wstepnewyjsciowy" : "Wyrównanie wstępne - wyjściowy", "A1:W60"],
    [label === "reference" ? "Wstepneaktualny" : "Wyrównanie wstępne - aktualny", "A1:W60"],
    [label === "reference" ? "IdentyfikacjaBazy" : "Identyfikacja", "A1:AS60"],
    [label === "reference" ? "Baza_wyj" : "Baza - wyjściowy", "A1:W60"],
    [label === "reference" ? "Baza_akt" : "Baza - aktualny", "A1:W60"],
    [label === "reference" ? "Przemieszczenia" : "Przemieszczenia ostateczne", "A1:O60"],
  ];
  const dir = path.join(workDir, "previews", label);
  await fs.mkdir(dir, { recursive: true });
  for (const [sheetName, range] of sheets) {
    const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    const safe = sheetName.replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_|_$/g, "");
    await fs.writeFile(
      path.join(dir, `${safe}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}

async function main() {
  await fs.mkdir(workDir, { recursive: true });
  const [reference, target] = await Promise.all([
    inspectWorkbook(referencePath, "reference"),
    inspectWorkbook(targetPath, "target"),
  ]);
  await Promise.all([
    renderWorkbook(referencePath, "reference"),
    renderWorkbook(targetPath, "target"),
  ]);
  await fs.writeFile(
    path.join(workDir, "initial_inspection.json"),
    JSON.stringify({ reference, target }, null, 2),
  );
  console.log("Wrote initial_inspection.json");
  console.log("Reference summary:");
  console.log(reference.summary);
  console.log("Target summary:");
  console.log(target.summary);
  console.log("Target formula errors:");
  console.log(target.errors);
}

await main();
