# -*- coding: utf-8 -*-
"""猎聘（liepin.com）平台适配器。

- 搜索：POST https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job
  （需先访问站点拿 XSRF-TOKEN；PC UA 会被风控返回 {"flag":0}，实测移动 UA 可用）
- 详情：移动页 https://m.liepin.com/job/<id>.shtml 里的 JSON-LD JobPosting
"""
from __future__ import annotations

import json
import random
import re
import ssl
import string
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import http.cookiejar
from typing import Any, Iterable

try:
    from ..models import JobPosting
    from .base import Platform, PlatformError, register
except ImportError:  # pragma: no cover
    from models import JobPosting
    from platforms.base import Platform, PlatformError, register

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
             "Mobile/15E148 Safari/604.1")

SEARCH_API = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"
HOME = "https://www.liepin.com/zhaopin/"
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# 开放平台/JSON-LD 描述里可能混入 NUL 等控制字符，Excel 不接受
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_text(text: str) -> str:
    if not text:
        return ""
    return _ILLEGAL.sub("", str(text))


@register
class LiepinPlatform(Platform):
    name = "liepin"
    label = "猎聘"
    PAGE_SIZE = 42
    MAX_PAGES = 10

    def __init__(self, delay: float = 0.8, timeout: int = 40, retries: int = 3):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.ctx = ssl.create_default_context()
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx),
        )
        self.xsrf = None
        self._refresh_cookie()

    # ------------------------------------------------ 基础
    def _refresh_cookie(self) -> None:
        try:
            self.op.open(urllib.request.Request(
                HOME, headers={"User-Agent": UA_MOBILE}), timeout=self.timeout).read()
        except Exception as e:  # pragma: no cover
            raise PlatformError(f"访问猎聘首页失败：{e}") from e
        toks = [c.value for c in self.cj if c.name.upper() == "XSRF-TOKEN"]
        if not toks:
            raise PlatformError("未能获取猎聘 XSRF-TOKEN（可能被风控拦截）")
        self.xsrf = toks[0]

    def _headers(self, referer: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": UA_MOBILE,
            "X-Client-Type": "web",
            "X-Fscp-Bi-Stat": json.dumps({"location": referer}),
            "X-Fscp-Fe-Version": "",
            "X-Fscp-Std-Info": '{"client_id": "40108"}',
            "X-Fscp-Trace-Id": str(uuid.uuid4()),
            "X-Fscp-Version": "1.1",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.liepin.com",
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
            "X-XSRF-TOKEN": self.xsrf or "",
        }

    def prepare_detail(self) -> None:
        if not self.xsrf:
            self._refresh_cookie()

    # ------------------------------------------------ 搜索
    def search_page(self, keyword: str, page: int) -> dict[str, Any]:
        rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))
        form = {
            "city": "", "dq": "", "pubTime": "", "currentPage": page,
            "pageSize": 40, "key": keyword, "suggestTag": "", "workYearCode": "",
            "compId": "", "compName": "", "compTag": "", "industry": "",
            "salaryCode": "", "jobKind": "", "compScale": "", "compKind": "",
            "compStage": "", "eduLevel": "", "salaryLow": "", "salaryHigh": "",
        }
        ptf = {"scene": "page", "skId": rnd, "fkId": rnd, "ckId": rnd,
               "sfrom": "search_job_pc"}
        payload = {"data": {"mainSearchPcConditionForm": form, "passThroughForm": ptf}}
        referer = "https://m.liepin.com/zhaopin/?key=" + urllib.parse.quote(keyword)

        last_err = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(
                    SEARCH_API, data=json.dumps(payload).encode("utf-8"),
                    headers=self._headers(referer), method="POST")
                raw = self.op.open(req, timeout=self.timeout).read().decode("utf-8", "replace")
                obj = json.loads(raw)
                if "data" not in obj or obj.get("flag") != 1:
                    raise PlatformError(f"搜索接口返回异常：{raw[:120]}")
                return obj["data"]
            except Exception as e:  # 风控/网络
                last_err = e
                time.sleep(2 + attempt * 3)
                try:
                    self._refresh_cookie()
                except Exception:
                    pass
        raise PlatformError(f"搜索失败（已重试 {self.retries} 次）：{last_err}")

    def iter_cards(self, keyword: str, max_cards: int = 0) -> Iterable[dict[str, Any]]:
        total = 0
        for page in range(self.MAX_PAGES):
            data = self.search_page(keyword, page)
            payload = data.get("data") or {}
            cards = payload.get("jobCardList") or []
            if not cards:
                break
            for card in cards:
                yield card
                total += 1
                if max_cards and total >= max_cards:
                    return
            pg = data.get("pagination") or {}
            if page + 1 >= (pg.get("totalPage") or self.MAX_PAGES):
                break
            time.sleep(max(self.delay, 0.5))

    # ------------------------------------------------ 卡片 -> JobPosting
    def to_posting(self, card: dict[str, Any], keyword: str = "") -> JobPosting:
        job = card.get("job") or {}
        comp = card.get("comp") or {}
        link = job.get("link") or ""
        job_id = str(job.get("jobId") or "")
        if not link and job_id:
            link = f"https://www.liepin.com/job/{job_id}.shtml"
        return JobPosting(
            platform="猎聘",
            job_id=job_id,
            title=(job.get("title") or "").strip(),
            company=(comp.get("compName") or "").strip(),
            location=(job.get("dq") or "").strip(),
            link=link,
            salary=(job.get("salary") or "").strip(),
            work_years=(job.get("requireWorkYears") or "").strip(),
            education=(job.get("requireEduLevel") or "").strip(),
            company_scale=(comp.get("compScale") or "").strip(),
            industry=(comp.get("compIndustry") or "").strip(),
            refreshed=str(job.get("refreshTime") or ""),
            extra={"keyword": keyword},
        )

    # ------------------------------------------------ 详情
    def _fetch_detail_html(self, job: JobPosting) -> str:
        candidates = []
        if job.link:
            candidates.append(job.link.replace("https://www.liepin.com/", "https://m.liepin.com/"))
        if job.job_id:
            alt = f"https://m.liepin.com/job/{job.job_id}.shtml"
            if alt not in candidates:
                candidates.append(alt)
        last_err = None
        for url in candidates:
            for attempt in range(self.retries):
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": UA_MOBILE,
                                      "Accept-Language": "zh-CN,zh;q=0.9",
                                      "Referer": "https://m.liepin.com/zhaopin/"})
                    return self.op.open(req, timeout=self.timeout).read().decode("utf-8", "replace")
                except Exception as e:
                    last_err = e
                    time.sleep(1.5 + attempt * 2)
        raise PlatformError(f"详情页抓取失败：{last_err}")

    def fill_detail(self, job: JobPosting, ck: dict[str, Any] | None = None) -> bool:
        """抓取详情。ck 为缓存字典（可选），命中时直接恢复，避免重复请求。"""
        ck = ck or {}
        if ck.get("checked") or ck.get("description"):
            job.description = ck.get("description") or ""
            job.full_description = ck.get("full_description") or job.description
            job.detail_checked = True
            job.location = ck.get("location") or job.location
            job.work_years = ck.get("work_years") or job.work_years
            job.education = ck.get("education") or job.education
            job.industry = ck.get("industry") or job.industry
            if ck.get("country"):
                job.extra["country"] = ck["country"]
            return bool(job.description)
        try:
            html = self._fetch_detail_html(job)
        except PlatformError:
            return False
        for block in LD_RE.findall(html):
            try:
                obj = json.loads(block)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                job.description = sanitize_text(obj.get("description") or "")
                # 职位介绍全文：JSON-LD 的 description 即猎聘“职位介绍”栏完整内容
                job.full_description = job.description
                job.detail_checked = True
                org = obj.get("hiringOrganization") or {}
                if org.get("name"):
                    job.company = org["name"]
                addr = ((obj.get("jobLocation") or {}).get("address") or {})
                region = (addr.get("addressRegion") or "").strip()
                city = (addr.get("addressLocality") or "").strip()
                if region and city.startswith(region):
                    city = city[len(region):].lstrip("-· ")
                if city and region and (city == region or city in region):
                    city = ""
                loc = "-".join([p for p in (region, city) if p])
                if len(loc) > 30:
                    loc = loc[:30]
                if loc:
                    job.location = loc
                job.work_years = obj.get("experienceRequirements") or job.work_years
                job.education = obj.get("educationRequirements") or job.education
                job.industry = obj.get("industry") or job.industry
                if addr.get("addressCountry"):
                    job.extra["country"] = addr["addressCountry"]
                ck.update({
                    "checked": True,
                    "description": job.description,
                    "full_description": job.full_description,
                    "location": job.location,
                    "work_years": job.work_years,
                    "education": job.education,
                    "industry": job.industry,
                    "country": job.extra.get("country") or "",
                })
                return bool(job.description)
        return False
