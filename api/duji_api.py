"""
毒鸡汤 API 处理模块
用于获取每日毒鸡汤，供日报模板使用
"""
from typing import Optional

import aiohttp

from astrbot.api import logger

from .alapi_api import ALAPIClient
from .base_api import BaseAPI


class DujiAPI(BaseAPI):
    """毒鸡汤 API 处理类"""

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        token: str = "",
    ):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
            token: 可选的 ALAPI Token，留空则无鉴权（需在插件配置界面填写）
        """
        super().__init__(session)
        self.alapi = ALAPIClient(session=session, token=token)
        # 使用 tangdouz 免费 API
        self.url = "https://api.tangdouz.com/djt.php"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def get_duji_async(self) -> Optional[str]:
        """
        异步方式获取毒鸡汤数据（推荐用于 AstrBot）
        优先使用 tangdouz 免费 API，失败时回退到 ALAPI

        Returns:
            毒鸡汤文本，失败返回 None
        """
        try:
            async with await self._request_with_retry(
                "GET",
                self.url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                text = await response.text()

                if text and len(text) > 0:
                    text = text.strip()
                    logger.debug(f"成功获取毒鸡汤: {text[:50]}...")
                    return text
        except Exception as e:
            logger.warning(f"毒鸡汤 API 请求失败: {e}")

        # 回退到 ALAPI
        logger.info("免费毒鸡汤 API 失败，尝试使用 ALAPI 备用接口")
        text = await self.alapi.get_soul()
        if text:
            return text
        return None

    def parse_duji(self, api_data: Optional[str]) -> str:
        """
        解析毒鸡汤数据

        Args:
            api_data: API 返回的原始数据

        Returns:
            毒鸡汤文本
        """
        if not api_data:
            logger.warning("毒鸡汤 API 数据为空，使用默认数据")
            return self._get_default_duji()

        # API 返回的就是纯文本，直接返回
        return api_data.strip()

    def _get_default_duji(self) -> str:
        """
        返回默认的毒鸡汤（当 API 失败时使用）

        Returns:
            默认毒鸡汤
        """
        return "靠运气赚来的钱，最终都会凭实力赔走，直到财富与认知匹配为止。"

    async def get_today_duji_async(self) -> str:
        """
        异步方式获取今日毒鸡汤（推荐用于 AstrBot）

        Returns:
            毒鸡汤文本
        """
        api_data = await self.get_duji_async()
        return self.parse_duji(api_data)
