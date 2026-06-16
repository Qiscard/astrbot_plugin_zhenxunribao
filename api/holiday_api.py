"""
节假日 API 处理模块
用于获取和解析节假日数据，供日报模板使用
"""
import aiohttp
import json
from datetime import datetime, date
from typing import List, Dict, Optional

from astrbot.api import logger
from .base_api import BaseAPI


class HolidayAPI(BaseAPI):
    """节假日 API 处理类"""

    def __init__(self, token: str, session: Optional[aiohttp.ClientSession] = None, year: Optional[int] = None):
        """
        初始化

        Args:
            token: ALAPI token（备用 API，可选）
            session: 可选的 aiohttp.ClientSession，如果提供则复用
            year: 指定年份，None 则使用当前年份
        """
        super().__init__(session)
        self.token = token
        # 使用 tangdouz 免费节日倒计时 API
        self.url = "https://api.tangdouz.com/nlholiday.php"
        # 备用 API（ALAPI）
        self.backup_url = "https://v3.alapi.cn/api/holiday"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.year = year or datetime.now().year

    async def get_holidays_async(self) -> Optional[Dict]:
        """
        异步方式获取节假日数据（推荐用于 AstrBot）
        优先使用 tangdouz 免费 API，失败时回退到 ALAPI

        Returns:
            API 返回的原始数据，失败返回 None
        """
        # 尝试 tangdouz 免费 API
        result = await self._fetch_from_tangdouz()
        if result:
            return result

        # 回退到 ALAPI（如果配置了 Token）
        if self.token:
            logger.info("免费节假日 API 失败，尝试使用 ALAPI 备用接口")
            result = await self._fetch_from_alapi()
            if result:
                return result

        # 都失败了，返回 None
        return None

    async def _fetch_from_tangdouz(self) -> Optional[Dict]:
        """从 tangdouz 免费 API 获取节假日倒计时"""
        try:
            session = await self._get_session()
            params = {"return": "json"}
            async with session.get(
                self.url,
                headers=self.headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                # 使用 text() 然后手动解析 JSON，避免 MIME 类型检查问题
                text = await response.text()
                data = json.loads(text)

                # tangdouz API 返回格式: [{"holiday":"端午节","days":3}, ...]
                if data and isinstance(data, list) and len(data) > 0:
                    logger.debug(f"成功从 tangdouz 免费 API 获取 {len(data)} 条节假日数据")
                    logger.debug(f"节假日数据样本: {data[:3]}")
                    # 转换为统一格式（兼容后续解析）
                    holidays_list = []
                    for item in data:
                        if isinstance(item, dict) and item.get('holiday') and 'days' in item:
                            holidays_list.append({
                                'name': item['holiday'],
                                'days_left': item['days']
                            })

                    if holidays_list:
                        return {'data': holidays_list}
                return None
        except Exception as e:
            logger.warning(f"tangdouz 节假日 API 请求失败: {e}")
            return None

    async def _fetch_from_alapi(self) -> Optional[Dict]:
        """从 ALAPI 备用接口获取节假日"""
        try:
            session = await self._get_session()
            params = {"token": self.token}
            async with session.get(
                self.backup_url,
                headers={"Content-Type": "application/json"},
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if data and data.get('data'):
                    logger.debug(f"成功从 ALAPI 备用接口获取节假日数据")
                    return data
                return None
        except Exception as e:
            logger.warning(f"ALAPI 备用接口请求失败: {e}")
            return None
    
    def parse_holidays(self, api_data: Optional[Dict], max_count: int = 3) -> List[Dict]:
        """
        解析节假日数据，转换为模板需要的格式

        Args:
            api_data: API 返回的原始数据
            max_count: 最多返回几个节假日

        Returns:
            格式化的节假日列表，格式：
            [
                {'name': '春节', 'days_left': 25},
                {'name': '清明节', 'days_left': 78},
                ...
            ]
        """
        if not api_data:
            logger.warning("节假日 API 数据为空，使用默认数据")
            return self._get_default_holidays()

        try:
            # 提取数据
            holidays_data = api_data.get('data', [])
            logger.debug(f"解析节假日数据，原始数据长度: {len(holidays_data) if isinstance(holidays_data, list) else 'N/A'}")

            if not isinstance(holidays_data, list) or len(holidays_data) == 0:
                logger.warning("节假日数据列表为空，使用默认数据")
                return self._get_default_holidays()

            # tangdouz API 已经处理好格式，直接使用
            # 数据格式: [{'name': '端午节', 'days_left': 3}, ...]
            result = holidays_data[:max_count]

            logger.debug(f"解析后的节假日: {result}")

            # 如果没有数据，返回默认值
            if len(result) == 0:
                logger.warning("未找到节假日数据，使用默认数据")
                return self._get_default_holidays()

            return result

        except Exception as e:
            logger.error(f"解析节假日数据时出错: {e}", exc_info=True)
            return self._get_default_holidays()
    
    def _get_default_holidays(self) -> List[Dict]:
        """
        返回默认的节假日数据（当 API 失败时使用）
        
        Returns:
            默认节假日列表
        """
        return [
            {'name': '周末', 'days_left': 3},
            {'name': '春节', 'days_left': 25},
            {'name': '清明节', 'days_left': 78}
        ]
    
    async def get_moyu_list_async(self, max_count: int = 3) -> List[Dict]:
        """
        异步方式获取摸鱼日历数据（推荐用于 AstrBot）
        
        Args:
            max_count: 最多返回几个节假日
            
        Returns:
            格式化的摸鱼日历列表
        """
        api_data = await self.get_holidays_async()
        return self.parse_holidays(api_data, max_count)
