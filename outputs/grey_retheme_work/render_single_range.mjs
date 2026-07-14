import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, outputPath, sheetName, range] = process.argv.slice(2);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const blob = await workbook.render({ sheetName, range, scale: 1.4 });
await fs.writeFile(outputPath, Buffer.from(await blob.arrayBuffer()));
console.log(`rendered ${sheetName}!${range}`);
