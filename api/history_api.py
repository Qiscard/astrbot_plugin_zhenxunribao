"""
历史上的今天 API 处理模块
用于获取历史上今天发生的事件，供日报模板使用
"""
import aiohttp
from typing import List, Optional, Dict

from astrbot.api import logger
from .base_api import BaseAPI


class HistoryAPI(BaseAPI):
    """历史上的今天 API 处理类"""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None, token: str = ""):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
            token: ALAPI Token，可从插件配置注入
        """
        super().__init__(session)
        # Token 来自插件配置（api_token），为空则无法请求该接口
        self.token = token or ""
        self.url = "https://v3.alapi.cn/api/eventHistory"
        self.headers = {
            "Content-Type": "application/json"
        }

    async def get_history_async(self) -> Optional[list]:
        """
        异步方式获取历史上的今天数据（推荐用于 AstrBot）

        Returns:
            API 返回的事件列表，失败返回 None
        """
        if not self.token:
            logger.warning("历史上的今天 API 未配置 Token（可在插件配置中填写 api_token）")
            return None

        try:
            params = {"token": self.token}
            # 注意：不要把带 token 的完整 URL 写入日志，避免凭据泄露
            logger.debug("[HistoryAPI] 请求 ALAPI 历史上的今天接口")

            async with await self._request_with_retry(
                "GET",
                self.url,
                params=params,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                status = response.status
                logger.debug(f"[HistoryAPI] 响应状态码: {status}")

                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = None

                if data and data.get("code") == 200 and data.get("data"):
                    logger.debug(f"成功获取历史上的今天数据")
                    return data.get("data")
                else:
                    logger.warning(
                        f"[HistoryAPI] 返回异常: code={data.get('code') if data else 'N/A'}, "
                        f"success={data.get('success') if data else 'N/A'}, "
                        f"message={data.get('message') if data else 'N/A'}, "
                        f"keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}"
                    )
                    return None
        except Exception as e:
            logger.warning(f"[HistoryAPI] 请求失败: {type(e).__name__}: {e}")
            return None

    def parse_history(self, api_data: Optional[list], max_count: int = 5) -> List[Dict[str, str]]:
        """
        解析历史上的今天数据

        Args:
            api_data: API 返回的事件列表
            max_count: 最多返回几条历史事件

        Returns:
            历史事件字典列表，格式：[{'year': '1923', 'title': '法国国王罗贝尔一世逝世'}, ...]
            数据不可用时返回空列表（由模板显示占位文案）
        """
        if not api_data:
            logger.warning("历史上的今天 API 数据为空")
            return []

        try:
            if not isinstance(api_data, list):
                logger.warning(f"历史上的今天 API 返回格式异常: {type(api_data)}")
                return []

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

            return history_list

        except Exception as e:
            logger.error(f"解析历史上的今天数据时出错: {e}", exc_info=True)
            return []

    async def get_today_history_async(self, max_count: int = 5) -> List[Dict[str, str]]:
        """
        异步方式获取历史上的今天数据（推荐用于 AstrBot）

        Args:
            max_count: 最多返回几条历史事件

        Returns:
            格式化的历史事件字典列表，数据不可用时返回空列表
        """
        api_data = await self.get_history_async()
        return self.parse_history(api_data, max_count)
