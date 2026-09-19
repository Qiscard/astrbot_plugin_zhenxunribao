"""
ALAPI (v3.alapi.cn) 统一客户端
封装本插件用到的全部 ALAPI 接口：
歇后语大全 / 每日一文 / 名人名言 / Hitokoto一言 / 节假日查询 /
历史上的今天 / 心灵毒鸡汤 / 每日早报
"""
import aiohttp
from datetime import date, datetime
from typing import Optional

from astrbot.api import logger

from .base_api import BaseAPI

# 不再内置公共 Token：用户需在插件配置界面手动填写 alapi_token。
# 未配置 Token 时仅能使用各数据源的免费通道，ALAPI 相关接口会降级/失败。
DEFAULT_TOKEN = ""
BASE_URL = "https://v3.alapi.cn"


class ALAPIClient(BaseAPI):
    """ALAPI 统一客户端，提供本插件全部需要的 ALAPI 接口方法。

    Args:
        session: 可选的 aiohttp.ClientSession，如果提供则复用。
        token: ALAPI Token，留空则无鉴权（需在插件配置界面填写）。
    """

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        token: str = "",
    ):
        super().__init__(session)
        self.token = (token or DEFAULT_TOKEN).strip()
        self.headers = {"Content-Type": "application/json"}

    async def _post(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """POST JSON 到 ALAPI 接口并返回解析后的顶层字典。

        Args:
            path: 接口路径，如 /api/soul。
            params: 业务参数（不含 token）。

        Returns:
            顶层响应字典，请求失败或 code != 200 返回 None。
        """
        body = {"token": self.token}
        if params:
            body.update(params)
        try:
            async with await self._request_with_retry(
                "POST",
                f"{BASE_URL}{path}",
                json=body,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if not isinstance(data, dict) or data.get("code") != 200:
                logger.warning(f"ALAPI {path} 返回异常: {data if isinstance(data, dict) else type(data)}")
                return None
            return data
        except Exception as e:
            logger.warning(f"ALAPI {path} 请求失败: {e}")
            return None

    async def get_xiehouyu(self) -> Optional[dict]:
        """获取一条随机歇后语。

        Returns:
            {"riddle": "谜面", "answer": "谜底"}，失败返回 None。
        """
        data = await self._post("/api/xhy/random")
        return data.get("data") if data else None

    async def get_daily_essay(self) -> Optional[dict]:
        """获取每日一文（随机美文）。

        Returns:
            {"title": ..., "content": ...}，失败返回 None。
        """
        data = await self._post("/api/mryw")
        return data.get("data") if data else None

    async def get_mingyan(self) -> Optional[dict]:
        """获取一条随机名人名言。

        Returns:
            {"content": ..., "author": ...}，失败返回 None。
        """
        data = await self._post("/api/mingyan")
        return data.get("data") if data else None

    async def get_hitokoto(self) -> Optional[dict]:
        """获取一条 Hitokoto 一言。

        Returns:
            {"hitokoto": ..., "from": ...}，失败返回 None。
        """
        data = await self._post("/api/hitokoto")
        return data.get("data") if data else None

    async def get_soul(self) -> Optional[str]:
        """获取一条心灵毒鸡汤。

        Returns:
            毒鸡汤文本，失败返回 None。
        """
        data = await self._post("/api/soul")
        if not data:
            return None
        dd = data.get("data") or {}
        return str(dd.get("content") or "").strip() or None

    async def get_holidays(self, year: Optional[int] = None) -> list:
        """获取指定年份的法定节假日安排。

        Args:
            year: 年份，None 使用当前年份。

        Returns:
            [{"name": "元旦", "date": "2026-01-01", "is_off_day": 1}, ...]，
            失败返回空列表。
        """
        params = {"year": str(year or datetime.now().year)}
        data = await self._post("/api/holiday", params)
        if not data:
            return []
        holiday_data = data.get("data")
        return holiday_data if isinstance(holiday_data, list) else []

    async def get_history(self, month: Optional[int] = None, day: Optional[int] = None) -> list:
        """获取历史上的今天事件列表。

        Args:
            month: 月份，None 使用当前月份。
            day: 日期，None 使用当前日期。

        Returns:
            [{"title": ..., "year": ..., "date": ..., "desc": ...}, ...]，
            失败返回空列表。
        """
        today = date.today()
        params = {
            "month": month or today.month,
            "day": day or today.day,
        }
        data = await self._post("/api/eventHistory", params)
        if not data:
            return []
        history_data = data.get("data")
        return history_data if isinstance(history_data, list) else []

    async def get_zaobao(self) -> Optional[dict]:
        """获取每日早报（60秒读懂世界）。

        Returns:
            {"date": ..., "news": [...], "weiyu": ...}，失败返回 None。
        """
        data = await self._post("/api/zaobao", {"format": "json"})
        return data.get("data") if data else None

    # ---- 便捷文本封装（底栏短句来源共用） ----

    async def get_quote_text(self, source: str) -> tuple:
        """按 ALAPI 接口名获取短句文本与署名。

        Args:
            source: ALAPI 短句接口名（hitokoto/soul/mingyan/xiehouyu）。

        Returns:
            (文本, 署名)，失败返回 ("", "")。
        """
        if source == "hitokoto":
            dd = await self.get_hitokoto()
            if dd:
                return str(dd.get("hitokoto", "") or "").strip(), str(
                    dd.get("from", "") or ""
                ).strip() or "佚名"
        elif source == "soul":
            text = await self.get_soul()
            if text:
                return text, ""
        elif source == "mingyan":
            dd = await self.get_mingyan()
            if dd:
                content = str(dd.get("content", "") or "").strip()
                author = str(dd.get("author", "") or "").strip()
                if content:
                    return content, author
        elif source == "xiehouyu":
            dd = await self.get_xiehouyu()
            if dd:
                riddle = str(dd.get("riddle", "") or "").strip()
                answer = str(dd.get("answer", "") or "").strip()
                if riddle:
                    return f"{riddle}——{answer}", ""
        return "", ""