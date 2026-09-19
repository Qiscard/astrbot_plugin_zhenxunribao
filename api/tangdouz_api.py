"""
糖豆子（tangdouz.com）API 处理模块
提供实时汇率、小黑盒游戏、随机谜语、随机一言等免费接口，供日报模板使用
"""

from typing import Optional

import aiohttp

from astrbot.api import logger

from .base_api import BaseAPI


class TangdouzAPI(BaseAPI):
    """糖豆子免费 API 处理类。

    Args:
        session: 可选的 aiohttp.ClientSession，如果提供则复用。
    """

    BASE = "https://api.tangdouz.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        super().__init__(session)

    async def _get_json(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET 并解析 JSON。

        Args:
            path: 接口路径，如 /a/huilv/huilv.php。
            params: 查询参数。

        Returns:
            顶层 JSON 字典，失败返回 None。
        """
        try:
            async with await self._request_with_retry(
                "GET",
                f"{self.BASE}{path}",
                params=params,
                headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except Exception as e:
            logger.warning(f"糖豆子接口 {path} 请求失败: {e}")
            return None

    # ---------- 实时汇率 ----------

    async def get_exchange_rate(
        self, from_currency: str = "USD", to_currency: str = "CNY", amount: float = 1
    ) -> Optional[dict]:
        """获取实时汇率换算结果。

        Args:
            from_currency: 源货币代码，如 USD。
            to_currency: 目标货币代码，如 CNY。
            amount: 换算金额，默认 1。

        Returns:
            {"from": ..., "to": ..., "rate": ..., "amount": ..., "result": ...,
             "update_time": ...}，失败返回 None。
        """
        data = await self._get_json(
            "/a/huilv/huilv.php",
            {
                "from": from_currency.upper(),
                "to": to_currency.upper(),
                "amount": str(amount),
            },
        )
        if not isinstance(data, dict) or data.get("code") != 0:
            return None
        return {
            "from": str(data.get("from", "") or from_currency.upper()),
            "to": str(data.get("to", "") or to_currency.upper()),
            "rate": data.get("rate"),
            "amount": data.get("amount"),
            "result": data.get("result"),
            "update_time": str(data.get("update_time", "") or ""),
        }

    # ---------- 小黑盒游戏 ----------

    async def get_hot_games(self, max_count: int = 6) -> Optional[dict]:
        """获取小黑盒近期热门/折扣游戏。

        Args:
            max_count: 最多返回几款游戏。

        Returns:
            {"date": ..., "games": [{"name", "image", "price_current", "price_initial",
             "discount", "is_free", "platforms", "genres", "hot_tags"}]}，失败返回 None。
        """
        data = await self._get_json(
            "/a/hbox/recent.php", {"return": "json"}
        )
        if not isinstance(data, dict) or data.get("code") != 200:
            return None
        groups = data.get("groups") or []
        games = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            for g in group.get("games") or []:
                if not isinstance(g, dict):
                    continue
                name = str(g.get("name") or "").strip()
                if not name:
                    continue
                price = g.get("price")
                if isinstance(price, dict):
                    price_current = price.get("current")
                    price_initial = price.get("initial")
                    discount = price.get("discount")
                else:
                    price_current = price_initial = discount = None
                games.append(
                    {
                        "name": name,
                        "image": str(g.get("image") or "").strip(),
                        "price_current": price_current,
                        "price_initial": price_initial,
                        "discount": discount,
                        "is_free": bool(g.get("is_free")),
                        "platforms": [
                            str(p) for p in (g.get("platforms") or []) if p
                        ],
                        "genres": [
                            str(x) for x in (g.get("genres") or []) if x
                        ],
                        "hot_tags": [
                            str(x) for x in (g.get("hot_tags") or []) if x
                        ],
                    }
                )
                if len(games) >= max_count:
                    break
            if len(games) >= max_count:
                break
        if not games:
            return None
        return {
            "date": str(data.get("date", "") or ""),
            "games": games,
        }

    # ---------- 随机谜语 ----------

    async def get_riddle(self) -> Optional[dict]:
        """获取一条随机谜语（仅谜面，答案不展示在日报中）。

        Returns:
            {"mimian": ..., "midi": ..., "type": ...}，失败返回 None。
        """
        data = await self._get_json("/a/miyu.php", {"return": "json"})
        if not isinstance(data, dict):
            return None
        mimian = str(data.get("mimian") or "").strip()
        if not mimian:
            return None
        return {
            "mimian": mimian,
            "midi": str(data.get("midi") or "").strip(),
            "type": str(data.get("type") or "").strip(),
        }

    # ---------- 随机一言（纯文本接口） ----------

    async def get_random_quote(self) -> Optional[str]:
        """获取一条随机一言（糖豆子纯文本接口）。

        Returns:
            一言文本，失败返回 None。
        """
        try:
            async with await self._request_with_retry(
                "GET",
                f"{self.BASE}/sjyy.php",
                headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                response.raise_for_status()
                text = await response.text()
            text = (text or "").strip()
            return text or None
        except Exception as e:
            logger.warning(f"糖豆子随机一言请求失败: {e}")
            return None
