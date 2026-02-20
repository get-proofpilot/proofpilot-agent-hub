#!/usr/bin/env node
// ╔═══════════════════════════════════════════════════════════════════════════════╗
// ║  PROOFPILOT DOCUMENT VALIDATOR                                              ║
// ║                                                                              ║
// ║  Usage: node validate-proofpilot.js <path-to-docx>                          ║
// ║                                                                              ║
// ║  Checks a generated .docx file against all ProofPilot brand requirements.   ║
// ║  Returns exit code 0 if all checks pass, 1 if any fail.                     ║
// ╚═══════════════════════════════════════════════════════════════════════════════╝

const fs = require('fs');
const JSZip = require('jszip');

const DOCX_PATH = process.argv[2];

if (!DOCX_PATH) {
  console.error("Usage: node validate-proofpilot.js <path-to-docx>");
  process.exit(1);
}

if (!fs.existsSync(DOCX_PATH)) {
  console.error("File not found: " + DOCX_PATH);
  process.exit(1);
}

// Brand color hex codes (lowercase for matching)
const BRAND_COLORS = {
  ELECTRIC_BLUE: "0051ff",
  DARK_BLUE: "00184d",
  NEON_GREEN: "c8ff00",
  MEDIUM_GRAY: "666666",
  RED: "dc3545",
  GREEN: "28a745"
};

