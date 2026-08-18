/**
 * Minimal, dependency-free, uncompressed PDF builder for e2e fixtures.
 *
 * Produces a real, spec-valid PDF with a genuine text layer (parseable by
 * pypdf, the backend's extractor) without needing a PDF library in the test
 * runner. One content stream per page, each with its own literal text.
 */
function escapePdfText(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

export function buildTextPdf(pageTexts: string[]): Buffer {
  const objects: string[] = [];
  const pageCount = pageTexts.length;

  const pageObjNums = pageTexts.map((_, i) => 4 + i * 2);
  const contentObjNums = pageTexts.map((_, i) => 5 + i * 2);
  const fontObjNum = 4 + pageCount * 2;

  objects.push(`1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n`);
  objects.push(
    `2 0 obj\n<< /Type /Pages /Kids [${pageObjNums.map((n) => `${n} 0 R`).join(' ')}] /Count ${pageCount} >>\nendobj\n`,
  );
  objects.push(`3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n`);

  pageTexts.forEach((text, i) => {
    const pageNum = pageObjNums[i];
    const contentNum = contentObjNums[i];
    objects.push(
      `${pageNum} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] ` +
        `/Resources << /Font << /F1 3 0 R >> >> /Contents ${contentNum} 0 R >>\nendobj\n`,
    );
    const stream = `BT /F1 14 Tf 72 750 Td (${escapePdfText(text)}) Tj ET`;
    objects.push(`${contentNum} 0 obj\n<< /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`);
  });
  void fontObjNum;

  let pdf = '%PDF-1.4\n';
  const offsets: number[] = [0];
  for (const obj of objects) {
    offsets.push(Buffer.byteLength(pdf, 'latin1'));
    pdf += obj;
  }
  const xrefStart = Buffer.byteLength(pdf, 'latin1');
  const totalObjs = objects.length + 1;
  pdf += `xref\n0 ${totalObjs}\n0000000000 65535 f \n`;
  for (let i = 1; i < offsets.length; i++) {
    pdf += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${totalObjs} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;

  return Buffer.from(pdf, 'latin1');
}
