/**
 * A Word document written in the browser: a few OOXML parts in a stored zip.
 *
 * Everything here runs on model output and text people typed, so nothing is
 * trusted as markup. Text is only ever placed in `<w:t>`, escaped, with the
 * characters XML cannot carry removed, because one stray control character makes
 * Word refuse the whole file.
 */

export type DocxBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string; indent?: number; bold?: boolean }
  | { kind: "bullet"; text: string }
  | { kind: "number"; n: number; text: string }
  | { kind: "table"; header: string[]; rows: string[][] };

export const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

// ---- text to blocks ----

const ALL_CAPS_LINE = /^[^a-z]*[A-Z]{2}[^a-z]*$/;

/** The plain text the drafting services render: capitals head a part, numbers and dashes list. */
export function textToBlocks(text: string): DocxBlock[] {
  const blocks: DocxBlock[] = [];
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trim();
    if (!line || /^-{3,}$/.test(line)) continue;
    const marked = line.match(/^(#{1,3})\s+(.+)$/);
    const bullet = line.match(/^[-*•]\s+(.+)$/);
    const numbered = line.match(/^(\d{1,3})[.)]\s+(.+)$/);
    if (marked) blocks.push({ kind: "heading", level: marked[1].length as 1 | 2 | 3, text: marked[2] });
    else if (bullet) blocks.push({ kind: "bullet", text: bullet[1] });
    else if (numbered) blocks.push({ kind: "number", n: Number(numbered[1]), text: numbered[2] });
    else if (line.length <= 120 && ALL_CAPS_LINE.test(line)) blocks.push({ kind: "heading", level: 2, text: line });
    else {
      const indent = raw.length - raw.trimStart().length;
      blocks.push(indent ? { kind: "paragraph", text: line, indent: Math.min(3, Math.ceil(indent / 2)) } : { kind: "paragraph", text: line });
    }
  }
  return blocks;
}

function decodeEntities(text: string): string {
  const named: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (whole, body: string) => {
    if (body[0] !== "#") return named[body] ?? whole;
    const code = body[1] === "x" || body[1] === "X" ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
    return Number.isFinite(code) && code <= 0x10ffff ? String.fromCodePoint(code) : "";
  });
}

/**
 * The case file comes from the server as escaped HTML of a known, plain shape.
 * Read as a stream of tags rather than a DOM, so the text stays inert and the
 * reader runs the same in a test as in the browser.
 */
