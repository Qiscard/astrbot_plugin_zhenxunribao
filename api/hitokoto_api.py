"""
今日一言 API 处理模块
用于获取今日一言数据
"""
import aiohttp
from typing import Optional, Dict

from astrbot.api import logger
from .base_api import BaseAPI


class HitokotoAPI(BaseAPI):
    """今日一言 API 处理类"""

    def __init__(self, token: str, session: Optional[aiohttp.ClientSession] = None):
        """
        初始化

        Args:
            token: API token (已弃用，保留参数兼容性)
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        super().__init__(session)
        # 使用官方免费 API，无需 Token
        self.url = "https://v1.hitokoto.cn/"
        # 备用 API（ALAPI，仅在官方 API 失败时使用）
        self.backup_url = "https://v3.alapi.cn/api/hitokoto"
        self.token = token
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def _get_default_hitokoto(self) -> Dict[str, str]:
        return {
            'hitokoto': '生活就像骑自行车，想保持平衡就得往前走。',
            'from': '未知'
        }

    async def get_hitokoto_async(self) -> Dict[str, str]:
        """
        异步获取今日一言（用于AstrBot）
        优先使用官方免费 API，失败时回退到 ALAPI

        Returns:
            Dict[str, str]: 包含 'hitokoto' 和 'from' 的字典
        """
        # 尝试官方 API
        result = await self._fetch_from_official()
        if result:
            return result

        # 回退到 ALAPI（如果配置了 Token）
        if self.token:
            logger.info("官方一言 API 失败，尝试使用 ALAPI 备用接口")
            result = await self._fetch_from_alapi()
            if result:
                return result

        # 都失败了，返回默认值
        return self._get_default_hitokoto()

    async def _fetch_from_official(self) -> Optional[Dict[str, str]]:
        """从官方 API 获取一言"""
        try:
            session = await self._get_session()
            async with session.get(
                self.url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # 官方 API 返回格式: {"hitokoto": "...", "from": "...", "from_who": "..."}
                hitokoto_text = data.get("hitokoto", "")
                from_value = data.get("from", "") or data.get("from_who", "")

                # 如果为空或"网络"则使用"佚名"
                if not from_value or (isinstance(from_value, str) and (from_value.strip() == "" or from_value.strip() == "网络")):
                    from_value = "佚名"
                else:
                    from_value = str(from_value).strip()

                if hitokoto_text:
                    logger.debug(f"成功从官方 API 获取一言: {hitokoto_text[:20]}...")
                    return {
                        'hitokoto': hitokoto_text,
                        'from': from_value
                    }
                return None
        except Exception as e:
            logger.warning(f"官方一言 API 请求失败: {e}")
            return None

    async def _fetch_from_alapi(self) -> Optional[Dict[str, str]]:
        """从 ALAPI 备用接口获取一言"""
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

                # 检查返回状态
                code = data.get("code")
                success = data.get("success", False)

                if (code == 200 or success) and data.get("data"):
                    hitokoto_data = data["data"]
                    from_value = hitokoto_data.get("from") or hitokoto_data.get("from_who") or ""

                    if not from_value or (isinstance(from_value, str) and (from_value.strip() == "" or from_value.strip() == "网络")):
                        from_value = "佚名"
                    else:
                        from_value = str(from_value).strip()

                    hitokoto_text = hitokoto_data.get("hitokoto", "")

                    if hitokoto_text:
                        logger.debug(f"成功从 ALAPI 备用接口获取一言")
                        return {
                            'hitokoto': hitokoto_text,
                            'from': from_value
                        }
                else:
                    logger.warning(f"ALAPI 返回异常: code={code}, success={success}")
                return None
        except Exception as e:
            logger.warning(f"ALAPI 备用接口请求失败: {e}")
            return None
