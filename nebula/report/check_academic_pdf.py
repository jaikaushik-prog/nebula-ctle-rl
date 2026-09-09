"""Render and validate the separate academic Nebula report."""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from nebula.report.competition_2026 import ROOT, OUT

PDF = OUT / 'Nebula_Competition_Report_Academic.pdf'
MANIFEST = OUT / 'Nebula_Competition_Report_Academic_sources.json'
REVIEW = OUT / 'Nebula_Competition_Report_Academic_review.json'
SCRATCH = ROOT / 'tmp/pdfs/competition_academic'


def main() -> None:
    import fitz
    import pdfplumber
    from PIL import Image, ImageDraw
    from pypdf import PdfReader

    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    doc = fitz.open(PDF)
    assert len(doc) == manifest['page_count'] == 22
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == manifest['report_sha256']
    for source in manifest['sources']:
        path = ROOT / source['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256'], source['path']

    pages = SCRATCH / 'pages'
    pages.mkdir(parents=True, exist_ok=True)
    poppler = shutil.which('pdftoppm') or str(ROOT / 'tmp/pdfs/poppler-runtime/Library/bin/pdftoppm.exe')
    if Path(poppler).is_file():
        subprocess.run([poppler, '-r', '144', '-png', str(PDF), str(pages / 'page')],
                       check=True, capture_output=True)
        renderer = 'Poppler pdftoppm 144 dpi'
    else:
        for i, page in enumerate(doc, 1):
            page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(pages / f'page-{i:02d}.png')
        renderer = 'PyMuPDF 144 dpi equivalent'

    problems = []
    stats = []
    for i, page in enumerate(doc, 1):
        text = page.get_text()
        assert len(text.strip()) > (250 if i == 1 else 500), (i, len(text.strip()))
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    x0, y0, x1, y1 = span['bbox']
                    if x0 < 0 or y0 < 0 or x1 > page.rect.width + .5 or y1 > page.rect.height + .5:
                        problems.append({'page': i, 'text': span['text'], 'bbox': list(span['bbox'])})
        body = [b for b in page.get_text('blocks') if b[1] > 105 and b[3] < 800]
        assert body
        bottom = max(b[3] for b in body)
        if i not in (1, 2, 3) and bottom < 625:
            problems.append({'page': i, 'issue': 'sparse body', 'body_bottom_pt': round(bottom, 1)})
        front_minimums = {1: 720, 2: 730, 3: 730}
        if i in front_minimums and bottom < front_minimums[i]:
            problems.append({'page': i, 'issue': 'sparse front matter',
                             'body_bottom_pt': round(bottom, 1)})
        image_count = len(page.get_images())
        if i == 1 and image_count < 1:
            problems.append({'page': i, 'issue': 'missing cover circuit visual'})
        stats.append({'page': i, 'characters': len(text), 'images': image_count,
                      'body_bottom_pt': round(bottom, 1)})

    for group in range(math.ceil(len(doc) / 4)):
        sheet = Image.new('RGB', (1300, 1840), '#dfe5eb')
        draw = ImageDraw.Draw(sheet)
        for offset in range(4):
            page_no = group * 4 + offset + 1
            if page_no > len(doc):
                break
            with Image.open(pages / f'page-{page_no:02d}.png') as im:
                im.thumbnail((615, 875))
                x, y = 18 + (offset % 2) * 642, 30 + (offset // 2) * 905
                sheet.paste(im, (x, y))
                draw.text((x, y - 19), f'PAGE {page_no}', fill='#16263c')
        sheet.save(pages / f'contact-{group + 1:02d}.jpg', quality=90)

    reader = PdfReader(PDF)
    assert len(reader.pages) == len(reader.outline) == 22
    with pdfplumber.open(PDF) as parsed:
        text = '\n'.join(page.extract_text() or '' for page in parsed.pages)
    expected = [
        'Abstract and project objectives', 'Contents and evidence map',
        'CHAPTER 1 / PROBLEM AND OBJECTIVES', 'CHAPTER 2 / AUTOMATED FRAMEWORK',
        'CHAPTER 3 / ANALOG VERIFICATION', 'CHAPTER 4 / REINFORCEMENT LEARNING',
        'CHAPTER 5 / REPRODUCIBILITY', 'CHAPTER 6 / CONCLUSIONS',
        'Future work and development priorities', '315/315', '45/45',
        '91.8x', '0.1550', 'Jai Kaushik', 'Rishabh Agarwal', 'Avi Mehta',
        'Birla Institute of Technology and Science, Pilani',
        'Final circuit at a glance', 'What the automated run produces',
        'Three evidence layers'
    ]
    for value in expected:
        assert value in text, value
    figures = [int(x) for x in re.findall(r'Figure\s+(\d+)\.', text)]
    assert figures == list(range(1, 13)), figures
    assert '\ufffd' not in text
    assert 'Future work and development priorities' in doc[-1].get_text()
    assert not problems, problems

    qa = {'pages': stats, 'bounds_issues': problems, 'renderer': renderer,
          'report_sha256': manifest['report_sha256'], 'source_hash_checks': 'PASS',
          'text_checks': 'PASS', 'figure_sequence': figures, 'visual_review': 'PENDING'}
    REVIEW.write_text(json.dumps(qa, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: 22 pages, source hashes, outline, extraction, figure sequence, body depth and bounds. Rendered with {renderer}.')


if __name__ == '__main__':
    main()