async function validate() {
  const buffer = fs.readFileSync(DOCX_PATH);
  const zip = await JSZip.loadAsync(buffer);

  // Read the main document XML
  const docXml = await zip.file("word/document.xml").async("string");
  const xml = docXml.toLowerCase();

  // Read styles XML if present
  let stylesXml = "";
  const stylesFile = zip.file("word/styles.xml");
  if (stylesFile) {
    stylesXml = (await stylesFile.async("string")).toLowerCase();
  }

  // Read header XMLs
  let headerXml = "";
  for (const filename of Object.keys(zip.files)) {
    if (filename.match(/word\/header\d+\.xml/)) {
      headerXml += (await zip.file(filename).async("string")).toLowerCase();
    }
  }

  // Read footer XMLs
  let footerXml = "";
  for (const filename of Object.keys(zip.files)) {
    if (filename.match(/word\/footer\d+\.xml/)) {
      footerXml += (await zip.file(filename).async("string")).toLowerCase();
    }
  }

  const results = [];
  let passCount = 0;
  let failCount = 0;

  function check(name, passed, detail) {
    if (passed) {
      passCount++;
      results.push({ status: "PASS", name, detail });
    } else {
      failCount++;
      results.push({ status: "FAIL", name, detail });
    }
  }

  // ─── CHECK 1: Page size is US Letter ───
  // US Letter = 12240 x 15840 twips
  const pgSzMatch = docXml.match(/<w:pgSz[^>]*>/i);
  if (pgSzMatch) {
    const pgSz = pgSzMatch[0];
    const wMatch = pgSz.match(/w:w="(\d+)"/i);
    const hMatch = pgSz.match(/w:h="(\d+)"/i);
    const width = wMatch ? parseInt(wMatch[1]) : 0;
    const height = hMatch ? parseInt(hMatch[1]) : 0;
    check("Page size is US Letter", width === 12240 && height === 15840,
      "Found: " + width + " x " + height + " (expected 12240 x 15840)");
  } else {
    check("Page size is US Letter", false, "No page size definition found");
  }

  // ─── CHECK 2: Heading 1 style is used ───
  // Look for w:pStyle w:val="Heading1" in document
  const heading1Count = (docXml.match(/w:val="Heading1"/gi) || []).length;
  check("Heading 1 style used", heading1Count >= 3,
    "Found " + heading1Count + " Heading 1 paragraphs (minimum 3 expected)");

  // ─── CHECK 3: Heading 2 style is used ───
  const heading2Count = (docXml.match(/w:val="Heading2"/gi) || []).length;
  check("Heading 2 style used", heading2Count >= 1,
    "Found " + heading2Count + " Heading 2 paragraphs");

  // ─── CHECK 4: Page breaks exist ───
  const pageBreakCount = (docXml.match(/<w:br w:type="page"\/>/gi) || []).length;
  check("Page breaks present (5+ expected)", pageBreakCount >= 5,
    "Found " + pageBreakCount + " page breaks");

  // ─── CHECK 5: Bebas Neue font referenced ───
  const bebasCount = (docXml.match(/bebas neue/gi) || []).length;
  const bebasInStyles = (stylesXml.match(/bebas neue/gi) || []).length;
  const totalBebas = bebasCount + bebasInStyles;
  check("Bebas Neue font used", totalBebas >= 3,
    "Found " + bebasCount + " in document + " + bebasInStyles + " in styles");

  // ─── CHECK 6: Calibri font referenced ───
  const calibriInDoc = (docXml.match(/calibri/gi) || []).length;
  const calibriInStyles = (stylesXml.match(/calibri/gi) || []).length;
  check("Calibri font used", (calibriInDoc + calibriInStyles) >= 1,
    "Found " + calibriInDoc + " in document + " + calibriInStyles + " in styles");

  // ─── CHECK 7: Dark Blue color present ───
  const darkBlueCount = (xml.match(/00184d/g) || []).length;
  check("Dark Blue (#00184D) used", darkBlueCount >= 3,
    "Found " + darkBlueCount + " references");

  // ─── CHECK 8: Electric Blue color present ───
  const electricBlueCount = (xml.match(/0051ff/g) || []).length;
  check("Electric Blue (#0051FF) used", electricBlueCount >= 2,
    "Found " + electricBlueCount + " references");

  // ─── CHECK 9: Neon Green color present ───
  const neonGreenCount = (xml.match(/c8ff00/g) || []).length;
  check("Neon Green (#C8FF00) used", neonGreenCount >= 1,
    "Found " + neonGreenCount + " references");

  // ─── CHECK 10: Table cell shading uses CLEAR not SOLID ───
  const solidShadingCount = (docXml.match(/w:val="solid"/gi) || []).length;
  const clearShadingCount = (docXml.match(/w:val="clear"/gi) || []).length;
  check("ShadingType.CLEAR used (not SOLID)", solidShadingCount === 0,
    "Found " + solidShadingCount + " SOLID shading (should be 0), " + clearShadingCount + " CLEAR");

  // ─── CHECK 11: Header contains PROOFPILOT ───
  const headerHasProofpilot = headerXml.includes("proofpilot");
  check("Header contains PROOFPILOT", headerHasProofpilot,
    headerHasProofpilot ? "Found in header" : "Missing from header");

  // ─── CHECK 12: Footer contains page numbers ───
  const footerHasPageNum = footerXml.includes("w:fldchar") || footerXml.includes("page");
  check("Footer contains page numbers", footerHasPageNum,
    footerHasPageNum ? "Found page number references" : "Missing page numbers");

  // ─── CHECK 13: No markdown artifacts ───
  // Look for literal markdown table syntax or heading syntax in text runs
  const textContent = docXml.replace(/<[^>]+>/g, " ");
  const markdownPipes = (textContent.match(/\|[\s]*\|/g) || []).length;
  const markdownDashes = (textContent.match(/---+/g) || []).length;
  const markdownHashes = (textContent.match(/##+ /g) || []).length;
  const totalMarkdown = markdownPipes + markdownDashes + markdownHashes;
  check("No markdown artifacts in output", totalMarkdown === 0,
    "Found " + markdownPipes + " pipe patterns, " + markdownDashes + " dash patterns, " + markdownHashes + " hash patterns");

  // ─── CHECK 14: No unicode dividers ───
  const unicodeDividers = (docXml.match(/[━═─╔╗╚╝║╠╣╬]/g) || []).length;
  check("No unicode divider characters", unicodeDividers === 0,
    "Found " + unicodeDividers + " unicode divider characters");

  // ─── CHECK 15: Tables have cell widths set ───
  const tableCount = (docXml.match(/<w:tbl>/gi) || []).length;
  const cellWidthCount = (docXml.match(/<w:tcW /gi) || []).length;
  check("Table cells have widths defined", tableCount === 0 || cellWidthCount > 0,
    "Found " + tableCount + " tables, " + cellWidthCount + " cell width definitions");

  // ─── OUTPUT RESULTS ───
  console.log("\n╔═══════════════════════════════════════════════════════╗");
  console.log("║  PROOFPILOT DOCUMENT VALIDATION RESULTS             ║");
  console.log("╚═══════════════════════════════════════════════════════╝\n");
  console.log("File: " + DOCX_PATH + "\n");

  for (const r of results) {
    const icon = r.status === "PASS" ? "✓" : "✗";
    const label = r.status === "PASS" ? "PASS" : "FAIL";
    console.log(icon + " [" + label + "] " + r.name);
    console.log("         " + r.detail);
  }

  console.log("\n─────────────────────────────────────────────────────────");
  console.log("Results: " + passCount + " passed, " + failCount + " failed out of " + results.length + " checks");
  console.log("─────────────────────────────────────────────────────────\n");

  if (failCount > 0) {
    console.log("ACTION REQUIRED: Fix all FAIL items and re-run validation.");
    process.exit(1);
  } else {
    console.log("All checks passed. Document is ready for delivery.");
    process.exit(0);
  }
}

validate().catch(err => {
  console.error("Validation error:", err.message);
  process.exit(1);
});
