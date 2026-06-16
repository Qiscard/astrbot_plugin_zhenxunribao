"""
BGM (Bangumi) API 处理模块
用于获取今日新番数据，供日报模板使用
"""
import aiohttp
from datetime import datetime
from typing import List, Dict, Optional

from astrbot.api import logger
from .base_api import BaseAPI


class BGMAPI(BaseAPI):
    """BGM API 处理类"""
    
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        super().__init__(session)
        # 主 API：国内可访问的 BGM 反代（anibt.net）
        self.url = "https://bgmapi.anibt.net/calendar"
        # 备用 API：官方 API（可能无法访问）
        self.backup_url = "https://api.bgm.tv/calendar"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    async def get_calendar_async(self) -> Optional[List]:
        """
        异步方式获取 BGM 日历数据（推荐用于 AstrBot）
        优先使用反代 API，失败时回退到官方 API

        Returns:
            API 返回的原始数据，失败返回 None
        """
        # 尝试反代 API
        result = await self._fetch_from_proxy()
        if result:
            return result

        # 回退到官方 API
        logger.info("BGM 反代 API 失败，尝试使用官方 API")
        result = await self._fetch_from_official()
        if result:
            return result

        # 都失败了，返回 None
        return None

    async def _fetch_from_proxy(self) -> Optional[List]:
        """从反代 API 获取数据"""
        try:
            session = await self._get_session()
            async with session.get(
                self.url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                response.raise_for_status()
                data = await response.json()
                logger.debug(f"成功从 BGM 反代 API 获取数据")
                return data
        except Exception as e:
            logger.warning(f"BGM 反代 API 请求失败: {e}")
            return None

    async def _fetch_from_official(self) -> Optional[List]:
        """从官方 API 获取数据（备用）"""
        try:
            session = await self._get_session()
            async with session.get(
                self.backup_url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                response.raise_for_status()
                data = await response.json()
                logger.debug(f"成功从 BGM 官方 API 获取数据")
                return data
        except Exception as e:
            logger.warning(f"BGM 官方 API 请求失败: {e}")
            return None
    
    def parse_today_anime(self, api_data: Optional[List], max_count: int = 4) -> List[Dict]:
        """
        解析 BGM 数据，提取今日新番

        Args:
            api_data: API 返回的原始数据
            max_count: 最多返回几个新番

        Returns:
            格式化的新番列表，格式：
            [
                {
                    'title': '动画名称',
                    'image': '图片URL'
                },
                ...
            ]
        """
        if not api_data or not isinstance(api_data, list):
            logger.warning("BGM API 数据为空或格式错误，使用默认数据")
            return self._get_default_anime()

        try:
            # 获取今天是星期几 (0=周一, 6=周日)
            # BGM API 使用 1-7 表示周一到周日
            today_weekday = datetime.now().weekday() + 1

            logger.debug(f"今天是星期 {today_weekday}，查找对应的新番数据")

            anime_list = []

            # 查找今天的数据
            for day_data in api_data:
                if not isinstance(day_data, dict):
                    continue

                weekday_info = day_data.get('weekday', {})
                weekday_id = weekday_info.get('id')

                # 找到今天的数据
                if weekday_id == today_weekday:
                    items = day_data.get('items', [])

                    logger.debug(f"找到今天的新番，共 {len(items)} 部")

                    for item in items:
                        if not isinstance(item, dict):
                            continue

                        # 优先使用中文名，没有则使用日文名
                        name_cn = item.get('name_cn', '')
                        name_jp = item.get('name', '')
                        title = name_cn if name_cn else name_jp

                        # 获取图片（使用 medium 尺寸）
                        images = item.get('images', {})
                        image_url = images.get('medium', '') or images.get('common', '')

                        # 确保图片 URL 使用 HTTPS（避免混合内容问题）
                        if image_url and image_url.startswith('http://'):
                            image_url = image_url.replace('http://', 'https://', 1)

                        if title and image_url:
                            logger.debug(f"新番: {title[:20]}... - 图片: {image_url[:50]}...")
                            anime_list.append({
                                'title': title,
                                'image': image_url
                            })

                        # 达到最大数量就停止
                        if len(anime_list) >= max_count:
                            break

                    break

            # 如果没有找到数据，返回默认值
            if len(anime_list) == 0:
                logger.warning("未找到今日新番数据，使用默认数据")
                return self._get_default_anime()

            logger.debug(f"成功解析 {len(anime_list)} 部新番")
            return anime_list

        except Exception as e:
            logger.error(f"解析 BGM 数据时出错: {e}", exc_info=True)
            return self._get_default_anime()
    
    def _get_default_anime(self) -> List[Dict]:
        """
        返回默认的新番数据（当 API 失败时使用）
        
        Returns:
            默认新番列表
        """
        return [
            {'title': '葬送的芙莉莲 第二季', 'image': './res/image/anime1.jpg'},
            {'title': '咒术回战 涉谷事变篇', 'image': './res/image/anime2.jpg'},
            {'title': '间谍过家家 第三季', 'image': './res/image/anime3.jpg'},
            {'title': '鬼灭之刃 柱训练篇', 'image': './res/image/anime4.jpg'}
        ]
    
    async def get_today_anime_async(self, max_count: int = 4) -> List[Dict]:
        """
        异步方式获取今日新番数据（推荐用于 AstrBot）
        
        Args:
            max_count: 最多返回几个新番
            
        Returns:
            格式化的今日新番列表
        """
        api_data = await self.get_calendar_async()
        return self.parse_today_anime(api_data, max_count)
