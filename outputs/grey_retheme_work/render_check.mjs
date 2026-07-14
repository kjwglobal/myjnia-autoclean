import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const outputDir = process.argv[3];

const defaultSheetNames = [
  "Dane",
  "Metoda analityczna",
  "Wartości przemieszczeń",
  "Wyr. wst. i met. analit.-graf.",
];
const sheetNames = process.argv.slice(4);
if (sheetNames.length === 0) {
  sheetNames.push(...defaultSheetNames);
}

await fs.mkdir(outputDir, { recursive: true });
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

for (const [index, sheetName] of sheetNames.entries()) {
  const blob = await workbook.render({ sheetName, scale: 1.4 });
  const bytes = Buffer.from(await blob.arrayBuffer());
  await fs.writeFile(`${outputDir}/sheet_${index + 1}.png`, bytes);
  console.log(`rendered ${sheetName}`);
}

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "formula error scan after color-only edit",
});
console.log(errors.ndjson);
