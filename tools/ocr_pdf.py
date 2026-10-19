# -*- coding: utf-8 -*-
"""OCR a PDF (scanned) to text using PyMuPDF rendering + RapidOCR (Chinese)."""
import sys, io
import pymupdf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def ocr_pdf(pdf_path, out_path, start=0, end=None, dpi=200):
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    doc = pymupdf.open(pdf_path)
    n = len(doc)
    end = n if end is None else min(end, n)
    out = []
    for i in range(start, end):
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        img_path = out_path + f".p{i+1}.png"
        pix.save(img_path)
        result, _ = ocr(img_path)
        lines = [r[1] for r in result] if result else []
        out.append(f"===== 第{i+1}页 =====")
        out.extend(lines)
        import os
        os.remove(img_path)
        print(f"page {i+1}/{n}: {len(lines)} lines", flush=True)
    txt = "\n".join(out)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"DONE chars={len(txt)} pages={end-start}")

if __name__ == "__main__":
    pdf, outp = sys.argv[1], sys.argv[2]
    s = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    e = int(sys.argv[4]) if len(sys.argv) > 4 else None
    ocr_pdf(pdf, outp, s, e)
