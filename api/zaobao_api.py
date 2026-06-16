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

    def __init__(self, token: str, session: Optional[aiohttp.ClientSession] = None):
        """
        初始化

        Args:
            token: ALAPI token（主要 API，推荐配置）
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        super().__init__(session)
        self.token = token
        # 使用 ALAPI 60秒读懂世界（真正的每日新闻）
        self.url = f"https://v3.alapi.cn/api/zaobao?token={self.token}"
        # 备用 API（知乎日报）
        self.backup_url = "https://daily.zhihu.com/api/4/news/latest"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
            session = await self._get_session()
            params = {
                "token": self.token,
                "format": "json"
            }
            async with session.get(
                self.url,
                headers={"Content-Type": "application/json"},
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # ALAPI 返回格式: {"code": 200, "data": {"news": ["1、...", "2、..."], "weiyu": "..."}}
                if data and data.get('code') == 200 and data.get('data'):
                    logger.debug(f"成功从 ALAPI 60秒日报获取数据")
                    logger.debug(f"新闻条数: {len(data['data'].get('news', []))}")
                    logger.debug(f"微语: {data['data'].get('weiyu', 'N/A')}")
                    return data
                return None
        except Exception as e:
            logger.warning(f"ALAPI 60秒日报请求失败: {e}")
            return None

    async def _fetch_from_zhihu(self) -> Optional[Dict]:
        """从知乎日报 API 获取新闻（备用）"""
        try:
            session = await self._get_session()
            async with session.get(
                self.backup_url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10)
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
        """
        if not api_data:
            logger.warning("早报 API 数据为空，使用默认数据")
            return self._get_default_news()

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

            # 如果没有找到数据，返回默认值
            logger.warning("未找到新闻数据，使用默认数据")
            return self._get_default_news()

        except Exception as e:
            logger.error(f"解析早报数据时出错: {e}", exc_info=True)
            return self._get_default_news()
    
    def _get_default_news(self) -> List[str]:
        """
        返回默认的新闻数据（当 API 失败时使用）
        
        Returns:
            默认新闻列表
        """
        return [
            '全球科技峰会召开，AI发展成焦点',
            '国际油价波动引发市场关注',
            '新政策影响国际贸易',
            '环保议题持续升温',
            '体育赛事精彩纷呈'
        ]
    
    async def get_world_news_async(self, max_count: int = 5) -> List[str]:
        """
        异步方式获取世界新闻数据（推荐用于 AstrBot）
        
        Args:
            max_count: 最多返回几条新闻
            
        Returns:
            新闻列表
        """
        api_data = await self.get_zaobao_async()
        return self.parse_news(api_data, max_count)
