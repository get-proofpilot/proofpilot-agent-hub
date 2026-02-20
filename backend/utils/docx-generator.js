/**
 * ProofPilot DOCX Generator — Node.js
 *
 * Built from the proofpilot-brand.skill boilerplate (v2, validated).
 * All 15 validator checks pass: heading styles, page breaks, brand colors,
 * no markdown artifacts, Bebas Neue font, Calibri body, US Letter page size.
 *
 * Usage: node utils/docx-generator.js <input.json> <output.docx>
 *
 * Input JSON: { content, client_name, workflow_title, job_id }
 *
 * Markdown patterns:
 *   [COVER_END]       — page break + exit cover mode
 *   # H1              — cover title (2-line split at " & ") or styled body H1
 *   ## H2             — section heading → HeadingLevel.HEADING_1 + auto page break
 *   ### H3            — sub-heading → HeadingLevel.HEADING_2
 *   > **HEADER**      — callout box (Dark Blue bg, Neon Green headline)
 *   > - bullet        — callout box bullet (Neon Green dot, white text)
 *   > plain text      — callout box body
 *   | col | col |     — brand table (or info table when headers are empty)
 *   - bullet          — bullet list
 *   1. item           — numbered list
 *   ---               — horizontal rule (paragraph border, no unicode chars)
 *   **bold**          — bold inline
 *   *italic*          — italic inline
 */

'use strict';

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, PageNumber, LevelFormat, BorderStyle,
  WidthType, ShadingType, HeadingLevel, PageBreak, VerticalAlign,
} = require('docx');
const fs = require('fs');

// ═══════════════════════════════════════════════════════════════════════
// BRAND COLORS — exact hex codes, no substitutions
// ═══════════════════════════════════════════════════════════════════════
const ELECTRIC_BLUE = "0051FF";
const DARK_BLUE     = "00184D";
const NEON_GREEN    = "C8FF00";
const BLACK         = "000000";
const LIGHT_GRAY    = "F4F4F4";
const MEDIUM_GRAY   = "666666";
const WHITE         = "FFFFFF";
const RED           = "DC3545";
const GREEN_COLOR   = "28A745";

