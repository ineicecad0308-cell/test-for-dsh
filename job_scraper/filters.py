# -*- coding: utf-8 -*-
"""本地筛选：岗位相关性、地点、年限、薪资、公司规模。"""
from __future__ import annotations

import re

from models import FilterConfig, JobPosting, overlap, parse_range

# 常见境外/港澳台地名（用于排除）
OVERSEAS = (
    "香港", "澳门", "台湾", "台北", "新加坡", "马来西亚", "日本", "东京", "大阪",
    "韩国", "首尔", "美国", "纽约", "洛杉矶", "旧金山", "西雅图", "英国", "伦敦",
    "德国", "柏林", "慕尼黑", "法兰克福", "法国", "巴黎", "荷兰", "阿姆斯特丹",
    "比利时", "布鲁塞尔", "越南", "河内", "胡志明", "泰国", "曼谷", "印度", "班加罗尔",
    "阿联酋", "迪拜", "沙特", "澳大利亚", "悉尼", "加拿大", "多伦多", "巴西",
    "墨西哥", "波兰", "匈牙利", "捷克", "西班牙", "意大利", "米兰", "瑞士",
    "瑞典", "丹麦", "挪威", "芬兰", "爱尔兰", "都柏林", "以色列", "土耳其",
    "印度尼西亚", "雅加达", "菲律宾", "马尼拉", "柬埔寨", "缅甸", "老挝",
)

# 省份 -> 常见城市（按城市名匹配地点）
PROVINCE_CITIES = {
    "广东": ["广州", "深圳", "东莞", "佛山", "珠海", "中山", "惠州", "江门", "肇庆",
             "汕头", "湛江", "茂名", "清远", "揭阳", "潮州", "韶关", "梅州", "河源",
             "阳江", "云浮", "汕尾"],
    "江苏": ["南京", "苏州", "无锡", "常州", "南通", "徐州", "扬州", "镇江", "泰州",
             "盐城", "淮安", "连云港", "宿迁"],
    "浙江": ["杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州", "舟山",
             "台州", "丽水"],
    "山东": ["济南", "青岛", "烟台", "潍坊", "临沂", "淄博", "济宁", "泰安", "威海",
             "日照", "东营", "德州", "聊城", "滨州", "菏泽", "枣庄"],
    "福建": ["福州", "厦门", "泉州", "漳州", "莆田", "宁德", "龙岩", "三明", "南平"],
    "河北": ["石家庄", "唐山", "保定", "廊坊", "秦皇岛", "邯郸", "邢台", "沧州",
             "张家口", "承德", "衡水"],
    "四川": ["成都", "绵阳", "德阳", "宜宾", "南充", "泸州", "乐山", "自贡"],
    "湖北": ["武汉", "宜昌", "襄阳", "荆州", "黄石", "十堰", "孝感", "荆门"],
    "湖南": ["长沙", "株洲", "湘潭", "衡阳", "岳阳", "常德", "郴州", "益阳"],
    "河南": ["郑州", "洛阳", "开封", "新乡", "南阳", "许昌", "商丘", "焦作", "周口"],
    "安徽": ["合肥", "芜湖", "蚌埠", "安庆", "马鞍山", "滁州", "阜阳", "宣城"],
    "辽宁": ["沈阳", "大连", "鞍山", "抚顺", "锦州", "营口", "丹东"],
    "陕西": ["西安", "咸阳", "宝鸡", "渭南", "榆林"],
    "江西": ["南昌", "九江", "赣州", "上饶", "宜春", "景德镇"],
    "广西": ["南宁", "柳州", "桂林", "梧州", "北海", "玉林"],
    "云南": ["昆明", "曲靖", "玉溪", "大理", "丽江"],
    "贵州": ["贵阳", "遵义", "六盘水"],
    "山西": ["太原", "大同", "临汾", "运城", "长治"],
    "吉林": ["长春", "吉林", "四平"],
    "黑龙江": ["哈尔滨", "大庆", "齐齐哈尔"],
    "内蒙古": ["呼和浩特", "包头", "鄂尔多斯"],
    "新疆": ["乌鲁木齐", "克拉玛依"],
    "甘肃": ["兰州", "天水"],
    "海南": ["海口", "三亚", "儋州"],
    "宁夏": ["银川"],
    "青海": ["西宁"],
    "西藏": ["拉萨"],
}


def location_terms(locations: list[str]) -> list[str]:
    """把用户输入的地点展开成可匹配的地名词列表（省 -> 省内城市）。"""
    terms: list[str] = []
    for loc in locations:
        loc = (loc or "").strip()
        if not loc or loc in ("全国", "不限", "中国"):
            continue
        terms.append(loc)
        for prov, cities in PROVINCE_CITIES.items():
            hit = loc == prov or (len(loc) >= 2 and prov.startswith(loc)) \
                or (len(prov) >= 2 and loc.startswith(prov))
            if hit:
                terms.extend(cities)
                break
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def is_overseas(location: str) -> bool:
    return any(o in (location or "") for o in OVERSEAS)


def title_matches(title: str, keyword: str, require_all: bool = False) -> bool:
    tokens = [t for t in re.split(r"[\s,，、/|]+", keyword or "") if t]
    if not tokens:
        return True
    low = (title or "").lower()
    hits = [t.lower() in low for t in tokens]
    if require_all:
        return any(t.lower() in low for t in tokens) if len(tokens) == 1 else all(hits)
    return any(hits)


def check(job: JobPosting, cfg: FilterConfig, terms: list[str]) -> tuple[bool, str]:
    """返回 (是否通过, 未通过原因)。"""
    # 1) 标题相关性
    must = [t for t in (cfg.require_tokens or []) if t]
    if must and not any(t.lower() in job.title.lower() for t in must):
        return False, "岗位名称不含必备关键词"
    if cfg.exclude_tokens and any(t.lower() in job.title.lower() for t in cfg.exclude_tokens):
        return False, "岗位名称命中排除词"

    # 2) 地点
    if cfg.exclude_overseas and job.extra.get("country") and job.extra["country"] != "CN":
        return False, "境外岗位"
    if cfg.exclude_overseas and is_overseas(job.location):
        return False, "境外岗位"
    if terms:
        loc = job.location or ""
        if not any(t in loc for t in terms):
            return False, "工作地点不符"

    # 3) 年限
    if cfg.years:
        span = job.years_span
        if span is None:
            return False, "经验要求无法识别"
        if not overlap(span, cfg.years, cfg.years_mode):
            return False, "经验年限不符"

    # 4) 薪资
    if cfg.salary:
        span = job.salary_span
        if span is None:
            return False, "薪资无法识别"
        if not overlap(span, cfg.salary, cfg.salary_mode):
            return False, "薪资不符"

    # 5) 公司规模
    if cfg.people_min or cfg.people_max:
        span = job.people_span
        if span is None:
            return False, "公司规模未公示"
        lo = cfg.people_min if cfg.people_min else 0
        hi = cfg.people_max if cfg.people_max else 10 ** 9
        if span[1] < lo or span[0] > hi:
            return False, "公司规模不符"

    return True, ""
