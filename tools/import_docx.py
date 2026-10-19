# -*- coding: utf-8 -*-
"""从 Word(.docx) 试卷中抽取题目，按 29 个概念自动分类，并导出题目配图

用法：
    python tools/import_docx.py                          # 读取 papers/ 下所有 .docx
    python tools/import_docx.py --src D:/试卷 --out data/raw/2026全国.json

结果写入 data/raw/*.json，配图导出到 site/img/。
之后运行 python tools/build_data_js.py 即可生成前端题库。
"""
import os, zipfile, json, re, argparse
import xml.etree.ElementTree as ET
from collections import Counter
import paths

paths.ensure_dirs()
IMG_DIR = paths.IMG_DIR

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

CONCEPT_RULES = [
    ('有理数', ['绝对值', '相反数', '倒数', '科学记数法', '数轴', '有理数', '正数', '负数']),
    ('实数', ['平方根', '立方根', '无理数', '估算', '实数']),
    ('二次根式', ['根号', '被开方数', '最简二次根式', '同类二次根式']),
    ('整式', ['整式', '单项式', '多项式', '合并同类项', '去括号', '幂的乘方', '积的乘方', '同底数幂', '整式乘法', '完全平方']),
    ('因式分解', ['因式分解', '分解因式', '十字相乘']),
    ('分式', ['分式', '异分母', '通分', '约分', '最简分式']),
    ('一元一次方程', ['一元一次方程', '一次方程']),
    ('二元一次方程组', ['二元一次方程组', '代入消元', '加减消元']),
    ('不等式与不等式组', ['不等式组', '解集', '数轴上表示']),
    ('一元二次方程', ['一元二次方程', '判别式', '根与系数']),
    ('分式方程', ['分式方程']),
    ('平面直角坐标系', ['象限', '横坐标', '纵坐标']),
    ('一次函数', ['一次函数', '正比例函数']),
    ('反比例函数', ['反比例函数', '反比例']),
    ('二次函数', ['二次函数', '抛物线', '顶点', '对称轴']),
    ('几何图形初步', ['线段', '射线', '对顶角', '余角', '补角', '三视图', '主视图', '俯视图', '左视图']),
    ('相交线与平行线', ['平行线', '同位角', '内错角', '同旁内角', '垂线']),
    ('三角形', ['三角形', '锐角三角形', '钝角三角形', '直角三角形', '外角']),
    ('全等三角形', ['全等', '≌', '对应边', '对应角']),
    ('轴对称与等腰三角形', ['轴对称', '对称轴', '等腰三角形', '等边三角形', '垂直平分线']),
    ('勾股定理', ['勾股定理', '勾股']),
    ('平行四边形与特殊四边形', ['平行四边形', '菱形', '矩形', '正方形', '对角线']),
    ('旋转与中心对称', ['旋转角', '顺时针', '逆时针', '中心对称']),
    ('圆', ['⊙', '直径', '半径', '弦', '切线', '弧', '圆心角', '扇形', '弧长', '优弧', '劣弧']),
    ('相似三角形', ['相似', '∽', '相似比']),
    ('锐角三角函数', ['正弦', '余弦', '正切', '解直角三角形']),
    ('统计', ['条形统计图', '扇形统计图', '折线统计图', '平均数', '中位数', '众数', '方差', '频数', '频率']),
    ('概率', ['概率', '树状图', '列表法', '古典概型']),
]
HINTS = [(c, [kw for kw in kws if kw]) for c, kws in CONCEPT_RULES]

def classify(q):
    s = re.sub(r'\s+', '', q)
    for c, kws in HINTS:
        for kw in kws:
            if kw in s:
                return c, kw
    return '整式', '其他'

def diff_of(num, sec):
    sec = sec or ''
    try: n = int(num)
    except Exception: return '中等'
    if '选择' in sec:
        if n <= 4: return '简单'
        if n <= 9: return '中等'
        return '较难'
    if '填空' in sec:
        if n <= 3: return '简单'
        if n <= 5: return '中等'
        return '较难'
    if '解答' in sec or '应用' in sec:
        if n <= 21: return '中等'
        if n <= 23: return '较难'
        return '难'
    return '中等'

SECTION_RE = re.compile(r'^\s*([一二三四五六七八九十]+)、?\s*(选择题|填空题|解答题|计算题|应用题|作图题|综合题|几何)')
QHEAD_RE = re.compile(r'^\s*(\d{1,2})\s*[．。.\)）]\s*[(（]?\s*([\d分]*)')

def region_year(fname):
    m = re.match(r'(20\d\d)年(.+?)中考', fname)
    if m: return m.group(1), m.group(2)
    m = re.match(r'(20\d\d)年(.+?)中[考学]', fname)
    if m: return m.group(1), m.group(2)
    return '2026', re.sub(r'\.docx$', '', fname)

def short_key(region, n, k):
    return f'nat_{region}_{n}_{k}.png'