// ═══════════════════════════════════════════════════════════════════════
// TABLE STYLING
// ═══════════════════════════════════════════════════════════════════════
const tableBorder = { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC" };
const cellBorders = { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder };

// ═══════════════════════════════════════════════════════════════════════
// COLUMN WIDTH PATTERNS (DXA; 1440 = 1 inch; total usable = 9360)
// ═══════════════════════════════════════════════════════════════════════
const COL_WIDTHS = {
  fiveColumnKeyword:    [2200, 1400, 1400, 1800, 2560],
  fourColumnRating:     [2600, 3200, 1000, 2560],
  fourColumnEqual:      [2340, 2340, 2340, 2340],
  threeColumnChecklist: [5000, 1200, 3160],
  twoColumnScore:       [6000, 3360],
  fullWidth:            [9360],
  infoTable:            [2500, 6860],
};

// ═══════════════════════════════════════════════════════════════════════
// STATUS PREFIXES — workflow progress lines, skip these in output
// ═══════════════════════════════════════════════════════════════════════
const STATUS_PREFIXES = [
  'Pulling', 'Fetching', 'Researching', 'Building', 'Loading',
  'Analyzing', 'Computing', 'Gathering', 'Checking',
];

// ═══════════════════════════════════════════════════════════════════════
// HELPER: sectionColor — alternates Dark/Electric Blue by section number
// ═══════════════════════════════════════════════════════════════════════
function sectionColor(n) {
  return n % 2 === 1 ? DARK_BLUE : ELECTRIC_BLUE;
}

// ═══════════════════════════════════════════════════════════════════════
// HELPER: stripMd — remove ** and * from plain text (for table cells)
// ═══════════════════════════════════════════════════════════════════════
function stripMd(text) {
  return (text || '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .trim();
}

// ═══════════════════════════════════════════════════════════════════════
// INLINE TEXT FORMATTING
// Parses **bold** and *italic* → array of TextRun
// ═══════════════════════════════════════════════════════════════════════
function parseInline(text, opts = {}) {
  const { color = BLACK, size = 26, font = "Calibri", italic = false } = opts;
  const runs = [];

  for (const boldPart of text.split(/(\*\*[^*]+\*\*)/)) {
    if (boldPart.startsWith('**') && boldPart.endsWith('**') && boldPart.length > 4) {
      runs.push(new TextRun({
        text: boldPart.slice(2, -2),
        bold: true,
        italics: italic,
        color,
        size,
        font: { name: font },
      }));
    } else {
      for (const italicPart of boldPart.split(/(\*[^*]+\*)/)) {
        if (italicPart.startsWith('*') && italicPart.endsWith('*') && italicPart.length > 2) {
          runs.push(new TextRun({
            text: italicPart.slice(1, -1),
            italics: true,
            color,
            size,
            font: { name: font },
          }));
        } else if (italicPart) {
          runs.push(new TextRun({
            text: italicPart,
            italics: italic,
            color,
            size,
            font: { name: font },
          }));
        }
      }
    }
  }

  return runs;
}

// ═══════════════════════════════════════════════════════════════════════
// BOILERPLATE HELPERS (from proofpilot-brand.skill)
// ═══════════════════════════════════════════════════════════════════════

/** createHeaderRow — styled table header row */
function createHeaderRow(headers, colWidths, bgColor) {
  return new TableRow({
    children: headers.map((h, i) => new TableCell({
      borders: cellBorders,
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      width: { size: colWidths[i] || 2000, type: WidthType.DXA },
      margins: { top: 0, bottom: 0, left: 115, right: 115 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({
        spacing: { before: 60, after: 60 },
        children: [new TextRun({
          text: stripMd(h),
          bold: true,
          color: WHITE,
          font: { name: "Calibri" },
          size: 26,
        })],
      })],
    })),
  });
}

/** createDataRow — data row with optional background / text color */
function createDataRow(cells, colWidths, options = {}) {
  const { bgColor = WHITE, textColor = BLACK, bold = false } = options;
  return new TableRow({
    children: cells.map((cell, i) => new TableCell({
      borders: cellBorders,
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      width: { size: colWidths[i] || 2000, type: WidthType.DXA },
      margins: { top: 0, bottom: 0, left: 115, right: 115 },
      children: [new Paragraph({
        spacing: { before: 60, after: 60 },
        children: [new TextRun({
          text: stripMd(String(cell)),
          color: textColor,
          bold,
          font: { name: "Calibri" },
          size: 26,
        })],
      })],
    })),
  });
}

/** createCTABox — Dark Blue callout box, Neon Green headline, white body */
function createCTABox(headline, bodyLines) {
  const innerChildren = [];

  if (headline) {
    innerChildren.push(new Paragraph({
      alignment: AlignmentType.LEFT,
      spacing: { before: 160, after: 80 },
      children: [new TextRun({
        text: headline,
        bold: true,
        color: NEON_GREEN,
        size: 28,
        font: { name: "Bebas Neue" },
      })],
    }));
  }

  for (const line of bodyLines) {
    if (!line.trim()) continue;
    const isBullet = line.startsWith('- ');
    const raw = isBullet ? line.slice(2) : line;

    const runs = [];
    if (isBullet) {
      runs.push(new TextRun({ text: '\u2022 ', color: NEON_GREEN, size: 20, font: { name: "Calibri" } }));
    }

    // **bold** inside callouts → Neon Green
    for (const part of raw.split(/(\*\*[^*]+\*\*)/)) {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        runs.push(new TextRun({ text: part.slice(2, -2), bold: true, color: NEON_GREEN, size: 20, font: { name: "Calibri" } }));
      } else if (part) {
        runs.push(new TextRun({ text: part, color: WHITE, size: 20, font: { name: "Calibri" } }));
      }
    }

    innerChildren.push(new Paragraph({
      spacing: { before: 40, after: 40 },
      indent: isBullet ? { left: 180 } : undefined,
      children: runs,
    }));
  }

  if (innerChildren.length === 0) return null;

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({
      children: [new TableCell({
        borders: cellBorders,
        shading: { fill: DARK_BLUE, type: ShadingType.CLEAR },
        width: { size: 9360, type: WidthType.DXA },
        margins: { top: 120, bottom: 120, left: 180, right: 180 },
        children: innerChildren,
      })],
    })],
  });
}

/** createSectionHeading — full-width banner with Dark Blue bg, Neon Green Bebas Neue heading */
function createSectionHeading(text, sectionNum) {
  // Use a full-width single-cell table as the section banner.
  // The paragraph inside uses HeadingLevel.HEADING_1 so the validator finds w:val="Heading1".
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({
      children: [new TableCell({
        borders: {
          top: { style: BorderStyle.NONE },
          bottom: { style: BorderStyle.NONE },
          left: { style: BorderStyle.NONE },
          right: { style: BorderStyle.NONE },
        },
        shading: { fill: DARK_BLUE, type: ShadingType.CLEAR },
        width: { size: 9360, type: WidthType.DXA },
        margins: { top: 120, bottom: 120, left: 200, right: 200 },
        children: [new Paragraph({
          heading: HeadingLevel.HEADING_1,
          spacing: { before: 0, after: 0 },
          children: [new TextRun({
            text: text.toUpperCase(),
            bold: true,
            color: NEON_GREEN,
            size: 32,
            font: { name: "Bebas Neue" },
          })],
        })],
      })],
    })],
  });
}

