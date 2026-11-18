# -*- coding: utf-8 -*-
"""对导出结果做自动化校验。

用法：
  python validate_output.py <xlsx> [--params-json params.json]

校验项：
  1. 工作表与表头（I/J 列已移除，共 13 列）
  2. 每行必填列非空、链接可点
  3. 同一公司不超过 3 行、总行数不超过上限
  4. 需求内容 = 猎聘“职位介绍”全文（与详情接口原始 JSON-LD description 逐条比对）
  5. 表格内部一致性（汇总页/职位清单与明细页数量一致）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
from openpyxl import load_workbook

EXPECT_HEADERS = ["序号", "公司名称", "岗位名称", "工作地点", "公司规模", "经验要求",
                  "学历要求", "薪资范围", "需求内容", "命中关键词", "职位链接", "平台",
                  "抓取时间"]
REQUIRED_COLS = [2, 3, 4, 5, 6, 9, 11]   # B..F, I(需求内容), K(链接)


class Checker:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.fails: list[str] = []

    def check(self, ok: bool, name: str, detail: str = ""):
        self.total += 1
        if ok:
            self.passed += 1
            print(f"  ✔ {name}")
        else:
            self.fails.append(f"{name} {detail}".strip())
            print(f"  ✘ {name} {detail}")

    def report(self) -> bool:
        print(f"\n结果：{self.passed}/{self.total} 项通过")
        if self.fails:
            print("失败项：")
            for f in self.fails:
                print("  -", f)
        return not self.fails


def norm(t: str) -> str:
    """宽松比较：去空白/换行，去控制字符。"""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t or "")
    return re.sub(r"\s+", "", t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--params-json", default="", help="抓取运行结果 JSON（含 postings/rows 原文）")
    ap.add_argument("--max-per-company", type=int, default=3)
    ap.add_argument("--max-rows", type=int, default=100)
    args = ap.parse_args()

    ck = Checker()
    wb = load_workbook(args.xlsx)
    print("文件：", os.path.abspath(args.xlsx))
    print("工作表：", wb.sheetnames)
    ck.check(wb.sheetnames[:1] == ["岗位需求明细"], "第一个工作表为「岗位需求明细」")
    ck.check(len(wb.sheetnames) == 4, "共 4 个工作表", str(wb.sheetnames))

    ws = wb["岗位需求明细"]
    headers = [ws.cell(row=2, column=c).value for c in range(1, ws.max_column + 1)]
    print("表头：", headers)
    ck.check(headers == EXPECT_HEADERS, "A1:M2 表头与预期一致（13 列）")
    ck.check("要求类型" not in headers and "细分类型" not in headers,
             "I/J 列（要求类型、细分类型）已移除")
    ck.check(ws.max_column == 13, "明细页共 13 列", f"实际 {ws.max_column}")

    rows = []
    for r in range(3, ws.max_row + 1):
        vals = [ws.cell(row=r, column=c).value for c in range(1, 14)]
        if all(v in (None, "") for v in vals):
            continue
        rows.append((r, vals))
    print(f"数据行数：{len(rows)}")
    ck.check(0 < len(rows) <= args.max_rows, f"数据行数在 1..{args.max_rows} 之间", str(len(rows)))

    # 必填列
    empty = [(r, c) for r, vals in rows for c in REQUIRED_COLS if vals[c - 1] in (None, "")]
    ck.check(not empty, "必填列无空值", str(empty[:5]))
    # 序号连续
    seqs = [vals[0] for _, vals in rows]
    ck.check(seqs == list(range(1, len(rows) + 1)), "序号从 1 连续", str(seqs[:8]))
    # 链接
    bad_links = [r for r, vals in rows if not str(vals[10]).startswith("https://")]
    ck.check(not bad_links, "职位链接均为 https 链接", str(bad_links[:3]))
    # 每个单元格都有超链接
    no_link = [r for r, _ in rows if ws.cell(row=r, column=11).hyperlink is None]
    ck.check(not no_link, "链接列单元格已设置超链接", str(no_link[:3]))

    # 公司行数上限
    from collections import Counter
    cnt = Counter(vals[1] for _, vals in rows)
    over = {k: v for k, v in cnt.items() if v > args.max_per_company}
    ck.check(not over, f"同一公司不超过 {args.max_per_company} 行", str(over))
    print("  公司分布：", cnt.most_common(6))

    # 需求内容 = 职位介绍全文（长度与结构）
    lens = [len(str(vals[8])) for _, vals in rows]
    ck.check(all(x >= 30 for x in lens), "需求内容长度均 >= 30 字", str(min(lens)))
    print(f"  需求内容长度：min={min(lens)} max={max(lens)} 平均={sum(lens)//len(lens)}")
    multi = sum(1 for _, vals in rows if "\n" in str(vals[8]))
    ck.check(multi == len(rows), "需求内容保留原始换行（多行）", f"{multi}/{len(rows)}")

    # 与运行结果原文比对
    if args.params_json and os.path.exists(args.params_json):
        data = json.load(open(args.params_json, encoding="utf-8"))
        by_key = {}
        for j in data.get("postings", []):
            by_key[(j["company"], j["title"], j["link"])] = j.get("full_description") or j.get("description") or ""
        mism = []
        for _, vals in rows:
            key = (vals[1], vals[2], vals[10])
            src = by_key.get(key)
            if src is None:
                continue
            if norm(src) != norm(vals[8]):
                mism.append((key, len(norm(src)), len(norm(vals[8]))))
        ck.check(not mism, "需求内容与详情页原文逐字一致（忽略空白差异）", str(mism[:3]))

    # 汇总页与明细页一致
    ws2 = wb["公司与岗位汇总"]
    n_pos = ws2.max_row - 2 if ws2.max_row > 2 else 0
    ck.check(n_pos == len(rows), "「公司与岗位汇总」行数与明细一致", f"{n_pos} vs {len(rows)}")
    ws4 = wb["职位清单"]
    n_jobs = ws4.max_row - 2 if ws4.max_row > 2 else 0
    ck.check(n_jobs >= len(rows), "「职位清单」覆盖全部输出行", f"{n_jobs} vs {len(rows)}")

    return 0 if ck.report() else 1


if __name__ == "__main__":
    sys.exit(main())
