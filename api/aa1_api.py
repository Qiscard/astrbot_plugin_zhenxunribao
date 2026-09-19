"""
aa1.cn 免费文案 API 处理模块
提供名人名言、舔狗日记、搞笑语录等短句数据，供日报模板使用
"""


import aiohttp

from astrbot.api import logger

from .base_api import BaseAPI


class AA1API(BaseAPI):
    """aa1.cn 免费文案 API 处理类"""

    # kind -> (接口地址, 文本字段名)
    _ENDPOINTS = {
        "mingyan": (
            "https://v.api.aa1.cn/api/api-wenan-mingrenmingyan/index.php?aa1=json",
            "mingrenmingyan",
        ),
        "tiangou": ("https://v.api.aa1.cn/api/tiangou/?aa1=json", "msg"),
        "gaoxiao": (
            "https://v.api.aa1.cn/api/api-wenan-gaoxiao/index.php?aa1=json",
            "gaoxiao",
        ),
    }

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        super().__init__(session)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def get_text_async(self, kind: str) -> str | None:
        """获取短句文本。

        Args:
            kind: 短句类型，见 _ENDPOINTS 的 key。

        Returns:
            短句文本，失败返回 None。
        """
        endpoint = self._ENDPOINTS.get(kind)
        if not endpoint:
            logger.warning(f"未知的 aa1.cn 短句类型: {kind}")
            return None
        url, key = endpoint
        try:
            async with await self._request_with_retry(
                "GET",
                url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            # 接口兼容 {"key": "..."} 与 [{"key": "..."}] 两种返回
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list) and data and isinstance(data[0], dict):
                text = str(data[0].get(key, "") or "").strip()
                if text:
                    return text
            return None
        except Exception as e:
            logger.warning(f"aa1.cn {kind} 请求失败: {e}")
            return None
