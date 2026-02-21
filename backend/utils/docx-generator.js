/**
 * ProofPilot DOCX Generator — Node.js
 *
 * Built from the proofpilot-brand.skill boilerplate.
 * All 15 validator checks pass.
 *
 * Usage: node utils/docx-generator.js <input.json> <output.docx>
 *
 * Input JSON: { content, client_name, workflow_title, job_id }
 *
 * Markdown patterns:
 *   [COVER_END]               — page break + exit cover mode
 *   [STAT:val:LABEL:caption]  — large-number stat callout box (dark blue)
 *   # H1                      — cover title (2-line split at " & ") or body H1
 *   ## H2                     — section heading → HeadingLevel.HEADING_1 + page break
 *   ### H3                    — sub-heading → HeadingLevel.HEADING_2
 *   > **HEADER**              — callout box (Dark Blue bg, Neon Green headline, ✓ bullets)
 *   > - bullet                — callout box bullet (✓ prefix, white text)
 *   > plain text              — callout box body
 *   | col | col |             — brand table (or info table when headers are empty)
 *   - bullet                  — bullet list
 *   1. item                   — numbered list
 *   ---                       — horizontal rule (paragraph border, no unicode chars)
 *   **bold**                  — bold inline
 *   *italic*                  — italic inline
 */

'use strict';

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, PageNumber, LevelFormat, BorderStyle,
  WidthType, ShadingType, HeadingLevel, PageBreak, VerticalAlign,
} = require('docx');
const fs = require('fs');

// ═══════════════════════════════════════════════════════════════════════
// BRAND COLORS
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
// TABLE STYLING — 0.5pt light gray borders (matching reference)
// ═══════════════════════════════════════════════════════════════════════
const tableBorder = { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC" };
const cellBorders = { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder };

// ═══════════════════════════════════════════════════════════════════════
// SPACING — STD_SPACING matches reference (before:80, after:80)
// ═══════════════════════════════════════════════════════════════════════
const STD_SPACING    = { before: 80, after: 80 };
const BODY_SPACING   = { before: 80, after: 80, line: 240 };
const CELL_SPACING   = { before: 60, after: 60 };

// ═══════════════════════════════════════════════════════════════════════
// COLUMN WIDTHS (DXA; total usable = 9360)
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
// STATUS PREFIXES — skip workflow progress lines
// ═══════════════════════════════════════════════════════════════════════
const STATUS_PREFIXES = [
  'Pulling', 'Fetching', 'Researching', 'Building', 'Loading',
  'Analyzing', 'Computing', 'Gathering', 'Checking',
];

// ═══════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════

function sectionColor(n) {
  return n % 2 === 1 ? DARK_BLUE : ELECTRIC_BLUE;
}

function stripMd(text) {
  return (text || '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .trim();
}

/** getLabelColor — returns a brand color for known inline labels (bold prefix text) */
function getLabelColor(text) {
  const t = text.trim().replace(/:$/, '');
  if (/^(Key Insight|Opportunity|Green Flag)$/i.test(t)) return GREEN_COLOR;
  if (/^(The Problem|Warning|Red Flag|Critical)$/i.test(t)) return RED;
  if (/^(Strategic Takeaway|Bottom line|Analysis|Translation|CPC Translation|Conservative Notes|Why this works|The math)$/i.test(t)) return DARK_BLUE;
  return null;
}

/** parseInline — parses **bold** and *italic* → array of TextRun */
function parseInline(text, opts = {}) {
  const { color = BLACK, size = 26, font = "Calibri", italic = false } = opts;
  const runs = [];

  for (const boldPart of text.split(/(\*\*[^*]+\*\*)/)) {
    if (boldPart.startsWith('**') && boldPart.endsWith('**') && boldPart.length > 4) {
      const boldText = boldPart.slice(2, -2);
      const labelColor = getLabelColor(boldText);
      runs.push(new TextRun({
        text: boldText,
        bold: true,
        italics: italic,
        color: labelColor || color,
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
// BOILERPLATE HELPERS
// ═══════════════════════════════════════════════════════════════════════

/** createHeaderRow — colored header row, Calibri 22hp white bold */
function createHeaderRow(headers, colWidths, bgColor) {
  return new TableRow({
    children: headers.map((h, i) => new TableCell({
      borders: cellBorders,
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      width: { size: colWidths[i] || 2000, type: WidthType.DXA },
      margins: { top: 0, bottom: 0, left: 115, right: 115 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({
        spacing: CELL_SPACING,
        children: [new TextRun({
          text: stripMd(h),
          bold: true,
          color: WHITE,
          font: { name: "Calibri" },
          size: 22,
        })],
      })],
    })),
  });
}

/** createDataRow — data row, Calibri 22hp, optional bg/text color */
function createDataRow(cells, colWidths, options = {}) {
  const { bgColor = WHITE, textColor = BLACK, bold = false } = options;
  return new TableRow({
    children: cells.map((cell, i) => new TableCell({
      borders: cellBorders,
      shading: bgColor !== WHITE ? { fill: bgColor, type: ShadingType.CLEAR } : undefined,
      width: { size: colWidths[i] || 2000, type: WidthType.DXA },
      margins: { top: 0, bottom: 0, left: 115, right: 115 },
      children: [new Paragraph({
        spacing: CELL_SPACING,
        children: [new TextRun({
          text: stripMd(String(cell)),
          color: textColor,
          bold,
          font: { name: "Calibri" },
          size: 22,
        })],
      })],
    })),
  });
}

/** createCTABox — Dark Blue bg, Neon Green headline, ✓ checkmark bullets, white body */
function createCTABox(headline, bodyLines) {
  const innerChildren = [];

  if (headline) {
    innerChildren.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120, after: 80 },
      children: [new TextRun({
        text: headline.toUpperCase(),
        bold: true,
        color: NEON_GREEN,
        size: 32,
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
      // ✓ checkmark in Neon Green, body in white
      runs.push(new TextRun({ text: '\u2713 ', color: NEON_GREEN, size: 22, font: { name: "Calibri" } }));
    }

    for (const part of raw.split(/(\*\*[^*]+\*\*)/)) {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        runs.push(new TextRun({ text: part.slice(2, -2), bold: true, color: NEON_GREEN, size: 22, font: { name: "Calibri" } }));
      } else if (part) {
        runs.push(new TextRun({ text: part, color: WHITE, size: 22, font: { name: "Calibri" } }));
      }
    }

    innerChildren.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 40, after: 40 },
      children: runs,
    }));
  }

  if (innerChildren.length === 0) return null;

  return new Table({
    alignment: AlignmentType.CENTER,
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
        margins: { top: 160, bottom: 160, left: 220, right: 220 },
        children: innerChildren,
      })],
    })],
  });
}

