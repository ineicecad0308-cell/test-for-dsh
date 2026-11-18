# -*- coding: utf-8 -*-
"""JD 正文清洗、逐条拆分与分类。"""
import html as htmlmod
import re
from typing import Any

SECTION_WORDS = [
    "岗位职责", "工作职责", "职位职责", "职责描述", "工作内容", "职位描述", "岗位描述",
    "岗位概要", "职位概要", "核心职责", "主要职责",
    "任职要求", "任职资格", "岗位要求", "职位要求", "任职条件", "任职需求", "岗位条件",
    "要求", "加分项", "优先条件", "能力要求", "技能要求", "其他要求", "必备条件",
    "我们希望", "我们希望你", "能力素质", "岗位亮点", "工作地点", "应聘通道", "特别提醒",
    "Position Summary", "Key Responsibilities", "Responsibilities", "Requirements",
    "Key Requirements", "Preferred Experience", "Preferred Technical Skills",
    "Functional Knowledge", "Ideal Candidate", "Qualifications", "Main Tasks",
]
DUTY_WORDS = ("岗位职责", "工作职责", "职位职责", "职责描述", "工作内容", "职位描述",
              "岗位描述", "岗位概要", "职位概要", "核心职责", "主要职责",
              "Responsibilities", "Key Responsibilities", "Main Tasks")
REQ_WORDS = ("任职要求", "任职资格", "岗位要求", "职位要求", "任职条件", "任职需求",
             "岗位条件", "加分项", "优先条件", "能力要求", "技能要求", "其他要求",
             "必备条件", "我们希望", "能力素质", "Requirements", "Key Requirements",
             "Preferred Experience", "Functional Knowledge", "Qualifications", "Ideal Candidate")
SKIP_WORDS = ("岗位亮点", "工作地点", "应聘通道", "特别提醒", "公司简介", "我们提供")

TAG_LABEL = re.compile(
    r"^[（(]?[一二三四五六七八九十]{1,3}[）)]?\s*[、.．]?\s*"
    r"(专业能力|工作经验|综合素质|学历与专业|经验与模块|行业背景|语言能力|必备条件|加分项|"
    r"能力素质|硬性要求|优先条件|其他要求|岗位职责|任职要求)[：:]\s*"
)