def parse_docx(fname, region):
    fpath = os.path.join(SRC, fname)
    with zipfile.ZipFile(fpath, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')
        rels_xml = z.read('word/_rels/document.xml.rels').decode('utf-8')
        media = sorted([n for n in z.namelist() if n.lower().startswith(('word/media/', 'media/'))])
    root = ET.fromstring(doc_xml)
    rels_root = ET.fromstring(rels_xml)
    rid_to_target = {}
    for rel in rels_root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
        rid_to_target[rel.attrib['Id']] = rel.attrib['Target']
    # blip order
    blips = []
    for blip in root.iter(A+'blip'):
        e = blip.attrib.get(R+'embed')
        if e:
            blips.append(e)
    base_to_media = {}
    for m in media:
        base_to_media[os.path.basename(m)] = m
    blip_to_media = {}
    for i, rid in enumerate(blips):
        target = rid_to_target.get(rid, '')
        base = os.path.basename(target).replace('\\', '/').split('/')[-1]
        match = base_to_media.get(base)
        if not match and i < len(media):
            match = media[i]
        blip_to_media[rid] = match
    # walk paragraphs
    body_el = root.find(W+'body')
    items = []   # [(text, [media_files])]
    for p in body_el.findall(W+'p'):
        texts = [t.text or '' for t in p.iter(W+'t')]
        text = ''.join(texts).strip()
        medias = []
        for blip in p.iter(A+'blip'):
            e = blip.attrib.get(R+'embed')
            if e and e in blip_to_media:
                medias.append(blip_to_media[e])
        items.append((text, medias))
    # parse sections & questions
    cur_sec = ''
    cur_q = []
    cur_imgs = []
    cur_num = None
    out = []
    def flush():
        nonlocal cur_q, cur_imgs, cur_num
        if cur_num is not None:
            qtext = '\n'.join(cur_q).strip()
            if qtext:
                out.append((cur_num, qtext, cur_sec, cur_imgs[:]))
        cur_q, cur_imgs, cur_num = [], [], None
    for text, medias in items:
        if medias and not text:
            cur_imgs.extend(medias)
            continue
        if text:
            sm = SECTION_RE.match(text)
            if sm:
                flush()
                cur_sec = sm.group(1) + sm.group(2)
                continue
            qm = QHEAD_RE.match(text)
            if qm:
                flush()
                cur_num = qm.group(1)
                cur_q = [text]
                if medias: cur_imgs = medias[:]
                continue
            if cur_num is not None:
                cur_q.append(text)
                cur_imgs.extend(medias)
    flush()
    # extract images
    new_out = []
    with zipfile.ZipFile(fpath, 'r') as z:
        for n, qtext, sec, mfs in out:
            rels = []
            for k, m in enumerate(mfs):
                if not m:
                    continue
                try:
                    target = os.path.join(IMG_DIR, short_key(region, n, k))
                    with z.open(m) as src_f, open(target, 'wb') as dst_f:
                        dst_f.write(src_f.read())
                    rels.append('img/' + os.path.basename(target))
                except KeyError:
                    pass
            new_out.append((n, qtext, sec, rels))
    return new_out

def main():
    ap = argparse.ArgumentParser(description='从 Word 试卷中抽取题目')
    ap.add_argument('--src', default=paths.papers_dir(), help='docx 试卷目录（默认 papers/）')
    ap.add_argument('--out', default=os.path.join(paths.RAW_DIR, 'docx_import.json'), help='输出原始 JSON 路径')
    args = ap.parse_args()
    SRC, OUT = args.src, args.out
    if not os.path.isdir(SRC):
        print('目录不存在：%s' % SRC)
        print('请用 --src 指定试卷目录，或把 docx 放进 papers/')
        return
    files = sorted([f for f in os.listdir(SRC) if f.endswith('.docx') and not f.startswith('~$')])
    if not files:
        print('未在 %s 找到 .docx 文件' % SRC)
        return
    problems, fail, summary = [], [], []
    for fi in files:
        year, region = region_year(fi)
        rl = region.rstrip('省').rstrip('市').rstrip('州').rstrip('盟')
        try:
            qs = parse_docx(os.path.join(SRC, fi), rl)
        except Exception as e:
            fail.append((fi, str(e)))
            continue
        for n, qtext, sec, imgs in qs:
            c, t = classify(qtext)
            d = diff_of(n, sec)
            problems.append({'y': int(year), 'n': int(n), 'src': f'{year}·{rl}中考 第{n}题',
                             'c': c, 't': t, 'd': d, 'q': qtext, 'a': '', 'imgs': imgs})
        summary.append((rl, len(qs), sum(1 for q in qs if q[3])))
        print(f'{rl:10} 题{len(qs):3} 含图{sum(1 for q in qs if q[3]):3}')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(problems, fh, ensure_ascii=False)
    print('==== 总量 %d 题 | 含图 %d 题 | 输出 %s' % (
        len(problems), sum(1 for p in problems if p.get('imgs')), OUT))
    print('概念分布:', Counter(p['c'] for p in problems).most_common(10))
    if fail:
        print('FAILED:', fail[:10])
    print('下一步：python tools/build_data_js.py')

if __name__ == '__main__':
    main()