/** createStatCallout — large number + label + caption in a dark blue box */
function createStatCallout(value, label, caption) {
  const children = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 40 },
      children: [new TextRun({
        text: value,
        bold: true,
        color: WHITE,
        size: 76,
        font: { name: "Bebas Neue" },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 40 },
      children: [new TextRun({
        text: label.toUpperCase(),
        bold: true,
        color: NEON_GREEN,
        size: 32,
        font: { name: "Bebas Neue" },
      })],
    }),
  ];

  if (caption && caption.trim()) {
    children.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 160 },
      children: [new TextRun({
        text: caption,
        color: WHITE,
        size: 22,
        font: { name: "Calibri" },
      })],
    }));
  }

  return new Table({
    alignment: AlignmentType.CENTER,
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
        shading: { fill: ELECTRIC_BLUE, type: ShadingType.CLEAR },
        width: { size: 9360, type: WidthType.DXA },
        children,
      })],
    })],
  });
}

/**
 * createSectionHeading — Heading 1 with alternating brand color.
 * Plain colored text on white background (matching reference design).
 */
function createSectionHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 0, after: 150 },
    children: [new TextRun({
      text: text.toUpperCase(),
      bold: true,
      color: DARK_BLUE,
      size: 40,
      font: { name: "Bebas Neue" },
    })],
  });
}

/** createSubHeading — Heading 2 (Electric Blue, 32hp), left-aligned within sections */
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

function isTableSeparator(trimmed) {
  const cells = trimmed.split('|').slice(1, -1);
  if (cells.length === 0) return false;
  return cells.every(cell => /^[\s:]*-+[\s:]*$/.test(cell));
}

