"""统一路径配置：所有工具脚本共用，保证项目可迁移到任意机器。

目录约定：
    <repo>/
      site/          前端（index.html、data.js、img/）
      data/raw/     各题源抽取出的原始 JSON
      papers/       用户自己放待处理试卷的目录（PDF / DOCX，默认不入库）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
IMG_DIR = os.path.join(SITE, 'img')
RAW_DIR = os.path.join(ROOT, 'data', 'raw')
DATA_JS = os.path.join(SITE, 'data.js')


def papers_dir():
    """待处理试卷目录。可用环境变量 PAPERS_DIR 覆盖，默认 <repo>/papers。"""
    return os.environ.get('PAPERS_DIR') or os.path.join(ROOT, 'papers')


def scan_pdfs(dirpath=None):
    """扫描试卷目录，按文件名中的 4 位年份建立 {年份: 文件名} 映射。

    试卷文件名需含年份，例如「2019天津数学试卷.pdf」。
    """
    import glob
    import re
    found = {}
    pattern = os.path.join(dirpath or papers_dir(), '*.pdf')
    for f in glob.glob(pattern):
        m = re.search(r'(20\d{2})', os.path.basename(f))
        if m:
            found[int(m.group(1))] = os.path.basename(f)
    return found


def ensure_dirs():
    for d in (IMG_DIR, RAW_DIR, papers_dir()):
        os.makedirs(d, exist_ok=True)


def import_paths():
    """让同目录脚本可以 `import paths`"""
    if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
