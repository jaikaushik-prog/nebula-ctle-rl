"""Render and check the independent submission PDF; visual review remains explicit."""
import json
import re
import shutil
import subprocess

from nebula.report.submission_story import (
    PDF, MANIFEST, REVIEW, SCRATCH, ROOT, sha, verify_sources,
)


def main():
    import fitz
    manifest=json.loads(MANIFEST.read_text())
    assert sha(PDF)==manifest["report_sha256"]
    verify_sources(manifest["sources"])
    pages=SCRATCH/"pages"; pages.mkdir(parents=True,exist_ok=True)
    poppler=shutil.which("pdftoppm") or str(ROOT/"tmp/pdfs/poppler-runtime/Library/bin/pdftoppm.exe")
    subprocess.run([poppler,"-r","120","-png",str(PDF),str(pages/"page")],check=True,capture_output=True)
    doc=fitz.open(PDF)
    assert len(doc)==manifest["page_count"]==25
    assert len(doc.get_toc())==25
    stats=[]; problems=[]; all_text=[]
    for i,page in enumerate(doc,1):
        text=page.get_text(); all_text.append(text)
        assert len(text)>350,(i,"insufficient text")
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines",[]):
                for span in line["spans"]:
                    x0,y0,x1,y1=span["bbox"]
                    if x0<0 or y0<0 or x1>page.rect.width+.5 or y1>page.rect.height+.5:
                        problems.append({"page":i,"text":span["text"],"bbox":span["bbox"]})
        stats.append({"page":i,"characters":len(text),"images":len(page.get_images()),
                      "content_bottom_pt":manifest["content_bottoms_pt"][i-1]})
    text="\n".join(all_text)
    figures=[int(n) for n in re.findall(r"Figure\s+(\d+)\.",text)]
    assert figures==list(range(1,len(manifest["figures"])+1)),figures
    assert "\ufffd" not in text and not problems,problems
    assert not re.search(r"\d\?\d|mm\?|\?C",text), "Damaged scientific symbols"
    assert "-54.92" in text and "-30" in text, "Missing negative HD3 signs"
    review={"report_sha256":sha(PDF),"page_count":len(doc),"source_hash_checks":"PASS",
            "text_bounds":"PASS","outline":"PASS","figure_sequence":figures,
            "renderer":"Poppler pdftoppm, 120 dpi","pages":stats,
            "visual_review":"PENDING","visual_review_note":"Inspect all rendered pages before delivery."}
    REVIEW.write_text(json.dumps(review,indent=2)+"\n",encoding="utf-8")
    print(f"PASS: {len(doc)} pages, hashes, bounds, outline and figures. Visual review pending.")


if __name__=="__main__":
    main()
