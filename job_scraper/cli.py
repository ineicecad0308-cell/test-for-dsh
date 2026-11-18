# -*- coding: utf-8 -*-
"""命令行入口：按条件抓取招聘要求并导出 Excel。

用法示例：
  python cli.py --platform liepin --keyword "SAP MM" --years 3-5 \
      --salary 15-30 --people 1000+ --location 上海 --rows 100

  python cli.py --interactive          # 一问一答式输入
  python cli.py -h                     # 查看全部参数
"""
from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "platforms"))

from excel_export import default_filename, export  # noqa: E402
from filters import PROVINCE_CITIES  # noqa: E402
from models import FilterConfig  # noqa: E402
from platforms.base import available_platforms, get_platform  # noqa: E402
from scraper import run  # noqa: E402

FIELDS = [
    ("platform", ("--platform", "-p"), {"default": "liepin", "help": "招聘平台（默认 liepin）"}),
    ("keyword", ("--keyword", "-k"), {"default": "SAP MM", "help": "岗位关键词，可用空格分词"}),
    ("years", ("--years", "-y"), {"default": "3-5", "help": "经验年限，如 3-5 / 3+ / 不限"}),
    ("salary", ("--salary", "-s"), {"default": "", "help": "月薪范围（千元），如 15-30 / 20+ / 不限"}),
    ("people", ("--people", "-c"), {"default": "", "help": "公司规模（人），如 1000+ / 500-2000 / 不限"}),
    ("location", ("--location", "-l"), {"default": "", "help": "工作地点，如 上海 / 广东 / 上海,北京"}),
    ("rows", ("--rows", "-n"), {"default": 100, "type": int, "help": "最多导出多少条要求"}),
    ("output", ("--output", "-o"), {"default": "", "help": "输出 Excel 路径"}),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="招聘岗位要求抓取器：按平台/岗位/年限/薪资/公司规模/地点抓取并汇总 Excel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python cli.py -k \"SAP MM\" -y 3-5 -s 15-30 -c 1000+ -l 上海 -n 100")
    for _, flags, kw in FIELDS:
        p.add_argument(*flags, dest=flags[0].lstrip("-").replace("-", "_"), **kw)
    p.add_argument("--require", default="", help="必备关键词（逗号分隔，须出现在岗位名称中），如 SAP,MM")
    p.add_argument("--exclude", default="", help="排除关键词（逗号分隔），如 实习,外包,销售")
    p.add_argument("--years-mode", choices=["overlap", "contains"], default="overlap",
                   help="年限匹配方式：overlap=有交集（默认），contains=岗位年限完全落在输入区间")
    p.add_argument("--include-overseas", action="store_true", help="不排除境外/港澳台岗位")
    p.add_argument("--max-cards", type=int, default=0, help="每个关键词最多读取多少条卡片（0=不限）")
    p.add_argument("--max-details", type=int, default=150, help="最多抓取多少条详情（默认 150）")
    p.add_argument("--max-per-company", type=int, default=3, help="同一公司最多几行（默认 3，0=不限）")
    p.add_argument("--no-cache", action="store_true", help="不使用详情缓存")
    p.add_argument("--cache", default=os.path.join(BASE, "data", "detail_cache.json"),
                   help="缓存文件路径")
    p.add_argument("--list-platforms", action="store_true", help="列出可用平台")
    p.add_argument("--interactive", "-i", action="store_true", help="交互式输入条件")
    return p


def parse_years(text: str):
    text = (text or "").strip().lower().replace("年", "").replace("以上", "+")
    if text in ("", "不限", "any", "none", "0", "*"):
        return None
    if text.endswith("+"):
        return (float(text[:-1]), 99.0)
    if "-" in text:
        lo, hi = text.split("-", 1)
        return (float(lo), float(hi))
    v = float(text)
    return (v, v)


def parse_salary(text: str):
    """支持 15-30、15k-30k、20+、20万 (万元，按 10 千元折算)。"""
    t = (text or "").strip().lower().replace(" ", "").replace("k", "").replace("千", "")
    if t in ("", "不限", "any", "none", "0", "*"):
        return None
    mult = 1.0
    if "万" in t:
        t = t.replace("万", "")
        mult = 10.0
    if t.endswith("+"):
        return (float(t[:-1]) * mult, 999.0)
    if "-" in t:
        lo, hi = t.split("-", 1)
        return (float(lo) * mult, float(hi) * mult)
    v = float(t) * mult
    return (v, v)