/** createSubHeading — Heading 2 (Electric Blue) */
function createSubHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 180, after: 80 },
    children: [new TextRun({
      text: text.toUpperCase(),
      bold: true,
      color: ELECTRIC_BLUE,
      size: 32,
      font: { name: "Bebas Neue" },
    })],
  });
}

/** pageBreak — insert before every major section */
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()], spacing: { before: 0, after: 0 } });
}

// ═══════════════════════════════════════════════════════════════════════
// MARKDOWN TABLE PARSER
// ═══════════════════════════════════════════════════════════════════════

/**
 * Detects if a table row is a separator (cells contain ONLY dashes/colons).
 * A separator must have at least one dash per cell. Empty cells are NOT separators.
 */
function isTableSeparator(trimmed) {
  const cells = trimmed.split('|').slice(1, -1);
  if (cells.length === 0) return false;
  return cells.every(cell => /^[\s:]*-+[\s:]*$/.test(cell));
}

/**
 * Parse markdown pipe table lines into { headers, rows, isInfoTable }.
 * isInfoTable = true when all header cells are empty (| | | pattern).
 */
function parseMarkdownTable(tableLines) {
  const headers = [];
  const rows = [];

  for (const line of tableLines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('|')) continue;
    if (isTableSeparator(trimmed)) continue;  // skip |---|---| rows

    const cells = trimmed
      .split('|')
      .slice(1, -1)
      .map(c => c.trim());

    if (headers.length === 0) {
      headers.push(...cells);
    } else {
      rows.push(cells);
    }
  }

  const isInfoTable = headers.length > 0 && headers.every(h => h === '');
  return { headers, rows, isInfoTable };
}

// ═══════════════════════════════════════════════════════════════════════
// TABLE BUILDERS
// ═══════════════════════════════════════════════════════════════════════

/** buildInfoTable — 2-col label/value table (metadata, no header row) */
function buildInfoTable(rows) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2500, 6860],
    rows: rows.map(row => new TableRow({
      children: [
        new TableCell({
          borders: cellBorders,
          shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
          width: { size: 2500, type: WidthType.DXA },
          margins: { top: 0, bottom: 0, left: 115, right: 115 },
          children: [new Paragraph({
            spacing: { before: 80, after: 80 },
            children: [new TextRun({
              text: stripMd(row[0] || ''),
              bold: true,
              size: 26,
              color: BLACK,
              font: { name: "Calibri" },
            })],
          })],
        }),
        new TableCell({
          borders: cellBorders,
          shading: { fill: WHITE, type: ShadingType.CLEAR },
          width: { size: 6860, type: WidthType.DXA },
          margins: { top: 0, bottom: 0, left: 115, right: 115 },
          children: [new Paragraph({
            spacing: { before: 80, after: 80 },
            children: [new TextRun({
              text: stripMd(row[1] || ''),
              size: 26,
              color: BLACK,
              font: { name: "Calibri" },
            })],
          })],
        }),
      ],
    })),
  });
}

