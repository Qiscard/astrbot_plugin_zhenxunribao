"""
早报 API 处理模块
用于获取60秒读懂世界新闻，供日报模板使用
"""
import aiohttp
from typing import List, Dict, Optional
import re

from astrbot.api import logger
from .base_api import BaseAPI

# 预编译正则表达式，避免循环内重复编译
NUMBER_PREFIX_PATTERN = re.compile(r'^\d+[\.、]\s*')


class ZaobaoAPI(BaseAPI):
    """早报 API 处理类"""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None, token: str = ""):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
            token: ALAPI Token，可从插件配置注入
        """
        super().__init__(session)
        # Token 来自插件配置（api_token），为空则跳过 ALAPI 主接口
        self.token = token or ""
        # 使用 ALAPI 60秒读懂世界（真正的每日新闻）
        self.url = "https://v3.alapi.cn/api/zaobao"
        # 备用 API（知乎日报）
        self.backup_url = "https://daily.zhihu.com/api/4/news/latest"
        self.headers = {
            "Content-Type": "application/json"
        }

    async def get_zaobao_async(self) -> Optional[Dict]:
        """
        异步方式获取早报数据（推荐用于 AstrBot）
        优先使用 ALAPI 60秒日报，失败时回退到知乎日报

        Returns:
            API 返回的原始数据，失败返回 None
        """
        # 优先尝试 ALAPI（如果配置了 Token）
        if self.token:
            result = await self._fetch_from_alapi()
            if result:
                return result
            logger.info("ALAPI 60秒日报失败，尝试使用知乎日报备用接口")

        # 回退到知乎日报
        result = await self._fetch_from_zhihu()
        if result:
            return result

        # 都失败了，返回 None
        return None

    async def _fetch_from_alapi(self) -> Optional[Dict]:
        """从 ALAPI 获取 60秒读懂世界新闻"""
        try:
            params = {
                "token": self.token,
                "format": "json"
            }
            # 注意：不要把带 token 的完整 URL 写入日志，避免凭据泄露
            logger.debug("[ZaobaoAPI] 请求 ALAPI 60秒日报接口")

            async with await self._request_with_retry(
                "GET",
                self.url,
                headers=self.headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                status = response.status
                logger.debug(f"[ZaobaoAPI] 响应状态码: {status}")

                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = None

                # ALAPI 返回格式: {"code": 200, "data": {"news": ["1、...", "2、..."], "weiyu": "..."}}
                if data and data.get('code') == 200 and data.get('data'):
                    logger.debug(f"成功从 ALAPI 60秒日报获取数据")
                    logger.debug(f"新闻条数: {len(data['data'].get('news', []))}")
                    return data
                else:
                    logger.warning(
                        f"[ZaobaoAPI] 返回异常: code={data.get('code') if data else 'N/A'}, "
                        f"success={data.get('success') if data else 'N/A'}, "
                        f"message={data.get('message') if data else 'N/A'}, "
                        f"keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}"
                    )
                return None
        except Exception as e:
            logger.warning(f"[ZaobaoAPI] 请求失败: {type(e).__name__}: {e}")
            return None

    async def _fetch_from_zhihu(self) -> Optional[Dict]:
        """从知乎日报 API 获取新闻（备用）"""
        try:
            async with await self._request_with_retry(
                "GET",
                self.backup_url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # 知乎日报返回格式: {"stories": [{"title": "..."}, ...]}
                if data and data.get('stories'):
                    # 转换为统一格式（兼容 ALAPI 格式）
                    news_list = [story.get('title', '') for story in data['stories'] if story.get('title')]
                    if news_list:
                        logger.debug(f"成功从知乎日报备用接口获取 {len(news_list)} 条新闻")
                        return {'data': {'news': news_list}}
                return None
        except Exception as e:
            logger.warning(f"知乎日报备用接口请求失败: {e}")
            return None
    
    def parse_news(self, api_data: Optional[Dict], max_count: int = 5) -> List[str]:
        """
        解析早报数据，提取新闻列表

        Args:
            api_data: API 返回的原始数据
            max_count: 最多返回几条新闻

        Returns:
            新闻列表，格式：['新闻1', '新闻2', ...]
            数据不可用时返回空列表（由模板显示占位文案）
        """
        if not api_data:
            logger.warning("早报 API 数据为空")
            return []

        try:
            logger.debug(f"解析早报数据，原始数据结构: {list(api_data.keys()) if isinstance(api_data, dict) else 'N/A'}")

            # 提取 data.news 字段
            if 'data' in api_data and isinstance(api_data['data'], dict):
                news_data = api_data['data'].get('news', [])

                logger.debug(f"提取到的新闻数据类型: {type(news_data)}, 长度: {len(news_data) if isinstance(news_data, list) else 'N/A'}")

                if isinstance(news_data, list):
                    news_list = []
                    for item in news_data:
                        # 达到最大数量就停止
                        if len(news_list) >= max_count:
                            break

                        if isinstance(item, str):
                            # 移除开头的编号（如 "1."、"1、"等）
                            cleaned = item.strip()
                            # 使用预编译的正则表达式
                            cleaned = NUMBER_PREFIX_PATTERN.sub('', cleaned)
                            if cleaned:
                                news_list.append(cleaned)

                    if len(news_list) > 0:
                        logger.debug(f"成功解析 {len(news_list)} 条新闻，样本: {news_list[0][:30]}...")
                        return news_list

            # 如果没有找到数据，返回空列表
            logger.warning("未找到新闻数据")
            return []

        except Exception as e:
            logger.error(f"解析早报数据时出错: {e}", exc_info=True)
            return []

    async def get_world_news_async(self, max_count: int = 5) -> List[str]:
        """
        异步方式获取世界新闻数据（推荐用于 AstrBot）

        Args:
            max_count: 最多返回几条新闻

        Returns:
            新闻列表，数据不可用时返回空列表
        """
        api_data = await self.get_zaobao_async()
        return self.parse_news(api_data, max_count)
