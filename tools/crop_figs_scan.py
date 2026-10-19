# -*- coding: utf-8 -*-
"""扫描版真题图形裁剪：OCR 文本框遮罩 → 非文字墨迹聚类 → 裁剪保存

适用于**没有文本层**的扫描版 PDF（须先用 ocr_pdf.py 抽出题目文本并整理成 JSON）。

用法：
    python tools/crop_figs_scan.py          # 处理全部年份
    python tools/crop_figs_scan.py 2023     # 只处理指定年份
    PAPERS_DIR=D:/my/papers python tools/crop_figs_scan.py

配图清单来源（按优先级）：
    1. data/figure_need.json —— 人工核对的清单，格式 {"2023": [3, 10, 11], "2024": [2, 10]}
       （扫描卷 OCR 常把"如图"字样丢掉，此时必须手工填这份清单）
    2. 否则取 data/raw/*.json 中题干含"如图"的题
"""
import pymupdf, json, re, os, sys, glob
import numpy as np
import cv2
from rapidocr_onnxruntime import RapidOCR
import paths

paths.ensure_dirs()
IMGDIR = paths.IMG_DIR
PDF_DIR = paths.papers_dir()
PDFS = paths.scan_pdfs()
DPI = 200
NEED_RE = re.compile(r'如图|图①|图②|图③|根据图|示意图|平面直角坐标系|网格|坐标系中')


def load_need():
    """构建 {年份: [题号]} 配图清单"""
    cfg = os.path.join(paths.ROOT, 'data', 'figure_need.json')
    if os.path.exists(cfg):
        with open(cfg, encoding='utf-8') as fh:
            return {int(k): v for k, v in json.load(fh).items()}
    need = {}
    for f in sorted(glob.glob(os.path.join(paths.RAW_DIR, '*.json'))):
        with open(f, encoding='utf-8') as fh:
            for p in json.load(fh):
                if 'y' in p and NEED_RE.search(p.get('q', '')):
                    need.setdefault(p['y'], set()).add(p['n'])
    return {k: sorted(v) for k, v in need.items()}


NEED = load_need()
ocr = RapidOCR()


def load_q(year):
    """取该年份的题干文本，用于裁剪结果与题目的一致性校验"""
    qs = {}
    for f in sorted(glob.glob(os.path.join(paths.RAW_DIR, '*.json'))):
        with open(f, encoding='utf-8') as fh:
            for p in json.load(fh):
                if p.get('y') == year:
                    qs[p['n']] = p['q']
    return qs

def norm(s):
    return re.sub(r'[\s，。、．,.:：；;（）()“”"\'"·]', '', s)

NUM_RE = re.compile(r'^\s*(?:[（(]\s*(\d{1,2})\s*[）)]|(\d{1,2})\s*[.、．])')

def line_num(t):
    m = NUM_RE.match(t)
    if not m: return None
    return int(m.group(1) or m.group(2))

def best_overlap(a, b):
    """最长公共子串长度（限制在 b 的前 30 字内）"""
    b = b[:30]
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i+k < len(a) and j+k < len(b) and a[i+k] == b[j+k]:
                k += 1
            best = max(best, k)
    return best

def ocr_page(page):
    pix = page.get_pixmap(dpi=DPI)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if pix.n >= 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    res, _ = ocr(img)
    lines = []
    if res:
        for it in res:
            pts = np.array(it[0], dtype=float)
            lines.append({'y0': float(pts[:,1].min()), 'y1': float(pts[:,1].max()),
                          'x0': float(pts[:,0].min()), 'x1': float(pts[:,0].max()), 't': it[1]})
    lines.sort(key=lambda d: (d['y0'], d['x0']))
    return img, lines