export function htmlToBlocks(html: string): DocxBlock[] {
  const body = html
    .replace(/<!doctype[^>]*>|<!--[\s\S]*?-->/gi, "")
    .replace(/<head[\s\S]*?<\/head>/gi, "")
    .replace(/<(style|script|title)[\s\S]*?<\/\1>/gi, "");
  const blocks: DocxBlock[] = [];
  let open = "";
  let buffer = "";
  let term = "";
  let table: { header: string[]; rows: string[][] } | null = null;
  let row: string[] = [];
  let rowIsHeader = false;
  const orderedDepth: number[] = [];
  const clean = () => decodeEntities(buffer).replace(/\s+/g, " ").trim();
  const flush = () => {
    const text = clean();
    if (open === "pre") blocks.push(...textToBlocks(decodeEntities(buffer)));
    else if (text) {
      if (/^h[1-3]$/.test(open)) blocks.push({ kind: "heading", level: Number(open[1]) as 1 | 2 | 3, text });
      else if (open === "li") {
        if (orderedDepth.length) { orderedDepth[orderedDepth.length - 1] += 1; blocks.push({ kind: "number", n: orderedDepth[orderedDepth.length - 1], text }); }
        else blocks.push({ kind: "bullet", text });
      } else blocks.push({ kind: "paragraph", text });
    }
    buffer = "";
    open = "";
  };
  for (const token of body.matchAll(/<(\/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*>|[^<]+|</g)) {
    const closing = token[1] === "/";
    const tag = token[2]?.toLowerCase();
    if (!tag) { buffer += token[0]; continue; }
    if (tag === "br") { buffer += " "; continue; }
    if (tag === "table") {
      flush();
      if (closing && table) { blocks.push({ kind: "table", ...table }); table = null; }
      else if (!closing) table = { header: [], rows: [] };
    } else if (table && (tag === "tr")) {
      if (closing) { if (rowIsHeader) table.header = row; else table.rows.push(row); }
      row = [];
      rowIsHeader = false;
    } else if (table && (tag === "td" || tag === "th")) {
      if (closing) { row.push(clean()); buffer = ""; }
      else { buffer = ""; if (tag === "th") rowIsHeader = true; }
    } else if (tag === "dt") {
      if (closing) { term = clean(); buffer = ""; } else buffer = "";
    } else if (tag === "dd") {
      if (closing) { blocks.push({ kind: "paragraph", text: `${term}: ${clean()}` }); buffer = ""; term = ""; } else buffer = "";
    } else if (tag === "ol" || tag === "ul") {
      flush();
      if (tag === "ol") { if (closing) orderedDepth.pop(); else orderedDepth.push(0); }
    } else if (/^(h[1-3]|p|li|pre|div|section|dl|h4|h5|h6)$/.test(tag)) {
      flush();
      if (!closing) open = tag === "h4" || tag === "h5" || tag === "h6" ? "h3" : tag;
    }
    // Inline tags fall through: their text simply continues the current block.
  }
  flush();
  return blocks;
}

// ---- OOXML ----

// XML 1.0 has no way to write most control characters, and a lone surrogate
// cannot be encoded. Tab and newline are handled by the caller.
export function xmlText(text: string): string {
  return text
    .replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, "")
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function run(text: string, bold = false): string {
  const properties = bold ? "<w:rPr><w:b/></w:rPr>" : "";
  return `<w:r>${properties}<w:t xml:space="preserve">${xmlText(text.replace(/[\t\n]/g, " "))}</w:t></w:r>`;
}

function paragraph(text: string, properties = "", bold = false): string {
  return `<w:p>${properties ? `<w:pPr>${properties}</w:pPr>` : ""}${run(text, bold)}</w:p>`;
}

const CELL_BORDERS = ["top", "left", "bottom", "right", "insideH", "insideV"]
  .map(side => `<w:${side} w:val="single" w:sz="4" w:space="0" w:color="808080"/>`)
  .join("");

function tableXml(block: Extract<DocxBlock, { kind: "table" }>): string {
  const columns = Math.max(block.header.length, ...block.rows.map(row => row.length), 1);
  const width = Math.floor(9000 / columns);
  const line = (cells: string[], header: boolean) => {
    const filled = [...cells, ...Array(columns - cells.length).fill("")];
    return `<w:tr>${header ? "<w:trPr><w:tblHeader/></w:trPr>" : ""}${filled
      .map(cell => `<w:tc><w:tcPr><w:tcW w:w="${width}" w:type="dxa"/></w:tcPr>${paragraph(cell, "", header)}</w:tc>`)
      .join("")}</w:tr>`;
  };
  const grid = Array(columns).fill(`<w:gridCol w:w="${width}"/>`).join("");
  return (
    `<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>${CELL_BORDERS}</w:tblBorders></w:tblPr><w:tblGrid>${grid}</w:tblGrid>` +
    (block.header.length ? line(block.header, true) : "") +
    block.rows.map(row => line(row, false)).join("") +
    "</w:tbl>" +
    // Word requires a paragraph after a table that ends a cell or body.
    "<w:p/>"
  );
}

interface NumberedList { start: number }

export function documentXml(blocks: DocxBlock[]): { xml: string; lists: NumberedList[] } {
  const lists: NumberedList[] = [];
  let previous: number | null = null;
  const parts = blocks.map(block => {
    const wasNumbered = previous;
    previous = null;
    switch (block.kind) {
      case "heading":
        return paragraph(block.text, `<w:pStyle w:val="Heading${block.level}"/>`);
      case "bullet":
        return paragraph(block.text, '<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>');
      case "number":
        // A legal draft's numbers mean something. "2." after an interruption stays
        // 2, so a list only continues when the next number actually follows on.
        if (wasNumbered === null || block.n !== wasNumbered + 1) lists.push({ start: block.n });
        previous = block.n;
        return paragraph(block.text, `<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="${lists.length + 1}"/></w:numPr>`);
      case "table":
        return tableXml(block);
      default:
        return paragraph(block.text, block.indent ? `<w:ind w:left="${block.indent * 360}"/>` : "", block.bold);
    }
  });
  const xml =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    parts.join("") +
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>' +
    "</w:body></w:document>";
  return { xml, lists };
}

function numberingXml(lists: NumberedList[]): string {
  const level = (format: string, text: string, font = "") =>
    `<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="${format}"/><w:lvlText w:val="${text}"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="540" w:hanging="360"/></w:pPr>${font}</w:lvl>`;
  return (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
    `<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>${level("bullet", "•")}</w:abstractNum>` +
    `<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/>${level("decimal", "%1.")}</w:abstractNum>` +
    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>' +
    lists
      .map(
        (list, index) =>
          `<w:num w:numId="${index + 2}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="${list.start}"/></w:lvlOverride></w:num>`,
      )
      .join("") +
    "</w:numbering>"
  );
}

const CONTENT_TYPES =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
  '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
  '<Default Extension="xml" ContentType="application/xml"/>' +
  '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
  '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>' +
  '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>' +
  "</Types>";

const ROOT_RELS =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
  "</Relationships>";

const DOCUMENT_RELS =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' +
  '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>' +
  "</Relationships>";

function headingStyle(level: number, size: number): string {
  return `<w:style w:type="paragraph" w:styleId="Heading${level}"><w:name w:val="heading ${level}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="${level - 1}"/></w:pPr><w:rPr><w:b/><w:sz w:val="${size}"/><w:szCs w:val="${size}"/></w:rPr></w:style>`;
}

const STYLES =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
  '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="en-IN"/></w:rPr></w:rPrDefault>' +
  '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>' +
  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>' +
  headingStyle(1, 32) +
  headingStyle(2, 26) +
  headingStyle(3, 24) +
  '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/></w:style>' +
  "</w:styles>";

// ---- a stored zip ----

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** Stored, not deflated: the files are small, and Word and LibreOffice both accept it. */
export function zipStored(entries: { name: string; data: string }[]): Uint8Array {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  // 1 January 1980, the first date the format can hold. No clock in the file, so
  // the same text makes the same bytes and the file does not say when it was made.
  const DOS_DATE = 0x0021;
  const header = (size: number, write: (view: DataView, bytes: Uint8Array) => void) => {
    const bytes = new Uint8Array(size);
    write(new DataView(bytes.buffer), bytes);
    return bytes;
  };
  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    const data = encoder.encode(entry.data);
    const crc = crc32(data);
    const fields = (view: DataView, at: number) => {
      view.setUint16(at, 20, true); // version needed
      view.setUint16(at + 2, 0x0800, true); // names are UTF-8
      view.setUint16(at + 4, 0, true); // stored
      view.setUint16(at + 6, 0, true); // time
      view.setUint16(at + 8, DOS_DATE, true);
      view.setUint32(at + 10, crc, true);
      view.setUint32(at + 14, data.length, true);
      view.setUint32(at + 18, data.length, true);
      view.setUint16(at + 22, name.length, true);
    };
    const local = header(30 + name.length, (view, bytes) => {
      view.setUint32(0, 0x04034b50, true);
      fields(view, 4);
      bytes.set(name, 30);
    });
    const start = offset;
    central.push(
      header(46 + name.length, (view, bytes) => {
        view.setUint32(0, 0x02014b50, true);
        view.setUint16(4, 20, true); // version made by
        fields(view, 6);
        view.setUint32(42, start, true);
        bytes.set(name, 46);
      }),
    );
    chunks.push(local, data);
    offset += local.length + data.length;
  }
  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = header(22, view => {
    view.setUint32(0, 0x06054b50, true);
    view.setUint16(8, entries.length, true);
    view.setUint16(10, entries.length, true);
    view.setUint32(12, centralSize, true);
    view.setUint32(16, offset, true);
  });
  const all = [...chunks, ...central, end];
  const output = new Uint8Array(all.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of all) {
    output.set(part, at);
    at += part.length;
  }
  return output;
}

export function buildDocx(blocks: DocxBlock[]): Uint8Array {
  const { xml, lists } = documentXml(blocks);
  // [Content_Types].xml goes first, which some readers expect.
  return zipStored([
    { name: "[Content_Types].xml", data: CONTENT_TYPES },
    { name: "_rels/.rels", data: ROOT_RELS },
    { name: "word/document.xml", data: xml },
    { name: "word/_rels/document.xml.rels", data: DOCUMENT_RELS },
    { name: "word/styles.xml", data: STYLES },
    { name: "word/numbering.xml", data: numberingXml(lists) },
  ]);
}

export function docxFilename(title: string, version?: number): string {
  const slug = title.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "document";
  return `${slug}${version === undefined ? "" : `-v${version}`}.docx`;
}

/** Nothing leaves the browser: the file is made here and handed to the download. */
export function saveDocx(filename: string, blocks: DocxBlock[]): void {
  const bytes = buildDocx(blocks);
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: DOCX_MIME }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
