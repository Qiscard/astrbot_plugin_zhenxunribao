"""
历史上的今天 API 处理模块
用于获取历史上今天发生的事件，供日报模板使用
"""
import aiohttp
from typing import List, Optional, Dict, Any
import re

from astrbot.api import logger
from .base_api import BaseAPI


class HistoryAPI(BaseAPI):
    """历史上的今天 API 处理类"""

    def __init__(self, token: str = "", session: Optional[aiohttp.ClientSession] = None):
        """
        初始化

        Args:
            token: ALAPI Token
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        super().__init__(session)
        self.token = token
        self.url = "https://v3.alapi.cn/api/eventHistory"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def get_history_async(self) -> Optional[list]:
        """
        异步方式获取历史上的今天数据（推荐用于 AstrBot）

        Returns:
            API 返回的事件列表，失败返回 None
        """
        if not self.token:
            logger.warning("历史上的今天 API 未配置 Token")
            return None

        try:
            session = await self._get_session()
            params = {"token": self.token}
            async with session.get(
                self.url,
                params=params,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if data.get("code") == 200 and data.get("data"):
                    logger.debug(f"成功获取历史上的今天数据")
                    return data.get("data")
                else:
                    logger.warning(f"历史上的今天 API 返回异常: {data.get('msg', '未知错误')}")
                    return None
        except Exception as e:
            logger.warning(f"历史上的今天 API 请求失败: {e}")
            return None

    def parse_history(self, api_data: Optional[list], max_count: int = 5) -> List[Dict[str, str]]:
        """
        解析历史上的今天数据

        Args:
            api_data: API 返回的事件列表
            max_count: 最多返回几条历史事件

        Returns:
            历史事件字典列表，格式：[{'year': '1923', 'title': '法国国王罗贝尔一世逝世'}, ...]
        """
        if not api_data:
            logger.warning("历史上的今天 API 数据为空，使用默认数据")
            return self._get_default_history()

        try:
            if not isinstance(api_data, list):
                logger.warning(f"历史上的今天 API 返回格式异常: {type(api_data)}")
                return self._get_default_history()

            history_list = []
            for event in api_data[:max_count]:
                if isinstance(event, dict):
                    year = event.get("year", "")
                    title = event.get("title", "")
                    if year and title:
                        history_list.append({
                            "year": str(year),
                            "title": title
                        })

            logger.debug(f"成功解析 {len(history_list)} 条历史事件")

            if len(history_list) == 0:
                logger.warning("未解析到历史事件数据，使用默认数据")
                return self._get_default_history()

            return history_list

        except Exception as e:
            logger.error(f"解析历史上的今天数据时出错: {e}", exc_info=True)
            return self._get_default_history()

    def _get_default_history(self) -> List[Dict[str, str]]:
        """
        返回默认的历史事件数据（当 API 失败时使用）

        Returns:
            默认历史事件字典列表
        """
        return [
            {'year': '1215', 'title': '英格兰国王约翰签署大宪章'},
            {'year': '1667', 'title': '人类历史上首次输血治疗在法国进行'},
            {'year': '1843', 'title': '挪威作曲家葛利格出生'},
            {'year': '1991', 'title': '菲律宾皮纳图博火山喷发'},
            {'year': '2002', 'title': '现代跆拳道创始人崔泓熙逝世'}
        ]

    async def get_today_history_async(self, max_count: int = 5) -> List[Dict[str, str]]:
        """
        异步方式获取历史上的今天数据（推荐用于 AstrBot）

        Args:
            max_count: 最多返回几条历史事件

        Returns:
            格式化的历史事件字典列表，格式：[{'year': '1923', 'title': '法国国王罗贝尔一世逝世'}, ...]
        """
        api_data = await self.get_history_async()
        return self.parse_history(api_data, max_count)