def parse_people(text: str):
    t = (text or "").strip().lower().replace("人", "").replace(" ", "")
    if t in ("", "不限", "any", "none", "0", "*"):
        return (None, None)
    if t.endswith("+"):
        return (float(t[:-1]), None)
    if "-" in t:
        lo, hi = t.split("-", 1)
        if hi.endswith("+"):
            return (float(lo), None)
        return (float(lo), float(hi))
    v = float(t)
    return (v, None)


def parse_locations(text: str) -> list[str]:
    parts = [x for x in (text or "").replace("，", ",").replace("、", ",").replace("/", ",").split(",")]
    return [x.strip() for x in parts if x.strip() and x.strip() not in ("全国", "不限")]


def ask(prompt: str, default: str = "") -> str:
    tip = f"{prompt}（回车默认 {default}）: " if default != "" else f"{prompt}: "
    try:
        val = input(tip).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        sys.exit(1)
    return val if val else default


def interactive(args) -> argparse.Namespace:
    plats = available_platforms()
    print("== 招聘要求抓取器 ==")
    print("可用平台：" + "，".join(f"{k}（{v}）" for k, v in plats.items()))
    args.platform = ask("招聘平台", args.platform)
    args.keyword = ask("岗位关键词（如 SAP MM、Java开发）", args.keyword)
    args.years = ask("经验年限（如 3-5、3+、不限）", str(args.years))
    args.salary = ask("月薪范围（千元，如 15-30、20+、不限）", str(args.salary or "不限"))
    args.people = ask("公司规模（人数，如 1000+、500-2000、不限）", str(args.people or "不限"))
    print("常见地点：" + "、".join(list(PROVINCE_CITIES)[:12]) + " 等")
    args.location = ask("工作地点（可多个，用逗号分隔；回车=全国）", str(args.location))
    args.rows = int(ask("最多导出多少行", str(args.rows)) or 100)
    args.max_per_company = int(ask("同一公司最多几行", str(args.max_per_company)) or 3)
    args.require = ask("岗位名称必须具备的关键词（逗号分隔，回车=不限）", args.require)
    args.exclude = ask("需要排除的关键词（逗号分隔，回车=无）", args.exclude)
    out = ask("输出文件路径（回车=自动命名）", "")
    if out:
        args.output = out
    return args


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_platforms:
        print("可用平台：")
        for k, v in available_platforms().items():
            print(f"  {k:<10} {v}")
        return 0
    if args.interactive:
        args = interactive(args)

    try:
        platform = get_platform(args.platform)
    except Exception as e:
        print(f"[错误] {e}")
        return 2

    years = parse_years(args.years)
    salary = parse_salary(args.salary)
    pmin, pmax = parse_people(args.people)
    cfg = FilterConfig(
        platform=platform.name,
        keyword=args.keyword.strip(),
        years=years,
        years_mode=args.years_mode,
        salary=salary,
        people_min=pmin,
        people_max=pmax,
        locations=parse_locations(args.location),
        require_tokens=[t.strip() for t in args.require.replace("，", ",").split(",") if t.strip()],
        exclude_tokens=[t.strip() for t in args.exclude.replace("，", ",").split(",") if t.strip()],
        max_cards=args.max_cards,
        max_details=args.max_details,
        limit_rows=args.rows,
        max_per_company=max(0, args.max_per_company),
        exclude_overseas=not args.include_overseas,
        cache=not args.no_cache,
    )
    if not cfg.keyword:
        print("[错误] 岗位关键词不能为空")
        return 2

    print("抓取条件：")
    for k, v in cfg.summary().items():
        print(f"  {k}: {v}")
    print()

    result = run(cfg, cache_path=args.cache, progress=print)
    if not result.rows:
        print("\n没有抓到符合条件的要求，可适当放宽年限/薪资/规模/地点后重试。")
        if result.errors:
            print("提示：" + "；".join(result.errors[:3]))
        return 1

    out = args.output or os.path.join(BASE, "output", default_filename(cfg))
    if not os.path.isabs(out):
        out = os.path.join(os.getcwd(), out)
    export(result, out)
    print("\n已生成：" + out)
    print("统计：" + "，".join(f"{k} {v}" for k, v in result.stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
