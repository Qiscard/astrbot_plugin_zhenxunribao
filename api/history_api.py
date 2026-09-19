"""
历史上的今天 API 处理模块
用于获取历史上今天发生的事件，供日报模板使用
"""
from typing import Optional

import aiohttp

from astrbot.api import logger

from .alapi_api import ALAPIClient
from .base_api import BaseAPI


class HistoryAPI(BaseAPI):
    """历史上的今天 API 处理类"""

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        token: str | None = None,
    ):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
            token: 可选的 ALAPI Token，留空则无鉴权（需在插件配置界面填写）
        """
        super().__init__(session)
        self.alapi = ALAPIClient(session=session, token=token or "")
        # aa1.cn 免费接口（无需 Key，作为主通道）
        self.aa1_url = "https://zj.v.api.aa1.cn/api/bk/"
        self.headers = {"User-Agent": "Mozilla/5.0"}

    async def _fetch_from_aa1(self, max_count: int) -> list[dict[str, str]] | None:
        """从 aa1.cn 免费接口获取历史上的今天。

        Args:
            max_count: 最多返回几条历史事件

        Returns:
            格式化的历史事件列表（无年份信息），失败返回 None
        """
        try:
            async with await self._request_with_retry(
                "GET",
                self.aa1_url,
                params={"num": max_count, "type": "json"},
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if isinstance(data, dict) and data.get("code") == 200:
                items = [
                    str(x).strip()
                    for x in (data.get("content") or [])
                    if str(x).strip()
                ]
                if items:
                    # aa1.cn 不返回年份，year 置空由模板决定是否展示
                    return [{"year": "", "title": t} for t in items[:max_count]]
            return None
        except Exception as e:
            logger.warning(f"aa1.cn 历史上的今天请求失败: {e}")
            return None

    def parse_history(
        self, api_data: list | None, max_count: int = 5
    ) -> list[dict[str, str]]:
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
                    title = event.get("title", "") or event.get("desc", "")
                    if title:
                        history_list.append({"year": str(year or ""), "title": title})

            logger.debug(f"成功解析 {len(history_list)} 条历史事件")

            if len(history_list) == 0:
                logger.warning("未解析到历史事件数据，使用默认数据")
                return self._get_default_history()

            return history_list

        except Exception as e:
            logger.error(f"解析历史上的今天数据时出错: {e}", exc_info=True)
            return self._get_default_history()

    def _get_default_history(self) -> list[dict[str, str]]:
        """
        返回默认的历史事件数据（当 API 失败时使用）

        Returns:
            默认历史事件字典列表
        """
        return [
            {"year": "1215", "title": "英格兰国王约翰签署大宪章"},
            {"year": "1667", "title": "人类历史上首次输血治疗在法国进行"},
            {"year": "1843", "title": "挪威作曲家葛利格出生"},
            {"year": "1991", "title": "菲律宾皮纳图博火山喷发"},
            {"year": "2002", "title": "现代跆拳道创始人崔泓熙逝世"},
        ]

    async def get_today_history_async(self, max_count: int = 5) -> list[dict[str, str]]:
        """
        异步方式获取历史上的今天数据（推荐用于 AstrBot）

        Args:
            max_count: 最多返回几条历史事件

        Returns:
            格式化的历史事件字典列表，格式：[{'year': '1923', 'title': '...'}, ...]
        """
        # 主通道：aa1.cn 免费接口（不消耗 ALAPI 额度）
        events = await self._fetch_from_aa1(max_count)
        if events:
            return events
        # 备用：ALAPI
        api_data = await self.alapi.get_history()
        return self.parse_history(api_data, max_count)