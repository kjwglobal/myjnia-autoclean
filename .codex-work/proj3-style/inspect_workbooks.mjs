import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const referencePath = "/Users/kjw1/Desktop/Monitoring/Proj3/Reference.xlsx";
const sourcePath = "/Users/kjw1/Desktop/Monitoring/332044_proj3_popr.xlsx";
const outputDir = "/Users/kjw1/Documents/New project/outputs/proj3_style_20260612/inspection";

async function loadWorkbook(filePath) {
  const blob = await FileBlob.load(filePath);
  return SpreadsheetFile.importXlsx(blob);
}

async function logInspect(label, workbook, options) {
  const result = await workbook.inspect(options);
  console.log(`\n--- ${label} ---`);
  console.log(result.ndjson);
}

async function renderSheets(label, workbook, sheetNames) {
  const dir = path.join(outputDir, label);
  await fs.mkdir(dir, { recursive: true });
  for (const sheetName of sheetNames) {
    try {
      const preview = await workbook.render({
        sheetName,
        autoCrop: "all",
        scale: 1,
        format: "png",
      });
      const bytes = new Uint8Array(await preview.arrayBuffer());
      const safeName = sheetName.replace(/[^\p{L}\p{N}_-]+/gu, "_");
      await fs.writeFile(path.join(dir, `${safeName}.png`), bytes);
    } catch (error) {
      console.log(`Render failed for ${label}/${sheetName}: ${error.message}`);
    }
  }
}

const reference = await loadWorkbook(referencePath);
const source = await loadWorkbook(sourcePath);

await fs.mkdir(outputDir, { recursive: true });

await logInspect("REFERENCE workbook summary", reference, {
  kind: "workbook,sheet,region,table,drawing",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 8,
  tableMaxCellChars: 80,
});

await logInspect("SOURCE workbook summary", source, {
  kind: "workbook,sheet,region,table,drawing",
  maxChars: 16000,
  tableMaxRows: 8,
  tableMaxCols: 8,
  tableMaxCellChars: 80,
});

await logInspect("REFERENCE formulas", reference, {
  kind: "formula",
  maxChars: 8000,
  options: { maxResults: 150 },
});

await logInspect("SOURCE formulas", source, {
  kind: "formula",
  maxChars: 12000,
  options: { maxResults: 250 },
});

await logInspect("REFERENCE styles top areas", reference, {
  kind: "computedStyle",
  range: "A1:Z40",
  maxChars: 12000,
});

await logInspect("SOURCE formula errors", source, {
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "source formula error scan",
  maxChars: 12000,
});

const referenceSheets = JSON.parse(`[${(await reference.inspect({ kind: "sheet", include: "name", maxChars: 8000 })).ndjson.trim().split("\n").join(",")}]`).map((row) => row.name);
const sourceSheets = JSON.parse(`[${(await source.inspect({ kind: "sheet", include: "name", maxChars: 8000 })).ndjson.trim().split("\n").join(",")}]`).map((row) => row.name);

await renderSheets("reference", reference, referenceSheets);
await renderSheets("source", source, sourceSheets);

console.log(`\nPreviews written to ${outputDir}`);
