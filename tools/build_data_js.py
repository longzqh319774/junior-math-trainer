# -*- coding: utf-8 -*-
"""合并 data/raw/ 下所有原始题库 JSON → 生成 site/data.js

用法：
    python tools/build_data_js.py

会扫描 data/raw/*.json（由 import_docx.py / 手工整理产生），
把所有题目合并成前端可直接加载的 data.js。
data.js 被 .gitignore 排除，不会进入版本库。
"""
import json
import os
import glob
from collections import Counter

import paths

paths.ensure_dirs()


def load_all():
    items = []
    for f in sorted(glob.glob(os.path.join(paths.RAW_DIR, '*.json'))):
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            print('跳过（解析失败）:', os.path.basename(f), e)
            continue
        if isinstance(data, list):
            items.extend(data)
            print('  载入 %-32s %5d 题' % (os.path.basename(f), len(data)))
    return items


exams = load_all()

out = []
for p in exams:
    src = p.get('src') or (('%s年%s 第%s题') % (p['y'], p.get('region', '中考'), p['n']) if 'y' in p else '未标注来源')
    out.append({
        'src': src,
        'c': p.get('c', '整式'),
        't': p.get('t', '综合'),
        'd': p.get('d', '中等'),
        'q': p.get('q', ''),
        'a': p.get('a', ''),
        'imgs': p.get('imgs', []),
    })

js = 'var FULL_PROBLEMS=' + json.dumps(out, ensure_ascii=False) + ';'
with open(paths.DATA_JS, 'w', encoding='utf-8') as fh:
    fh.write(js)

print('写入 %s' % paths.DATA_JS)
print('总题数: %d | 含图题: %d' % (len(out), sum(1 for p in out if p['imgs'])))
print('概念分布(Top 15):', Counter(p['c'] for p in out).most_common(15))