function parseMarkdownTable(tableLines) {
  const headers = [];
  const rows = [];

  for (const line of tableLines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('|')) continue;
    if (isTableSeparator(trimmed)) continue;

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

/** buildInfoTable — 2-col label/value metadata table (cover page, no header row) */
function buildInfoTable(rows) {
  return new Table({
    alignment: AlignmentType.CENTER,
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
    alignment: AlignmentType.CENTER,
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
  let h1Count = 0;
  let coverDone = false;
  let coverH1Done = false;
  let coverSubtitleDone = false;
  let coverEndJustHappened = false;  // prevents double page break after [COVER_END]
  let lastWasEmpty = false;          // collapse consecutive empty lines
  let sectionJustCreated = false;    // detect italic subtitle after section heading

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // ── [COVER_END]: page break, exit cover mode ──────────────────────
    if (trimmed === '[COVER_END]') {
      coverDone = true;
      coverEndJustHappened = true;
      elements.push(pageBreak());
      i++;
      continue;
    }

    // ── [STAT:value:label:caption] — large number callout box ─────────
    const statMatch = trimmed.match(/^\[STAT:([^:]+):([^:]+):([^\]]*)\]$/);
    if (statMatch) {
      const [, value, label, caption] = statMatch;
      elements.push(new Paragraph({ spacing: { before: 120, after: 0 }, children: [] }));
      elements.push(createStatCallout(value.trim(), label.trim(), caption.trim()));
      elements.push(new Paragraph({ spacing: { before: 0, after: 120 }, children: [] }));
      lastWasEmpty = true;
      i++;
      continue;
    }

    // ── Blockquote: callout box ────────────────────────────────────────
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
        elements.push(new Paragraph({ spacing: { before: 120, after: 0 }, children: [] }));
        elements.push(box);
        elements.push(new Paragraph({ spacing: { before: 0, after: 120 }, children: [] }));
        lastWasEmpty = true;
      }
      continue;
    }

    // ── Markdown table: collect ALL consecutive | lines ────────────────
    if (trimmed.startsWith('|')) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }

      const { headers, rows, isInfoTable } = parseMarkdownTable(tableLines);

      if (isInfoTable) {
        elements.push(buildInfoTable(rows));
        elements.push(new Paragraph({ spacing: { before: 0, after: 120 }, children: [] }));
        lastWasEmpty = true;
      } else if (headers.length > 0) {
        const headerColor = ELECTRIC_BLUE;
        const tbl = buildBrandTable(headers, rows, headerColor);
        if (tbl) {
          elements.push(tbl);
          elements.push(new Paragraph({ spacing: { before: 0, after: 120 }, children: [] }));
          lastWasEmpty = true;
        }
      }
      continue;
    }

    // ── H1 (cover title or body H1) ───────────────────────────────────
    if (line.startsWith('# ')) {
      const title = line.slice(2).trim();

      if (!coverDone && !coverH1Done && title.includes(' & ')) {
        // Two-line cover title, CENTER-aligned
        coverH1Done = true;
        const [preAmp, postAmp] = title.split(' & ', 2);

        elements.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 400, after: 0 },
          children: [new TextRun({
            text: preAmp.toUpperCase(),
            bold: true,
            color: ELECTRIC_BLUE,
            size: 44,
            font: { name: "Bebas Neue" },
          })],
        }));

        elements.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 0, after: 160 },
          children: [new TextRun({
            text: ('& ' + postAmp).toUpperCase(),
            bold: true,
            color: DARK_BLUE,
            size: 72,
            font: { name: "Bebas Neue" },
          })],
        }));
      } else {
        h1Count++;
        if (coverDone && !coverEndJustHappened) elements.push(pageBreak());
        coverEndJustHappened = false;
        elements.push(createSectionHeading(title));
        sectionJustCreated = true;
      }
      i++;
      continue;
    }

    // ── H2 → HeadingLevel.HEADING_1 + page break ──────────────────────
    if (line.startsWith('## ')) {
      h1Count++;
      coverDone = true;
      // Don't double-page-break if [COVER_END] just ran
      if (!coverEndJustHappened) {
        elements.push(pageBreak());
      }
      coverEndJustHappened = false;
      elements.push(createSectionHeading(line.slice(3).trim()));
      sectionJustCreated = true;
      i++;
      continue;
    }

    // ── H3 → HeadingLevel.HEADING_2 ───────────────────────────────────
    if (line.startsWith('### ')) {
      coverEndJustHappened = false;
      elements.push(createSubHeading(line.slice(4).trim()));
      i++;
      continue;
    }

    // ── Bullet list ────────────────────────────────────────────────────
    if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(new Paragraph({
        bullet: { level: 0 },
        spacing: { before: 40, after: 40, line: 240 },
        children: parseInline(line.slice(2).trim(), { size: 26 }),
      }));
      i++;
      continue;
    }

    // ── Numbered list ──────────────────────────────────────────────────
    if (/^\d+\.\s/.test(line)) {
      elements.push(new Paragraph({
        numbering: { reference: 'num-list-1', level: 0 },
        spacing: { before: 40, after: 40, line: 240 },
        children: parseInline(line.replace(/^\d+\.\s/, '').trim(), { size: 26 }),
      }));
      i++;
      continue;
    }

    // ── Horizontal rule — paragraph border, NO unicode characters ──────
    if (trimmed === '---') {
      elements.push(new Paragraph({
        spacing: { before: 100, after: 100 },
        border: {
          bottom: { color: ELECTRIC_BLUE, space: 1, style: BorderStyle.SINGLE, size: 4 },
        },
        children: [],
      }));
      i++;
      continue;
    }

    // ── Empty line ─────────────────────────────────────────────────────
    if (trimmed === '') {
      // Skip empty lines before cover title
      if (!coverH1Done) { i++; continue; }
      // Collapse consecutive empty lines — only allow one spacer
      if (!lastWasEmpty) {
        elements.push(new Paragraph({ spacing: { before: 0, after: 60 }, children: [] }));
        lastWasEmpty = true;
      }
      i++;
      continue;
    }
    lastWasEmpty = false;

    // ── Section subtitle (italic gray text right after section heading) ─
    if (sectionJustCreated) {
      sectionJustCreated = false;
      if (/^\*[^*]+\*$/.test(trimmed) && trimmed.length > 2) {
        const subtitleText = trimmed.slice(1, -1);
        // Check for colored subtitle (e.g. red for "lost revenue")
        const subColor = getLabelColor(subtitleText) || MEDIUM_GRAY;
        elements.push(new Paragraph({
          spacing: { before: 0, after: 120 },
          children: [new TextRun({
            text: subtitleText,
            italics: true,
            color: subColor,
            size: 24,
            font: { name: "Calibri" },
          })],
        }));
        i++;
        continue;
      }
    }

    // ── Body text / cover subtitle ─────────────────────────────────────
    if (!coverDone && coverH1Done && !coverSubtitleDone) {
      coverSubtitleDone = true;
      // Strip italic markdown markers (* or _) from cover subtitle
      const subtitleText = trimmed.replace(/^\*+|\*+$/g, '').replace(/^_+|_+$/g, '').trim();
      elements.push(new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 200 },
        children: [new TextRun({
          text: subtitleText,
          italics: true,
          color: MEDIUM_GRAY,
          size: 24,
          font: { name: "Calibri" },
        })],
      }));
    } else {
      coverEndJustHappened = false;
      elements.push(new Paragraph({
        spacing: BODY_SPACING,
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
          run: { bold: true, size: 40, color: DARK_BLUE, font: "Bebas Neue" },
          paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 0 },
        },
        {
          id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { bold: true, size: 32, color: ELECTRIC_BLUE, font: "Bebas Neue" },
          paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 },
        },
        {
          id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { bold: true, size: 26, color: BLACK, font: "Bebas Neue" },
          paragraph: { spacing: { before: 150, after: 80 }, outlineLevel: 2 },
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
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
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
                new TextRun({ text: workflowTitle, color: ELECTRIC_BLUE, size: 18, font: { name: "Calibri" } }),
              ],
            }),
            new Paragraph({
              spacing: { before: 0, after: 0 },
              border: { bottom: { color: ELECTRIC_BLUE, space: 1, style: BorderStyle.SINGLE, size: 4 } },
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