def clean(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</(p|div|li|tr)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = htmlmod.unescape(t)
    t = t.replace("\xa0", " ").replace("\u3000", " ")
    t = t.replace("\\n", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return re.sub(r"\n{2,}", "\n", t).strip()


def strip_markdown(s: str) -> str:
    s = re.sub(r"^#{1,6}\s*", "", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = s.replace("`", "")
    s = s.strip().strip('\"“”')
    return s.strip()


def strip_number(line: str) -> str:
    s = strip_markdown(line.strip())
    s = re.sub(r"^(?:\d{1,2}\s*[、.．)）]|\(\s*\d{1,2}\s*\)|（\s*\d{1,2}\s*）)\s*", "", s)
    s = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*", "", s)
    s = re.sub(r"^[lL]\s*\d{1,2}\s*[)）.．]\s*", "", s)
    s = re.sub(r"^[•·●○◆◇▪■\-–—*]\s*", "", s)
    s = re.sub(r"^[•·●○◆◇▪■\-–—*]\s*", "", s)
    return s.strip()


def section_of(line: str):
    raw = line.strip().strip("：:【】[]")
    low = raw.lower()
    for w in SECTION_WORDS:
        wl = w.lower()
        if low == wl or (low.startswith(wl) and len(low) <= len(wl) + 6):
            return w
    return None


def classify(text: str, section: str = "duty") -> str:
    s = text
    if re.search(r"\d+\s*[-~至到]\s*\d+\s*年|\d+\s*年以上|\d+\s*年及以上|经验|年限|项目经验|实施经验|years", s, re.I):
        return "经验要求"
    if re.search(r"本科|硕士|大专|专科|学历|学位|统招|Degree|Bachelor", s):
        return "学历要求"
    if re.search(r"英语|日语|韩语|英文|口语|TOPIK|N1|N2|CET|工作语言|English|Japanese", s):
        return "语言能力"
    if re.search(r"SAP|MM|模块|配置|后台|主数据|MRP|BOM|接口|集成|ABAP|报表|系统|流程|供应链|采购|库存|物料", s):
        return "专业技能"
    if re.search(r"负责|参与|主导|推动|实施|运维|支持|培训|编写|测试|上线|设计|分析|优化|配合|协助|对接|跟进|组织|输出|解决|搭建|承担", s):
        return "岗位职责" if section == "duty" else "综合素质"
    if re.search(r"沟通|协调|团队|抗压|出差|责任心|学习能力|逻辑|表达|文档|服务意识|敬业|communication|team", s, re.I):
        return "综合素质"
    return "岗位职责" if section == "duty" else "综合素质"


def is_noise(s: str) -> bool:
    if not s or len(s) < 6:
        return True
    if re.fullmatch(r"[【\[（(]?\s*(任职要求|岗位职责|任职资格|工作职责|Requirements|Responsibilities)\s*[】\]）)]?[：:]?", s):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 &/、.\-:]{2,60}", s) and len(s.split()) <= 6 and not re.search(r"years|experience", s, re.I):
        return True
    if re.fullmatch(r"[\d\s.,%+—\-/：:]+", s):
        return True
    if re.search(r"We are seeking|We are looking|This role|该岗位为|本岗位为|本职位为|职位概要|岗位概要|核心执行岗", s, re.I):
        return True
    return False


def extract_items(desc: str) -> list[tuple[str, str, str]]:
    """把 JD 拆成 [(section, 子标题, 文本)]。section: duty / req。"""
    text = clean(desc)
    items: list[tuple[str, str, str]] = []
    section = "duty"
    skip = False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        sec = section_of(line)
        if sec:
            low = sec.lower()
            if any(w.lower() in low for w in DUTY_WORDS):
                section, skip = "duty", False
            elif any(w.lower() in low for w in REQ_WORDS):
                section, skip = "req", False
            elif any(w.lower() in low for w in SKIP_WORDS):
                skip = True
            tail = line.split("：", 1)[1].strip() if "：" in line else ""
            if tail and len(tail) > 6:
                items.append((section, "", tail))
            continue
        if skip:
            continue
        body = strip_number(line)
        sub = ""
        m = TAG_LABEL.match(body)
        if m:
            sub = m.group(1)
            body = body[m.end():].strip()
        for p in re.split(r"(?<=[。；;])\s*(?=\d{1,2}\s*[、.．)）])", body):
            p = strip_number(p).strip("；;。 ")
            if is_noise(p):
                continue
            items.append((section, sub, p))
    return items


def relevant(text: str, require_tokens: list[str], exclude_tokens: list[str]) -> bool:
    """内容相关性：命中任一必备词且不命中排除词。"""
    if exclude_tokens and any(t.lower() in text.lower() for t in exclude_tokens):
        return False
    if not require_tokens:
        return True
    return any(t.lower() in text.lower() for t in require_tokens)


def requirement_rows(job, require_tokens: list[str], exclude_tokens: list[str],
                     keyword: str = "") -> list[dict[str, Any]]:
    """把一个岗位拆成“一条要求一行”的记录。"""
    out = []
    for sec, sub, text in extract_items(job.description):
        if not relevant(text, require_tokens, exclude_tokens):
            continue
        if re.search(r"五险一金|薪资|福利|名额|入职带薪|培训费|公众号|简历投递", text):
            continue
        out.append({
            "公司名称": job.company,
            "岗位名称": job.title,
            "工作地点": job.location,
            "公司规模": job.company_scale,
            "行业": job.industry,
            "经验要求": job.work_years,
            "学历要求": job.education,
            "薪资范围": job.salary,
            "要求类型": "岗位职责" if sec == "duty" else "任职要求",
            "细分类型": classify(text, sec),
            "需求内容": text,
            "命中关键词": keyword,
            "职位链接": job.link,
            "平台": job.platform,
            "职位ID": job.job_id,
        })
    return out
