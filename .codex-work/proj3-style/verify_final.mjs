import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "/Users/kjw1/Documents/New project/outputs/proj3_style_20260612/332044_proj3_popr_styl_reference_uzupelniony.xlsx";
const outputDir = "/Users/kjw1/Documents/New project/outputs/proj3_style_20260612/final_previews_uzupelniony";

const blob = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(blob);

async function logInspect(label, options) {
  const result = await workbook.inspect(options);
  console.log(`\n--- ${label} ---`);
  console.log(result.ndjson);
}

await fs.mkdir(outputDir, { recursive: true });

await logInspect("Sheets", {
  kind: "sheet",
  include: "name",
  maxChars: 5000,
});

await logInspect("Dane key range", {
  kind: "table",
  range: "Dane!A1:L37",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 12,
  maxChars: 12000,
});

await logInspect("Przemieszczenia key range", {
  kind: "table",
  range: "Przemieszczenia!A1:I53",
  include: "values,formulas",
  tableMaxRows: 60,
  tableMaxCols: 9,
  maxChars: 16000,
});

await logInspect("Formula error scan", {
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 12000,
});

const visibleSheets = [
  "Dane",
  "Wstepnewyjsciowy",
  "Wstepneaktualny",
  "IdentyfikacjaBazy",
  "Baza_wyj",
  "Baza_akt",
  "Przemieszczenia",
];

for (const sheetName of visibleSheets) {
  const safeName = sheetName.replace(/[^\p{L}\p{N}_-]+/gu, "_");
  try {
    const preview = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      path.join(outputDir, `${safeName}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  } catch (error) {
    console.log(`Render failed for ${sheetName}: ${error.message}`);
    const preview = await workbook.render({
      sheetName,
      range: "A1:Q60",
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      path.join(outputDir, `${safeName}_sample.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}

console.log(`\nPreviews written to ${outputDir}`);