/** buildBrandTable — standard data table with colored header row */
function buildBrandTable(headers, rows, headerColor) {
  if (!headers || headers.length === 0) return null;

  const totalWidth = 9360;
  const colWidth = Math.floor(totalWidth / headers.length);
  const colWidths = headers.map((_, i) =>
    i === headers.length - 1 ? totalWidth - colWidth * (headers.length - 1) : colWidth
  );

  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      createHeaderRow(headers, colWidths, headerColor),
      ...rows.map((row, idx) => {
        const paddedRow = [...row];
        while (paddedRow.length < headers.length) paddedRow.push('');
        return createDataRow(
          paddedRow,
          colWidths,
          { bgColor: idx % 2 === 1 ? LIGHT_GRAY : WHITE },
        );
      }),
    ],
  });
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN MARKDOWN RENDERER
// ═══════════════════════════════════════════════════════════════════════
function renderMarkdown(content) {
  const elements = [];
  const lines = content.split('\n');
  let i = 0;
  let h1Count = 0;   // counts ## headings → mapped to HeadingLevel.HEADING_1
  let coverDone = false;
  let coverH1Done = false;
  let coverSubtitleDone = false;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // ── [COVER_END]: page break, exit cover mode ─────────────────────
    if (trimmed === '[COVER_END]') {
      coverDone = true;
      elements.push(pageBreak());
      i++;
      continue;
    }

    // ── Blockquote: callout box or status skip ─────────────────────────
    if (trimmed.startsWith('> ')) {
      const rawContent = trimmed.slice(2).trim();
      if (STATUS_PREFIXES.some(pfx => rawContent.startsWith(pfx))) {
        i++;
        continue;
      }

      const calloutLines = [];
      while (i < lines.length && lines[i].trim().startsWith('> ')) {
        calloutLines.push(lines[i].trim().slice(2).trim());
        i++;
      }

      // First line is headline if **BOLD HEADER** pattern
      let headline = '';
      const bodyLines = [];
      if (calloutLines.length > 0 && /^\*\*[^*]+\*\*$/.test(calloutLines[0])) {
        headline = calloutLines[0].replace(/^\*\*([^*]+)\*\*$/, '$1');
        bodyLines.push(...calloutLines.slice(1));
      } else {
        bodyLines.push(...calloutLines);
      }

      const box = createCTABox(headline, bodyLines);
      if (box) {
        elements.push(new Paragraph({ spacing: { before: 100, after: 0 }, children: [] }));
        elements.push(box);
        elements.push(new Paragraph({ spacing: { before: 0, after: 120 }, children: [] }));
      }
      continue;
    }

    // ── Markdown table: collect ALL consecutive | lines ────────────────
    // Important: grab the whole block first, then parse it. This ensures
    // empty-header rows (| | |) and separator rows (|---|---|) don't leak
    // to body text.
    if (trimmed.startsWith('|')) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }

      const { headers, rows, isInfoTable } = parseMarkdownTable(tableLines);

      if (isInfoTable) {
        elements.push(buildInfoTable(rows));
        elements.push(new Paragraph({ spacing: { before: 0, after: 100 }, children: [] }));
      } else if (headers.length > 0) {
        const headerColor = sectionColor(h1Count);
        const tbl = buildBrandTable(headers, rows, headerColor);
        if (tbl) {
          elements.push(tbl);
          elements.push(new Paragraph({ spacing: { before: 0, after: 100 }, children: [] }));
        }
      }
      continue;
    }

    // ── H1 (cover title or body) ─────────────────────────────────────
    if (line.startsWith('# ')) {
      const title = line.slice(2).trim();

      if (!coverDone && !coverH1Done && title.includes(' & ')) {
        // Cover title: split at " & " into two styled lines
        coverH1Done = true;
        const [preAmp, postAmp] = title.split(' & ', 2);

        elements.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 560, after: 0 },
          children: [new TextRun({
            text: preAmp,
            bold: true,
            color: ELECTRIC_BLUE,
            size: 48,
            font: { name: "Bebas Neue" },
          })],
        }));

        elements.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 0, after: 160 },
          children: [new TextRun({
            text: '& ' + postAmp,
            bold: true,
            color: DARK_BLUE,
            size: 76,
            font: { name: "Bebas Neue" },
          })],
        }));
      } else {
        // Body H1 (rare — use Heading 1 style)
        h1Count++;
        if (coverDone) elements.push(pageBreak());
        elements.push(createSectionHeading(title, h1Count));
      }
      i++;
      continue;
    }

    // ── H2 → HeadingLevel.HEADING_1 + auto page break ─────────────────
    if (line.startsWith('## ')) {
      h1Count++;
      coverDone = true;
      // Insert page break before every section (except the very first when
      // [COVER_END] already added one)
      elements.push(pageBreak());
      elements.push(createSectionHeading(line.slice(3).trim(), h1Count));
      i++;
      continue;
    }

    // ── H3 → HeadingLevel.HEADING_2 ───────────────────────────────────
    if (line.startsWith('### ')) {
      elements.push(createSubHeading(line.slice(4).trim()));
      i++;
      continue;
    }

    // ── Bullet list ─────────────────────────────────────────────────────
    if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(new Paragraph({
        bullet: { level: 0 },
        spacing: { before: 40, after: 40 },
        children: parseInline(line.slice(2).trim(), { size: 26 }),
      }));
      i++;
      continue;
    }

    // ── Numbered list ───────────────────────────────────────────────────
    if (/^\d+\.\s/.test(line)) {
      elements.push(new Paragraph({
        numbering: { reference: 'num-list-1', level: 0 },
        spacing: { before: 40, after: 40 },
        children: parseInline(line.replace(/^\d+\.\s/, '').trim(), { size: 26 }),
      }));
      i++;
      continue;
    }

    // ── Horizontal rule — paragraph border, NO unicode characters ───────
    if (trimmed === '---') {
      elements.push(new Paragraph({
        spacing: { before: 120, after: 120 },
        border: {
          bottom: { color: ELECTRIC_BLUE, space: 1, style: BorderStyle.SINGLE, size: 6 },
        },
        children: [],
      }));
      i++;
      continue;
    }

    // ── Empty line ──────────────────────────────────────────────────────
    if (trimmed === '') {
      elements.push(new Paragraph({ spacing: { before: 0, after: 60 }, children: [] }));
      i++;
      continue;
    }

    // ── Body text / cover subtitle ──────────────────────────────────────
    if (!coverDone && coverH1Done && !coverSubtitleDone) {
      // First plain-text line after cover H1 → italic gray subtitle
      coverSubtitleDone = true;
      elements.push(new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 240 },
        children: [new TextRun({
          text: trimmed,
          italics: true,
          color: MEDIUM_GRAY,
          size: 28,
          font: { name: "Calibri" },
        })],
      }));
    } else {
      elements.push(new Paragraph({
        spacing: { before: 0, after: 150 },
        children: parseInline(trimmed, { size: 26 }),
      }));
    }
    i++;
  }

  return elements;
}

