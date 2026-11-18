# -*- coding: utf-8 -*-
"""数据模型与通用解析工具。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------- 区间
def parse_range(text: str, *, unit: str = "") -> Optional[tuple[float, float]]:
    """把 "3-5年" / "3年以上" / "20-30k·13薪" / "1.5-2.5万" 解析成数值区间。

    unit 仅用于文档说明；返回值统一为 float 元组（薪资统一折算为“千元/月”）。
    """
    if not text:
        return None
    s = str(text).strip().replace(" ", "").replace("，", ",")
    if not s:
        return None

    if unit == "salary":
        return _parse_salary(s)
    if unit == "people":
        return _parse_people(s)
    return _parse_years(s)


def _parse_years(s: str) -> Optional[tuple[float, float]]:
    if re.search(r"不限|无要求|无需", s):
        return (0.0, 99.0)
    if re.search(r"应届|在校|实习", s):
        return (0.0, 1.0)
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*年", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*年(?:及)?以上", s)
    if m:
        return (float(m.group(1)), 99.0)
    m = re.search(r"(\d+(?:\.\d+)?)\s*年以下", s)
    if m:
        return (0.0, float(m.group(1)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*年", s)
    if m:
        v = float(m.group(1))
        return (v, v)
    # 英文：3-5 years / at least 3 years
    m = re.search(r"(\d+)\s*[-~]\s*(\d+)\s*years?", s, re.I)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"(?:at least|over|minimum of?)\s*(\d+)\s*years?", s, re.I)
    if m:
        return (float(m.group(1)), 99.0)
    return None


def _parse_salary(s: str) -> Optional[tuple[float, float]]:
    """统一折算为 千元/月。"""
    # 年薪：万/年
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万(?:元)?/?年", s)
    if m:
        lo, hi = float(m.group(1)) * 10 / 12, float(m.group(2)) * 10 / 12
        return (round(lo, 1), round(hi, 1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*万(?:元)?/?年", s)
    if m:
        v = float(m.group(1)) * 10 / 12
        return (round(v, 1), round(v, 1))
    # 月薪：万
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万", s)
    if m:
        return (float(m.group(1)) * 10, float(m.group(2)) * 10)
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", s)
    if m:
        v = float(m.group(1)) * 10
        return (v, v)
    # 月薪：k / 千
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK千]", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*[kK千]", s)
    if m:
        v = float(m.group(1))
        return (v, v)
    # 元/月
    m = re.search(r"(\d{3,6})\s*[-~至到]\s*(\d{3,6})\s*元", s)
    if m:
        return (round(float(m.group(1)) / 1000, 1), round(float(m.group(2)) / 1000, 1))
    m = re.search(r"(\d{3,6})\s*元/?月?", s)
    if m:
        v = round(float(m.group(1)) / 1000, 1)
        return (v, v)
    # 纯数字区间，默认按 k
    m = re.search(r"^(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)$", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


def _parse_people(s: str) -> Optional[tuple[float, float]]:
    s = s.replace("人", "").replace("以上", "+")
    m = re.match(r"^(\d+)-(\d+)$", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = re.match(r"^(\d+)\+?$", s)
    if m:
        return (float(m.group(1)), 999999.0)
    return None


def overlap(a: Optional[tuple[float, float]], b: Optional[tuple[float, float]],
            mode: str = "overlap") -> bool:
    """两个区间是否满足条件。mode: overlap=有交集，contains=b 完全落在 a 内。"""
    if not a or not b:
        return False
    if mode == "contains":
        return a[0] <= b[0] and a[1] >= b[1]
    return not (a[1] < b[0] or b[1] < a[0])


def fmt_range(rng: Optional[tuple[float, float]], unit: str = "") -> str:
    if not rng:
        return ""
    lo, hi = rng
    if hi >= 99:
        return f"{lo:g}{unit}以上"
    return f"{lo:g}-{hi:g}{unit}"


# ---------------------------------------------------------------- 岗位
@dataclass
class JobPosting:
    platform: str
    job_id: str
    title: str
    company: str
    location: str
    link: str
    salary: str = ""
    work_years: str = ""
    education: str = ""
    company_scale: str = ""
    industry: str = ""
    refreshed: str = ""
    description: str = ""
    requirement_items: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    # 详情页完整“职位介绍”文本（不去重、不筛选，直接导出用）
    full_description: str = ""
    # 已抓过详情（含“无正文”的情况），下次不再重复请求
    detail_checked: bool = False

    # 解析后的区间
    @property
    def years_span(self):
        return parse_range(self.work_years)

    @property
    def salary_span(self):
        return parse_range(self.salary, unit="salary")

    @property
    def people_span(self):
        return parse_range(self.company_scale, unit="people")

    def to_dict(self) -> dict[str, Any]:
        return {
            "平台": self.platform,
            "职位ID": self.job_id,
            "公司名称": self.company,
            "岗位名称": self.title,
            "工作地点": self.location,
            "公司规模": self.company_scale,
            "行业": self.industry,
            "经验要求": self.work_years,
            "学历要求": self.education,
            "薪资范围": self.salary,
            "刷新时间": self.refreshed,
            "职位链接": self.link,
            "需求条数": len(self.requirement_items),
        }


@dataclass
class FilterConfig:
    """抓取条件。"""
    platform: str = "liepin"
    keyword: str = "SAP MM"
    years: Optional[tuple[float, float]] = (3, 5)
    years_mode: str = "overlap"          # overlap=岗位年限与 3-5 有交集；contains=岗位须完全落在 3-5 内
    salary: Optional[tuple[float, float]] = None   # 千元/月
    salary_mode: str = "overlap"
    people_min: Optional[float] = None
    people_max: Optional[float] = None
    locations: list[str] = field(default_factory=list)
    require_tokens: list[str] = field(default_factory=list)
    exclude_tokens: list[str] = field(default_factory=list)
    max_cards: int = 0                   # 0=不限（每个关键词最多翻 10 页）
    max_details: int = 120               # 详情页最多抓多少条
    limit_rows: int = 100                # Excel 最多展示多少行
    max_per_company: int = 3             # 同一公司最多几行
    exclude_overseas: bool = True
    cache: bool = True

    # 展示用文本
    def summary(self) -> dict[str, str]:
        return {
            "平台": self.platform,
            "关键词": self.keyword,
            "经验要求": fmt_range(self.years, "年") or "不限",
            "薪资要求": (fmt_range(self.salary, "k") or "不限") + ("/月" if self.salary else ""),
            "公司规模": self._people_text(),
            "工作地点": "、".join(self.locations) or "全国",
            "必备关键词": "、".join(self.require_tokens) or "无",
            "排除关键词": "、".join(self.exclude_tokens) or "无",
            "条数上限": str(self.limit_rows),
        }

    def _people_text(self) -> str:
        if self.people_min and self.people_max:
            return f"{self.people_min:g}-{self.people_max:g}人"
        if self.people_min:
            return f"{self.people_min:g}人以上"
        if self.people_max:
            return f"{self.people_max:g}人以下"
        return "不限"
