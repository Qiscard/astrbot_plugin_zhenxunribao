"""
MiloraAPI (api.milorapart.top) 客户端
封装 AI早报 (aidaily)。
鉴权来自插件配置；业务参数由日报模块按调用传入。
"""
import re
from typing import Optional

import aiohttp

from astrbot.api import logger

from .base_api import BaseAPI

BASE_URL = "https://api.milorapart.top/apis"

# 从 md/txt 正文中提取条目行
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[\.、\)）])\s+(.+)$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_EMPH_RE = re.compile(r"[*_`]+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_ARROW_RE = re.compile(r"\s*[↗→]\s*")
_TAG_RE = re.compile(r"\s*`?#\d+`?\s*")
_TITLE_RE = re.compile(r"^(?:AI\s*早报|视频版)\b", re.I)


class MiloraAPI(BaseAPI):
    """Milora 接口客户端。

    Args:
        session: 可选的 aiohttp.ClientSession，如果提供则复用。
        api_key: Milora API Key，通过查询参数 key 传递；免费接口可留空。
    """

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        api_key: str = "",
        aidaily_type: str = "txt",
        aidaily_date: str = "",
    ):
        super().__init__(session)
        self.api_key = (api_key or "").strip()
        self.aidaily_type = (aidaily_type or "txt").strip().lower() or "txt"
        self.aidaily_date = (aidaily_date or "").strip()

    async def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET Milora /apis 接口并返回 JSON 字典。

        Args:
            path: 接口路径，如 /aidaily。
            params: 业务查询参数（不含 key）。

        Returns:
            顶层响应字典，失败返回 None。
        """
        query = dict(params or {})
        if self.api_key:
            query["key"] = self.api_key
        try:
            async with await self._request_with_retry(
                "GET",
                f"{BASE_URL}{path}",
                params=query,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if not isinstance(data, dict):
                logger.warning(f"Milora {path} 返回非对象: {type(data)}")
                return None
            code = data.get("code")
            if code not in (200, "200", None):
                logger.warning(f"Milora {path} 返回异常: {data}")
                return None
            return data
        except Exception as e:
            logger.warning(f"Milora {path} 请求失败: {e}")
            return None

    @staticmethod
    def _clean_line(text: str) -> str:
        """清理 Markdown 标记，得到适合日报展示的单行文本。"""
        s = _MD_LINK_RE.sub(r"\1", text)
        s = _TAG_RE.sub(" ", s)
        s = _ARROW_RE.sub(" ", s)
        s = _MD_EMPH_RE.sub("", s)
        return re.sub(r"\s+", " ", s).strip()

    @classmethod
    def _parse_content_items(cls, content: str, max_count: int = 12) -> list[str]:
        """从 AI早报 md/txt 正文解析条目列表。

        Args:
            content: 接口返回的 content 字段。
            max_count: 最多保留条数。

        Returns:
            清洗后的条目文本列表。
        """
        if not content:
            return []
        items: list[str] = []
        section_names = {
            "概览",
            "要闻",
            "模型发布",
            "开发生态",
            "产品应用",
            "行业动态",
            "投融资",
            "安全与风险",
            "其他",
        }
        for raw in str(content).splitlines():
            line = raw.strip()
            if not line:
                continue
            if _HEADING_RE.match(line) or line.startswith("**视频") or _TITLE_RE.match(line):
                continue
            plain_head = cls._clean_line(_HEADING_RE.sub("", line))
            if plain_head in section_names:
                continue
            m = _BULLET_RE.match(line)
            if m:
                cleaned = cls._clean_line(m.group(1))
            else:
                # 非列表行：仅保留足够长的正文，过滤章节名
                cleaned = cls._clean_line(line)
                if cleaned in section_names or len(cleaned) < 16:
                    continue
            if cleaned and cleaned not in items:
                items.append(cleaned)
            if len(items) >= max_count:
                break
        return items

    async def get_aidaily(
        self, max_count: int = 12, rtype: str = "", date: str = ""
    ) -> Optional[dict]:
        """获取 AI早报展示数据。

        Args:
            max_count: 文本模式下最多展示条数。
            rtype: 返回格式 image/txt/md，空则用实例默认。
            date: 日期 YYYY-MM-DD，空则用实例默认（再空表示当天）。

        Returns:
            {
              "date": "YYYY-MM-DD",
              "type": "txt"|"md"|"image",
              "items": [...],          # 文本模式
              "image_url": "...",      # image 模式
              "content": "..."         # 原始正文（可选）
            }，失败返回 None。
        """
        rtype = (rtype or self.aidaily_type).strip().lower()
        rtype = rtype if rtype in ("image", "txt", "md") else "txt"
        date = (date or self.aidaily_date).strip()
        params: dict = {"type": rtype}
        if date:
            params["date"] = date
        data = await self._get("/aidaily", params)
        if not data:
            return None
        date_str = str(data.get("date") or date or "").strip()
        if rtype == "image":
            url = str(data.get("url") or "").strip()
            if not url:
                return None
            return {"date": date_str, "type": "image", "image_url": url, "items": []}
        content = str(data.get("content") or "").strip()
        items = self._parse_content_items(content, max_count=max_count)
        if not items and content:
            # 解析失败时退回截断原文
            plain = self._clean_line(content.replace("\n", " "))
            items = [plain[:180] + ("…" if len(plain) > 180 else "")] if plain else []
        if not items:
            return None
        return {
            "date": date_str,
            "type": rtype,
            "items": items,
            "content": content,
            "image_url": "",
        }
