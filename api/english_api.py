"""
每日英语 API 处理模块
用于获取随机英语单词，供日报模板使用
"""


import aiohttp

from astrbot.api import logger

from .base_api import BaseAPI


class EnglishAPI(BaseAPI):
    """每日英语 API 处理类（xxapi.cn）。"""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        super().__init__(session)
        self.url = "https://v2.xxapi.cn/api/randomenglishwords"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def get_word_async(self) -> dict | None:
        """获取一个随机英语单词卡片数据。

        Returns:
            标准化后的单词字典，失败返回 None。格式：
            {
                "word": "connexion",
                "phonetic": "kə'nekʃən",
                "translations": [{"pos": "n", "tran_cn": "..."}],
                "example_en": "...",
                "example_cn": "..."
            }
        """
        try:
            async with await self._request_with_retry(
                "GET",
                self.url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
            if not isinstance(payload, dict) or payload.get("code") != 200:
                return None
            data = payload.get("data") or {}
            if not isinstance(data, dict):
                return None
            word = str(data.get("word") or "").strip()
            if not word:
                return None

            translations = []
            for item in data.get("translations") or []:
                if not isinstance(item, dict):
                    continue
                tran_cn = str(item.get("tran_cn") or item.get("tran") or "").strip()
                if not tran_cn:
                    continue
                translations.append(
                    {
                        "pos": str(item.get("pos") or "").strip(),
                        "tran_cn": tran_cn,
                    }
                )

            example_en = ""
            example_cn = ""
            for item in data.get("sentences") or []:
                if not isinstance(item, dict):
                    continue
                example_en = str(item.get("s_content") or "").strip()
                example_cn = str(item.get("s_cn") or "").strip()
                if example_en:
                    break

            phonetic = str(
                data.get("usphone") or data.get("ukphone") or data.get("phonetic") or ""
            ).strip()
            return {
                "word": word,
                "phonetic": phonetic,
                "translations": translations,
                "example_en": example_en,
                "example_cn": example_cn,
            }
        except Exception as e:
            logger.warning(f"每日英语 API 请求失败: {e}")
            return None

    async def get_words_async(self, max_count: int = 1) -> list[dict]:
        """并发获取多个单词卡片。

        Args:
            max_count: 需要的单词数量

        Returns:
            单词卡片列表
        """
        import asyncio

        count = max(1, min(int(max_count or 1), 5))
        results = await asyncio.gather(
            *[self.get_word_async() for _ in range(count)],
            return_exceptions=True,
        )
        words = []
        for item in results:
            if isinstance(item, dict) and item.get("word"):
                words.append(item)
        return words