// ═══════════════════════════════════════════════════════════════════════
// DOCUMENT BUILDER
// ═══════════════════════════════════════════════════════════════════════
function buildDocument(content, clientName, workflowTitle) {
  const children = renderMarkdown(content);

  return new Document({
    styles: {
      default: { document: { run: { font: "Calibri", size: 26 } } },
      paragraphStyles: [
        {
          id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 40, bold: true, color: DARK_BLUE, font: "Bebas Neue" },
          paragraph: { spacing: { before: 350, after: 150 }, outlineLevel: 0 },
        },
        {
          id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 32, bold: true, color: ELECTRIC_BLUE, font: "Bebas Neue" },
          paragraph: { spacing: { before: 250, after: 120 }, outlineLevel: 1 },
        },
        {
          id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 26, bold: true, color: BLACK, font: "Bebas Neue" },
          paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 },
        },
      ],
    },
    numbering: {
      config: [
        {
          reference: "bullet-list",
          levels: [{
            level: 0,
            format: LevelFormat.BULLET,
            text: "\u2022",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          }],
        },
        {
          reference: "num-list-1",
          levels: [{
            level: 0,
            format: LevelFormat.DECIMAL,
            text: "%1.",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          }],
        },
      ],
    },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              spacing: { before: 0, after: 60 },
              children: [
                new TextRun({ text: "PROOFPILOT", bold: true, color: DARK_BLUE, size: 20, font: { name: "Calibri" } }),
                new TextRun({ text: "  |  ", color: ELECTRIC_BLUE, size: 18, font: { name: "Calibri" } }),
                new TextRun({ text: workflowTitle.toUpperCase(), color: ELECTRIC_BLUE, size: 18, font: { name: "Calibri" } }),
              ],
            }),
            new Paragraph({
              spacing: { before: 0, after: 0 },
              border: { bottom: { color: ELECTRIC_BLUE, space: 1, style: BorderStyle.SINGLE, size: 6 } },
              children: [],
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "ProofPilot  \u00b7  " + clientName + "  \u00b7  Page ", size: 16, color: MEDIUM_GRAY, font: { name: "Calibri" } }),
              new TextRun({ children: [PageNumber.CURRENT], size: 16, color: MEDIUM_GRAY, font: { name: "Calibri" } }),
              new TextRun({ text: " of ", size: 16, color: MEDIUM_GRAY, font: { name: "Calibri" } }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: MEDIUM_GRAY, font: { name: "Calibri" } }),
            ],
          })],
        }),
      },
      children,
    }],
  });
}

// ═══════════════════════════════════════════════════════════════════════
// ENTRY POINT
// ═══════════════════════════════════════════════════════════════════════
async function main() {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) {
    console.error('Usage: node docx-generator.js <input.json> <output.docx>');
    process.exit(1);
  }

  let jobData;
  try {
    jobData = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  } catch (err) {
    console.error('Failed to read input JSON:', err.message);
    process.exit(1);
  }

  const { content, client_name, workflow_title } = jobData;
  if (!content || !client_name || !workflow_title) {
    console.error('Input JSON must have: content, client_name, workflow_title');
    process.exit(1);
  }

  try {
    const doc    = buildDocument(content, client_name, workflow_title);
    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync(outputPath, buffer);
    console.log('OK:' + outputPath);
  } catch (err) {
    console.error('DOCX generation failed:', err.message, err.stack);
    process.exit(1);
  }
}

main();
