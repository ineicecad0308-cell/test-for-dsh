# -*- coding: utf-8 -*-
"""招聘平台适配层。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

try:  # 兼容“作为包导入”和“作为脚本目录内的顶层模块”两种方式
    from ..models import JobPosting
except ImportError:  # pragma: no cover
    from models import JobPosting


class PlatformError(RuntimeError):
    pass


class Platform(ABC):
    """平台适配器接口：搜索职位卡片 + 抓取职位详情。"""

    name = "base"
    label = "通用"

    @abstractmethod
    def iter_cards(self, keyword: str, max_cards: int = 0) -> Iterable[dict[str, Any]]:
        """按关键词翻页产出原始职位卡片（dict）。"""

    @abstractmethod
    def to_posting(self, card: dict[str, Any], keyword: str = "") -> JobPosting:
        """把原始卡片转成 JobPosting（不含详情正文）。"""

    @abstractmethod
    def fill_detail(self, job: JobPosting, ck: dict[str, Any] | None = None) -> bool:
        """抓取详情正文并写入 job.description；返回是否成功。"""

    def prepare_detail(self) -> None:
        """详情抓取前的准备（如刷新 Cookie），可选。"""


_REGISTRY: dict[str, type[Platform]] = {}


def register(cls: type[Platform]) -> type[Platform]:
    _REGISTRY[cls.name] = cls
    return cls


def available_platforms() -> dict[str, str]:
    _load_builtin()
    return {k: v.label for k, v in _REGISTRY.items()}


def get_platform(name: str) -> Platform:
    _load_builtin()
    key = (name or "liepin").strip().lower()
    if key not in _REGISTRY:
        raise PlatformError(
            f"暂不支持平台「{name}」，当前可用：{', '.join(available_platforms())}")
    return _REGISTRY[key]()


_LOADED = False


def _load_builtin() -> None:
    global _LOADED
    if _LOADED:
        return
    try:
        from . import liepin  # noqa: F401
    except ImportError:
        import liepin  # noqa: F401
    _LOADED = True
