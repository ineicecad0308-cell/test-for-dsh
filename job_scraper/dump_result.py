# -*- coding: utf-8 -*-
"""重跑一次抓取（命中缓存）并导出比对用 JSON，供 validate_output.py 校验“需求内容=职位介绍全文”。"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "platforms"))
sys.stdout.reconfigure(encoding="utf-8")

from models import FilterConfig  # noqa: E402
from scraper import run  # noqa: E402

cfg = FilterConfig(
    platform="liepin",
    keyword="SAP MM",
    years=(3, 5),
    people_min=1000,
    locations=["上海", "北京", "深圳", "广州", "杭州", "苏州", "成都", "武汉", "大连"],
    require_tokens=["SAP", "MM"],
    max_details=150,
    limit_rows=100,
    max_per_company=3,
)
res = run(cfg, cache_path=os.path.join(BASE, "data", "detail_cache.json"), progress=print)
data = {
    "cfg": cfg.summary(),
    "postings": [{
        "company": j.company,
        "title": j.title,
        "link": j.link,
        "work_years": j.work_years,
        "location": j.location,
        "full_description": j.full_description or j.description,
    } for j in res.postings],
    "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in res.rows],
}
json.dump(data, open(os.path.join(BASE, "data", "run_result.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("postings", len(data["postings"]), "rows", len(data["rows"]))
