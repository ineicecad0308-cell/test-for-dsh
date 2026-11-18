# -*- coding: utf-8 -*-
"""抓取流水线：搜索 -> 本地筛选 -> 抓详情 -> 拆分要求 -> 汇总。"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from filters import check, location_terms
from jd_parser import requirement_rows
from models import FilterConfig, JobPosting
from platforms.base import Platform, get_platform

Progress = Callable[[str], None]


@dataclass
class ScrapeResult:
    cfg: FilterConfig
    postings: list[JobPosting] = field(default_factory=list)
    rejected: list[tuple[JobPosting, str]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class DetailCache:
    """按 平台+jobId 缓存详情正文，避免重复请求。"""

    def __init__(self, path: str, enabled: bool = True):
        self.path = path
        self.enabled = enabled
        self.data: dict[str, dict[str, str]] = {}
        if enabled and os.path.exists(path):
            try:
                self.data = json.load(open(path, encoding="utf-8"))
            except Exception:
                self.data = {}

    def key(self, platform: str, job_id: str) -> str:
        return f"{platform}:{job_id}"

    def get(self, platform: str, job_id: str):
        return self.data.get(self.key(platform, job_id))

    def put(self, platform: str, job_id: str, payload: dict[str, str]) -> None:
        if not self.enabled:
            return
        self.data[self.key(platform, job_id)] = payload

    def save(self) -> None:
        if not self.enabled:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        json.dump(self.data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, self.path)


def run(cfg: FilterConfig, cache_path: str, progress: Progress | None = None,
        platform: Platform | None = None, stop_after_details: int = 0) -> ScrapeResult:
    """执行一次抓取。stop_after_details>0 时只抓这么多详情（调试用）。"""
    say = progress or (lambda msg: None)
    result = ScrapeResult(cfg=cfg)
    pf = platform or get_platform(cfg.platform)
    terms = location_terms(cfg.locations)
    cache = DetailCache(cache_path, cfg.cache)

    say(f"[1/4] 在「{pf.label}」检索「{cfg.keyword}」…")
    seen: set[str] = set()
    cards = []
    try:
        for card in pf.iter_cards(cfg.keyword, cfg.max_cards):
            job = pf.to_posting(card, cfg.keyword)
            if not job.job_id or job.job_id in seen:
                continue
            seen.add(job.job_id)
            cards.append(job)
    except Exception as e:
        result.errors.append(f"检索中断：{e}")
        say(f"    检索中断：{e}")
    result.stats["检索到的职位"] = len(cards)
    say(f"    去重后共 {len(cards)} 个职位")

    say("[2/4] 按地点/年限/薪资/公司规模预筛…")
    candidates: list[JobPosting] = []
    for job in cards:
        ok, reason = check(job, cfg, terms)
        if ok:
            candidates.append(job)
        else:
            result.rejected.append((job, reason))
    result.stats["预筛通过"] = len(candidates)
    result.stats["预筛淘汰"] = len(result.rejected)
    say(f"    通过 {len(candidates)} 个，淘汰 {len(result.rejected)} 个")

    limit = cfg.max_details or len(candidates)
    if stop_after_details:
        limit = min(limit, stop_after_details)
    todo = candidates[:limit]
    if len(candidates) > len(todo):
        say(f"    详情抓取上限 {len(todo)} 条（共 {len(candidates)} 条符合条件）")
        result.stats["因上限未抓详情"] = len(candidates) - len(todo)

    say(f"[3/4] 抓取职位详情（{len(todo)} 条，可命中缓存）…")
    pf.prepare_detail()
    fetched = cached = failed = skipped_now = 0
    for i, job in enumerate(todo, 1):
        ck = cache.get(pf.name, job.job_id) or {}
        was_cached = bool(ck.get("checked") or ck.get("description"))
        ok = False
        try:
            ok = pf.fill_detail(job, ck)
        except Exception as e:
            result.errors.append(f"{job.title}：{e}")
        if ok:
            if was_cached:
                cached += 1
            else:
                fetched += 1
                time.sleep(0.6)
            cache.put(pf.name, job.job_id, ck)
        else:
            # “无正文”也记入缓存，避免下次重复请求
            if job.detail_checked:
                cache.put(pf.name, job.job_id, ck)
                skipped_now += 1
            failed += 1
        if i % 10 == 0 or i == len(todo):
            say(f"    进度 {i}/{len(todo)}（新抓 {fetched}，缓存 {cached}，失败 {failed}）")
            cache.save()

    # 详情落盘后，用详情里的公司/地点/年限再做一次校验（更准确）
    passed: list[JobPosting] = []
    skipped = 0
    for job in todo:
        if not job.description:
            if job.detail_checked:
                skipped += 1
            continue
        ok, reason = check(job, cfg, terms)
        if ok:
            passed.append(job)
        else:
            result.rejected.append((job, f"详情校验：{reason}"))
    result.postings = passed

    say("[4/4] 汇总职位介绍并按公司取数…")
    for job in passed:
        # 需求内容 = 猎聘“职位介绍”栏全文（保留原始换行）
        text = job.full_description or job.description or ""
        job.requirement_items = requirement_rows(
            job, cfg.require_tokens, cfg.exclude_tokens, cfg.keyword)
        result.rows.append({
            "公司名称": job.company,
            "岗位名称": job.title,
            "工作地点": job.location,
            "公司规模": job.company_scale,
            "行业": job.industry,
            "经验要求": job.work_years,
            "学历要求": job.education,
            "薪资范围": job.salary,
            "需求内容": text,
            "命中关键词": job.extra.get("keyword", cfg.keyword),
            "职位链接": job.link,
            "平台": job.platform,
            "职位ID": job.job_id,
            "_拆分要求条数": len(job.requirement_items),
        })

    total_jobs = len(result.rows)
    result.rows = _cap_per_company(result.rows, cfg.limit_rows, cfg.max_per_company)
    result.stats["拆分出的要求总数"] = sum(r.get("_拆分要求条数", 0) for r in result.rows)

    for i, row in enumerate(result.rows, 1):
        row["序号"] = i
    result.stats.update({
        "命中岗位": len(passed),
        "新抓详情": fetched,
        "缓存命中": cached,
        "详情失败": failed,
        "详情无正文跳过": skipped,
        "符合条件岗位总数": total_jobs,
        "输出行数": len(result.rows),
        "覆盖公司数": len({r["公司名称"] for r in result.rows}),
        "每公司上限": cfg.max_per_company,
    })
    cache.save()
    say(f"    完成：{len(passed)} 个岗位，输出 {len(result.rows)} 行，"
        f"{result.stats['覆盖公司数']} 家公司")
    return result


def _cap_per_company(rows: list[dict[str, Any]], limit: int,
                     cap: int) -> list[dict[str, Any]]:
    """同一公司最多 cap 行；整体不超过 limit 行（按岗位顺序取）。"""
    out: list[dict[str, Any]] = []
    used: dict[str, int] = {}
    for r in rows:
        if limit and len(out) >= limit:
            break
        co = r["公司名称"]
        if cap and used.get(co, 0) >= cap:
            continue
        used[co] = used.get(co, 0) + 1
        out.append(r)
    return out