def fig_boxes(img, lines, ytop, ybot):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = np.zeros((h, w), np.uint8)
    for d in lines:
        if d['y1'] < ytop or d['y0'] > ybot: continue
        if d['y1'] - d['y0'] > 48: continue        # 超高的框多为斜置水印，不遮罩
        if d['x1'] - d['x0'] > 1400: continue       # 异常超宽框（整页级）才跳过
        mask[max(0,int(d['y0'])-3):int(d['y1'])+3, max(0,int(d['x0'])-3):int(d['x1'])+3] = 255
    band = np.zeros((h, w), np.uint8); band[int(ytop):int(ybot), :] = 255
    ink = (gray < 160).astype(np.uint8)*255
    fig = cv2.bitwise_and(ink, cv2.bitwise_and(band, cv2.bitwise_not(mask)))
    # 剔除长细横线组件（题中填空下划线），避免把文字与图形串成一片
    n0, lab0, st0, _ = cv2.connectedComponentsWithStats(fig, 8)
    clean = np.zeros_like(fig)
    for i in range(1, n0):
        x, y, ww, hh, area = st0[i]
        if hh <= 7 and ww >= 90:
            continue
        clean[lab0 == i] = 255
    fig = clean
    fig = cv2.morphologyEx(fig, cv2.MORPH_CLOSE, np.ones((7,41), np.uint8))
    fig = cv2.morphologyEx(fig, cv2.MORPH_OPEN, np.ones((2,2), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fig, 8)
    out = []
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        if area < 800 or ww < 50 or hh < 40: continue
        if hh < 45 and ww > 400: continue
        if ww > w*0.95 and hh > h*0.85: continue
        out.append((int(x), int(y), int(ww), int(hh), int(area)))
    out.sort(key=lambda c: -c[4])
    return out

def main(years):
    fmap, log = {}, []
    for y in years:
        if y not in PDFS:
            log.append('%s: 未找到对应 PDF（试卷文件名需含年份）' % y)
            continue
        doc = pymupdf.open(os.path.join(PDF_DIR, PDFS[y]))
        qs = load_q(y)
        nums = list(NEED.get(y, [])); done = set()
        cache = {}
        for pno, page in enumerate(doc):
            if len(done) >= len(nums): break
            img, lines = ocr_page(page)
            cache[pno] = (img, lines)
            # 本页题号行
            starts = []
            for d in lines:
                if d['x0'] > 320: continue            # 题号行靠左，排除"1.2""0.6"等数据误判
                nn = line_num(d['t'])
                if nn is not None: starts.append((d['y0'], nn, d))
            starts.sort()
            for i, (y0, nn, d) in enumerate(starts):
                if nn not in nums or nn in done: continue
                # 题干校验
                frag = norm(qs.get(nn, ''))
                ctx = norm(''.join(x['t'] for x in lines if y0-6 <= x['y0'] <= y0+320))
                ov = best_overlap(ctx, frag)
                if ov < 5:
                    log.append(f'{y} Q{nn} p{pno+1}: 跳过(题干匹配度低 ov={ov})')
                    continue
                ybot = starts[i+1][0] if i+1 < len(starts) else page.rect.height*DPI/72
                cand = fig_boxes(img, lines, y0, ybot)
                if not cand and pno+1 < len(doc):   # 图形可能落到了下一页
                    img2, lines2 = ocr_page(doc[pno+1]); cache[pno+1] = (img2, lines2)
                    nxt = [l['y0'] for l in lines2 if line_num(l['t']) is not None]
                    lim = min(nxt) if nxt else doc[pno+1].rect.height*DPI/72
                    cand = fig_boxes(img2, lines2, 0, lim)
                    if cand:
                        x, yy, ww, hh, area = cand[0]
                        crop = img2[max(0,yy-8):yy+hh+8, max(0,x-8):x+ww+8]
                        fn = f'y{y}_q{nn}.png'; cv2.imwrite(os.path.join(IMGDIR, fn), crop)
                        fmap[f'{y}-{nn}'] = ['img/'+fn]; done.add(nn)
                        log.append(f'{y} Q{nn} p{pno+2}(续): 裁 {ww}x{hh}')
                        continue
                # 原页裁剪（取最大簇；若最大簇之外还有面积够大的独立簇，一并裁）
                picked = []
                if cand:
                    base = cand[0]
                    picked = [base]
                    for c in cand[1:]:
                        cx, cy, cw, ch, ca = c
                        # 与已选簇垂直距离较远则认为独立图形
                        if all(cy+ch < p[1]-30 or cy > p[1]+p[3]+30 for p in picked):
                            picked.append(c)
                    picked = picked[:3]
                if not picked:
                    log.append(f'{y} Q{nn} p{pno+1}: 未找到图形')
                    continue
                img_paths = []
                for k, (x, yy, ww, hh, area) in enumerate(picked):
                    crop = img[max(0,yy-8):yy+hh+8, max(0,x-8):x+ww+8]
                    fn = f'y{y}_q{nn}' + (f'_{k+1}' if len(picked) > 1 else '') + '.png'
                    cv2.imwrite(os.path.join(IMGDIR, fn), crop)
                    img_paths.append('img/'+fn)
                fmap[f'{y}-{nn}'] = img_paths; done.add(nn)
                log.append(f'{y} Q{nn} p{pno+1}: {len(img_paths)}图 {[f"{p[2]}x{p[3]}" for p in picked]}')
        for m in set(nums)-done:
            log.append(f'{y} Q{m}: !!! 缺失')
        doc.close()
    mp = os.path.join(paths.ROOT, 'data', 'figure_map.json')
    old = {}
    if os.path.exists(mp):
        with open(mp, encoding='utf-8') as fh:
            old = json.load(fh)
    old.update(fmap)
    with open(mp, 'w', encoding='utf-8') as fh:
        json.dump(old, fh, ensure_ascii=False, indent=1)
    logdir = os.path.join(paths.ROOT, 'logs')
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, 'crop_scan_log.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(log))
    print('完成，共裁剪 %d 题的图形。日志见 logs/crop_scan_log.txt' % len(fmap))

if __name__ == '__main__':
    if not NEED:
        print('未找到配图清单：请在 data/figure_need.json 中指定，或先整理题干含"如图"的题目')
        sys.exit(1)
    main([int(a) for a in sys.argv[1:]] or sorted(NEED))
