# -*- coding: utf-8 -*-
"""真题 PDF 图形裁剪（适用于含文本层的 Word 整理版试卷）

按题号把页面切分成"题目带"，在带内定位嵌入图片与矢量绘图，裁剪成 PNG 挂到题目上。

用法：
    python tools/crop_figs.py              # 处理 papers/ 下全部试卷
    python tools/crop_figs.py 2019 2020    # 只处理指定年份
    PAPERS_DIR=D:/my/papers python tools/crop_figs.py

要求：
    1. 试卷文件名中含 4 位年份（如「2019天津数学试卷.pdf」）；
    2. data/raw/ 下已有对应年份的题目 JSON（由 import_docx.py 或手工整理生成）。
"""
import pymupdf, json, re, sys, os, glob
import paths

paths.ensure_dirs()
IMGDIR = paths.IMG_DIR
PDF_DIR = paths.papers_dir()
PDFS = paths.scan_pdfs()
NEED_RE = re.compile(r'如图|图①|图②|图③|根据图|示意图|平面直角坐标系|网格|坐标系中')


def load_need():
    """从 data/raw/*.json 中收集需要配图的题号"""
    need = {}  # year -> set(problem numbers)
    for f in sorted(glob.glob(os.path.join(paths.RAW_DIR, '*.json'))):
        with open(f, encoding='utf-8') as fh:
            for p in json.load(fh):
                if 'y' in p and NEED_RE.search(p.get('q', '')):
                    need.setdefault(p['y'], set()).add(p['n'])
    return need

def page_starts(page):
    """页内题号行: [(y0, num)]"""
    d = page.get_text("dict")
    starts = []
    for b in d["blocks"]:
        if b.get("type") != 0: continue
        for ln in b["lines"]:
            text = "".join(s["text"] for s in ln["spans"]).strip()
            m = re.match(r'^(\d{1,2})\s*[.、．]\s*', text)
            if m:
                starts.append((ln["bbox"][1], int(m.group(1))))
    starts.sort()
    return starts

def fig_rects(page):
    """页面上的图形候选框（嵌入图片 + 大矢量绘图），过滤噪声"""
    rects = []
    W, H = page.rect.width, page.rect.height
    for im in page.get_image_info():
        r = pymupdf.Rect(im['bbox'])
        if r.width < 22 and r.height < 22: continue
        if r.width > W*0.85 and r.height > H*0.85: continue
        rects.append(r)
    for dr in page.get_drawings():
        r = dr['rect']
        if r.width < 25 or r.height < 25: continue
        if r.width > W*0.8 and r.height > H*0.8: continue
        rects.append(r)
    return rects

def cluster(rects, gap=8):
    """合并相交/相近矩形"""
    rects = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        while rects:
            r = rects.pop()
            grown = pymupdf.Rect(r.x0-gap, r.y0-gap, r.x1+gap, r.y1+gap)
            i = 0
            while i < len(rects):
                if grown.intersects(rects[i]):
                    r |= rects.pop(i); changed = True
                    grown = pymupdf.Rect(r.x0-gap, r.y0-gap, r.x1+gap, r.y1+gap)
                else:
                    i += 1
            out.append(r)
        rects = out
    return rects

def process_year(year, needset, fmap, log):
    doc = pymupdf.open(os.path.join(PDF_DIR, PDFS[year]))
    # 全文档扫描题号行，构建 band 列表 (num, pno, y0) -> 截止于下一题号
    marks = []  # (pno, y0, num)
    for pno, page in enumerate(doc):
        for y0, num in page_starts(page):
            marks.append((pno, y0, num))
    # 每页图形框
    prects = {pno: fig_rects(page) for pno, page in enumerate(doc)}
    done = set()
    for i, (pno, y0, num) in enumerate(marks):
        if num not in needset or num in done: continue
        # band 范围
        if i+1 < len(marks) and marks[i+1][0] == pno:
            y1 = marks[i+1][1]
        else:
            y1 = doc[pno].rect.height
        band_rects = []
        for r in prects[pno]:
            cy = (r.y0 + r.y1) / 2
            if y0 <= cy <= y1:
                band_rects.append(r)
        # 若跨页：下一页顶部直到下一个题号
        if i+1 < len(marks) and marks[i+1][0] == pno + 1:
            npno = pno + 1
            for r in prects[npno]:
                cy = (r.y0 + r.y1) / 2
                if cy <= marks[i+1][1]:
                    band_rects.append(r)
        if not band_rects:
            log.append(f'{year} Q{num}: 未找到图形')
            continue
        clusters = cluster(band_rects)
        clusters = [c for c in clusters if c.width >= 28 and c.height >= 22]
        clusters.sort(key=lambda r: r.y0)
        if not clusters:
            log.append(f'{year} Q{num}: 图形框均为噪声')
            continue
        page = doc[pno]
        img_paths = []
        for k, c in enumerate(clusters[:3]):
            clip = pymupdf.Rect(max(0,c.x0-4), max(0,c.y0-4), min(page.rect.width,c.x1+4), min(page.rect.height,c.y1+4))
            pix = page.get_pixmap(clip=clip, dpi=200)
            name = f'y{year}_q{num}' + (f'_{k+1}' if len(clusters) > 1 else '') + '.png'
            pix.save(os.path.join(IMGDIR, name))
            img_paths.append('img/' + name)
        fmap[f'{year}-{num}'] = img_paths
        done.add(num)
        log.append(f'{year} Q{num}: {len(img_paths)}图 -> {img_paths[0]}')
    miss = needset - done
    for m in miss:
        log.append(f'{year} Q{m}: !!! 缺失')
    doc.close()

if __name__ == '__main__':
    need = load_need()
    fmap = {}
    log = []
    if not PDFS:
        print('未在 %s 下找到含年份的 PDF，请设置 PAPERS_DIR 或把试卷放进 papers/' % PDF_DIR)
        sys.exit(1)
    years = [int(y) for y in sys.argv[1:]] or sorted(need)
    for y in years:
        if y not in PDFS:
            log.append('%s: 未找到对应 PDF' % y)
            continue
        process_year(y, need.get(y, set()), fmap, log)
    # 合并已有映射（扫描版年份由 crop_figs_scan.py 单独产出）
    mappath = os.path.join(paths.ROOT, 'data', 'figure_map.json')
    old = {}
    if os.path.exists(mappath):
        with open(mappath, encoding='utf-8') as fh:
            old = json.load(fh)
    old.update(fmap)
    with open(mappath, 'w', encoding='utf-8') as fh:
        json.dump(old, fh, ensure_ascii=False, indent=1)
    logdir = os.path.join(paths.ROOT, 'logs')
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, 'crop_log.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(log))
    print('完成，共裁剪 %d 题的图形。日志见 logs/crop_log.txt' % len(fmap))
