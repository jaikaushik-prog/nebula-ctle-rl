"""Render every report page and check extraction/bounds; no circuit simulation."""
from __future__ import annotations

import json
import hashlib
import math
import shutil
import subprocess
from pathlib import Path

from nebula.report.competition_2026 import ROOT, OUT, SCRATCH


def main():
    import fitz
    import pdfplumber
    from PIL import Image, ImageDraw
    from pypdf import PdfReader

    path = OUT / "Nebula_Competition_Report.pdf"
    pages = SCRATCH / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(path)
    manifest = json.loads((OUT / 'Nebula_Competition_Report_sources.json').read_text())
    assert len(doc) == manifest['page_count'] == 19
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['report_sha256']
    for source in manifest['sources']:
        assert hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest() == source['sha256'], source['path']
    poppler = shutil.which('pdftoppm') or str(ROOT / 'tmp/pdfs/poppler-runtime/Library/bin/pdftoppm.exe')
    if Path(poppler).is_file():
        subprocess.run([poppler, '-r', '122', '-png', str(path), str(pages / 'page')], check=True, capture_output=True)
        renderer = 'Poppler pdftoppm 122 dpi'
    else:
        renderer = 'PyMuPDF interim render; Poppler final review pending'
    problems = []
    stats = []
    for i, page in enumerate(doc, 1):
        if not Path(poppler).is_file():
            pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            pix.save(pages / f"page-{i:02d}.png")
        txt = page.get_text()
        assert len(txt.strip()) > 500
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    x0,y0,x1,y1 = span["bbox"]
                    if x0 < 0 or y0 < 0 or x1 > page.rect.width+.5 or y1 > page.rect.height+.5:
                        problems.append({"page": i, "text": span["text"], "bbox": list(span["bbox"])})
        body = [b for b in page.get_text('blocks') if b[1] > 105 and b[3] < 800]
        assert body and max(b[3] for b in body) > 740, f'Page {i}: sparse bottom'
        stats.append({"page": i, "characters": len(txt), "images": len(page.get_images()),
                      "body_bottom_pt": round(max(b[3] for b in body), 1)})
    for group in range(math.ceil(len(doc)/4)):
        sheet = Image.new("RGB", (1040, 1510), "#dfe5eb")
        d = ImageDraw.Draw(sheet)
        for offset in range(4):
            p = group*4+offset+1
            if p > len(doc):
                break
            with Image.open(pages / f"page-{p:02d}.png") as im:
                im.thumbnail((490, 706))
                x,y = 15+(offset%2)*515, 30+(offset//2)*745
                sheet.paste(im, (x,y))
                d.text((x,y-18), f"PAGE {p}", fill="#16263c")
        sheet.save(pages / f"contact-{group+1}.png")
    reader = PdfReader(path)
    assert len(reader.pages) == 19 and len(reader.outline) == 19
    with pdfplumber.open(path) as parsed:
        text = "\n".join(p.extract_text() or "" for p in parsed.pages)
    for expected in ["315/315", "45/45", "0.1550", "NOT_VERIFIED", "behavioural", "8.834", "1.769", "0.007855", "rl-physical", "p2/q2/p3/q3", "Imitation only", "BANK NO FIXED"]:
        assert expected in text, expected
    assert "\ufffd" not in text
    assert not problems, problems
    qa = {"pages": stats, "bounds_issues": problems, "renderer": renderer,
          "report_sha256": manifest['report_sha256'],
          "source_hash_checks": "PASS", "text_checks": "PASS", "visual_review": "PENDING"}
    (SCRATCH / "qa.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    (OUT / 'Nebula_Competition_Report_review.json').write_text(json.dumps(qa, indent=2), encoding='utf-8')
    print(f"PASS: 19 pages, source hashes, outlines, extraction, body depth and text bounds. Rendered with {renderer}.")


if __name__ == "__main__":
    main()
