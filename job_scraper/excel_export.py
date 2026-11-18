# -*- coding: utf-8 -*-
"""导出 Excel：岗位需求明细 / 公司与岗位汇总 / 筛选条件 / 职位清单。"""
from __future__ import annotations

import datetime
import os
import re
from collections import OrderedDict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from models import fmt_range  # noqa: F401  (保留给调用方复用)

TITLE_FILL = PatternFill("solid", fgColor="1F4E79")
HEAD_FILL = PatternFill("solid", fgColor="DCE6F1")
ALT_FILL = PatternFill("solid", fgColor="F2F7FB")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
FONT = "微软雅黑"
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(value):
    """清洗 Excel 不接受的控制字符，其余内容原样保留。"""
    if isinstance(value, str):
        return _ILLEGAL.sub("", value)
    return value


def _title(ws, text, ncols):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=text)
    c.font = Font(name=FONT, size=13, bold=True, color="FFFFFF")
    c.fill = TITLE_FILL
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30


def _header(ws, headers, widths):
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=2, column=j, value=h)
        c.font = Font(name=FONT, size=10, bold=True)
        c.fill = HEAD_FILL
        c.alignment = CENTER
        c.border = BORDER
        ws.column_dimensions[get_column_letter(j)].width = widths[j - 1]
    ws.row_dimensions[2].height = 26


def _row(ws, r, values, center_cols, link_col=None, link=None):
    for j, v in enumerate(values, 1):
        c = ws.cell(row=r, column=j, value=_clean(v))
        c.font = Font(name=FONT, size=9)
        c.border = BORDER
        c.alignment = CENTER if j in center_cols else WRAP
        if r % 2 == 0:
            c.fill = ALT_FILL
    if link_col and link:
        c = ws.cell(row=r, column=link_col)
        c.hyperlink = link
        c.font = Font(name=FONT, size=9, color="0563C1", underline="single")


def export(result, path: str) -> str:
    cfg = result.cfg
    rows = result.rows
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    wb = Workbook()

    # ---------------- Sheet1 岗位需求明细
    # I/J 列（要求类型、细分类型）已按需求移除；需求内容 = 猎聘“职位介绍”栏全文
    ws = wb.active
    ws.title = "岗位需求明细"
    headers = ["序号", "公司名称", "岗位名称", "工作地点", "公司规模", "经验要求", "学历要求",
               "薪资范围", "需求内容", "命中关键词", "职位链接", "平台", "抓取时间"]
    widths = [6, 26, 28, 15, 13, 10, 10, 14, 100, 11, 44, 9, 16]
    cond = cfg.summary()
    _title(ws, f"{cond['平台']}「{cond['关键词']}」岗位要求汇总 · "
               f"{cond['工作地点']} · 经验 {cond['经验要求']} · 公司规模 {cond['公司规模']}"
               f" · 共 {len(rows)} 行", len(headers))
    _header(ws, headers, widths)
    for i, r in enumerate(rows, 3):
        _row(ws, i, [r["序号"], r["公司名称"], r["岗位名称"], r["工作地点"], r["公司规模"],
                     r["经验要求"], r["学历要求"], r["薪资范围"], r["需求内容"],
                     r["命中关键词"], r["职位链接"], r["平台"], now],
             {1, 4, 5, 6, 7, 10, 12, 13}, 11, r["职位链接"])
        # 需求内容为长文本，按内容量给行高（上限 409，Excel 单行最大高度）
        text = str(r["需求内容"] or "")
        lines = sum(max(1, -(-sum(2 if ord(ch) > 127 else 1 for ch in seg) // 195))
                    for seg in text.split("\n")) or 1
        ws.row_dimensions[i].height = min(13.5 * lines + 5, 409)
    ws.freeze_panes = "C3"
    if rows:
        ws.auto_filter.ref = f"A2:M{2 + len(rows)}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:2"

    # ---------------- Sheet2 公司与岗位汇总
    ws2 = wb.create_sheet("公司与岗位汇总")
    h2 = ["序号", "公司名称", "岗位名称", "工作地点", "公司规模", "经验要求", "学历要求",
          "薪资范围", "拆分要求条数", "行业", "职位链接"]
    w2 = [6, 30, 34, 22, 13, 10, 10, 14, 13, 18, 44]
    agg: OrderedDict[str, dict] = OrderedDict()
    for r in rows:
        key = (r["公司名称"], r["岗位名称"], r["工作地点"], r["职位链接"])
        if key not in agg:
            agg[key] = dict(r)
        agg[key]["_拆分要求条数"] = agg[key].get("_拆分要求条数", 0) + r.get("_拆分要求条数", 0)
    _title(ws2, f"覆盖公司与岗位一览（{len(agg)} 个岗位 / "
                f"{len({k[0] for k in agg})} 家公司 / {len(rows)} 行）", len(h2))
    _header(ws2, h2, w2)
    for i, (key, s) in enumerate(agg.items(), 3):
        _row(ws2, i, [i - 2, s["公司名称"], s["岗位名称"], s["工作地点"], s["公司规模"],
                      s["经验要求"], s["学历要求"], s["薪资范围"], s.get("_拆分要求条数", ""),
                      s["行业"], s["职位链接"]], {1, 4, 5, 6, 7, 9}, 11, s["职位链接"])
    ws2.freeze_panes = "C3"
    if agg:
        ws2.auto_filter.ref = f"A2:K{2 + len(agg)}"

    # ---------------- Sheet3 筛选条件与统计
    ws3 = wb.create_sheet("筛选条件与统计")
    ws3.column_dimensions["A"].width = 27
    ws3.column_dimensions["B"].width = 118
    _title(ws3, "本次抓取条件与统计", 2)
    lines = [
        ("平台", cond["平台"]),
        ("岗位关键词", cond["关键词"]),
        ("工作地点", cond["工作地点"]),
        ("经验年限", cond["经验要求"] + ("（与岗位年限区间有交集）" if cfg.years_mode == "overlap" else "（岗位年限须完全落在该区间）")),
        ("薪资范围", cond["薪资要求"] or "不限（统一折算为千元/月，比较月薪区间）"),
        ("公司规模", cond["公司规模"]),
        ("必备关键词", cond["必备关键词"] + "（须出现在岗位名称中）"),
        ("排除关键词", cond["排除关键词"]),
        ("行数上限", cond["条数上限"]),
        ("同一公司上限", f"{cfg.max_per_company} 行"),
        ("需求内容", "猎聘“职位介绍”栏全文（保留原始换行，不拆分、不删减）"),
        ("抓取时间", now),
        ("数据来源", "各招聘平台公开招聘页面；详情正文解析自职位详情页的结构化数据（JSON-LD）。"),
        ("—— 统计 ——", ""),
        ("检索到的职位数", str(result.stats.get("检索到的职位", 0))),
        ("预筛通过岗位数", str(result.stats.get("预筛通过", 0))),
        ("命中岗位数（详情校验后）", str(result.stats.get("命中岗位", 0))),
        ("详情新抓 / 缓存命中 / 失败",
         f"{result.stats.get('新抓详情', 0)} / {result.stats.get('缓存命中', 0)} / {result.stats.get('详情失败', 0)}"),
        ("符合条件岗位总数", str(result.stats.get("符合条件岗位总数", len(rows)))),
        ("输出行数", str(len(rows))),
        ("拆分出的要求总数（参考）", str(result.stats.get("拆分出的要求总数", ""))),
    ]
    if result.errors:
        lines.append(("错误/警告", "；".join(result.errors[:5])))
    for i, (k, v) in enumerate(lines, 3):
        a = ws3.cell(row=i, column=1, value=k)
        a.font = Font(name=FONT, size=10, bold=True)
        a.fill = HEAD_FILL
        a.alignment = Alignment(vertical="top", wrap_text=True)
        a.border = BORDER
        b = ws3.cell(row=i, column=2, value=v)
        b.font = Font(name=FONT, size=10)
        b.alignment = Alignment(vertical="top", wrap_text=True)
        b.border = BORDER
        width = sum(2 if ord(ch) > 127 else 1 for ch in str(v))
        ws3.row_dimensions[i].height = 19 * max(1, -(-width // 155)) + 4

    # ---------------- Sheet4 职位清单
    ws4 = wb.create_sheet("职位清单")
    h4 = ["序号", "公司名称", "岗位名称", "工作地点", "公司规模", "行业", "经验要求",
          "学历要求", "薪资范围", "拆分要求条数", "职位链接"]
    w4 = [6, 30, 36, 20, 13, 18, 10, 10, 14, 13, 44]
    counts: dict[tuple, int] = {}
    for r in rows:
        k = (r["公司名称"], r["岗位名称"], r["工作地点"], r["职位链接"])
        counts[k] = counts.get(k, 0) + int(r.get("_拆分要求条数", 0) or 0)
    _title(ws4, f"命中岗位清单（{len(result.postings)} 个）", len(h4))
    _header(ws4, h4, w4)
    for i, job in enumerate(result.postings, 3):
        count = counts.get((job.company, job.title, job.location, job.link), "")
        _row(ws4, i, [i - 2, job.company, job.title, job.location, job.company_scale,
                      job.industry, job.work_years, job.education, job.salary,
                      count, job.link],
             {1, 4, 5, 6, 7, 8, 10}, 11, job.link)
    ws4.freeze_panes = "C3"

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
    return path


def default_filename(cfg) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    kw = (cfg.keyword or "岗位").replace(" ", "").replace("/", "-")
    loc = "".join(cfg.locations)[:8] or "全国"
    return f"招聘要求_{cfg.platform}_{kw}_{loc}_{ts}.xlsx"
