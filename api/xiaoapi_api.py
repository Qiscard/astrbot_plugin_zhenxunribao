"""
慕名API (xiaoapi.cn) 客户端
封装：追番更新-腾讯动漫 / bili番剧 / 语录 / 诗词 / 知识答题 / 猜灯谜。
全部为免费接口，无需 KEY。
"""
import random
from typing import Optional

import aiohttp

from astrbot.api import logger

from .base_api import BaseAPI

BASE_URL = "https://xiaoapi.cn/v1"


class XiaoapiAPI(BaseAPI):
    """慕名API 客户端。

    Args:
        session: 可选的 aiohttp.ClientSession，如果提供则复用。
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        super().__init__(session)

    async def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET 慕名API 接口并返回 JSON 字典。

        Args:
            path: 接口路径，如 /update_cartoon.php。
            params: 查询参数。

        Returns:
            顶层响应字典，失败或 code != 200 返回 None。
        """
        try:
            async with await self._request_with_retry(
                "GET",
                f"{BASE_URL}{path}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if not isinstance(data, dict):
                logger.warning(f"慕名API {path} 返回非对象: {type(data)}")
                return None
            if data.get("code") not in (200, "200"):
                logger.warning(f"慕名API {path} 返回异常: {data}")
                return None
            return data
        except Exception as e:
            logger.warning(f"慕名API {path} 请求失败: {e}")
            return None

    # ---------- 追番更新-腾讯动漫 ----------
    async def get_cartoon_updates(self, date_str: str = "") -> Optional[dict]:
        """获取腾讯动漫当天更新列表。

        Args:
            date_str: 指定日期 YYYYMMDD，留空表示当天。

        Returns:
            {"today": ..., "today_week": ..., "items": [{title,type,up_time,up_date,up_desc,link}]}。
        """
        params = {"time": date_str} if date_str else None
        data = await self._get("/update_cartoon.php", params)
        if not data:
            return None
        items = data.get("data") or []
        cleaned = []
        for it in items:
            if isinstance(it, dict) and it.get("title"):
                cleaned.append(
                    {
                        "title": str(it.get("title", "")).strip(),
                        "type": str(it.get("type", "") or "").strip(),
                        "up_time": str(it.get("up_time", "") or "").strip(),
                        "up_date": str(it.get("up_date", "") or "").strip(),
                        "up_desc": str(it.get("up_desc", "") or "").strip(),
                        "link": str(it.get("link", "") or "").strip(),
                    }
                )
        if not cleaned:
            return None
        return {
            "today": str(data.get("today", "") or "").strip(),
            "today_week": str(data.get("today_week", "") or "").strip(),
            "items": cleaned,
        }

    # ---------- bili番剧 ----------
    async def search_bili(self, keyword: str, limit: int = 8) -> list:
        """按关键词搜索番剧。

        Args:
            keyword: 番剧关键词。
            limit: 最多返回条数。

        Returns:
            [{title, id, desc, cover}]。
        """
        data = await self._get("/bili.php", {"type": "so", "msg": keyword})
        if not data:
            return []
        items = []
        for it in (data.get("data") or [])[:limit]:
            if isinstance(it, dict) and it.get("title"):
                items.append(
                    {
                        "title": str(it.get("title", "")).strip(),
                        "id": it.get("id"),
                        "desc": str(it.get("desc", "") or "").strip(),
                        "cover": str(it.get("cover", "") or "").strip(),
                    }
                )
        return items

    # ---------- 语录 ----------
    YULU_TYPES = ["经典", "动漫", "恋爱", "鼓励", "孤独", "搞笑", "友情", "歌词"]

    async def get_yulu(self, type_: str = "") -> Optional[dict]:
        """获取一条语录。

        Args:
            type_: 语录类型，留空随机。

        Returns:
            {"type": ..., "text": ..., "author": ..., "from": ...}。
        """
        t = (type_ or "").strip()
        if t not in self.YULU_TYPES:
            t = random.choice(self.YULU_TYPES)
        data = await self._get("/zs_yulu.php", {"type": t})
        if not data:
            return None
        text = str(data.get("text", "") or "").strip()
        if not text:
            return None
        return {
            "type": t,
            "text": text,
            "author": str(data.get("author", "") or "").strip(),
            "from": str(data.get("from", "") or "").strip(),
        }

    # ---------- 诗词 ----------
    async def get_shici(self, keyword: str, index: int = 1) -> Optional[dict]:
        """搜索并返回一首诗词。

        Args:
            keyword: 诗词搜索内容，如 赠汪伦。
            index: 结果序号，默认 1。

        Returns:
            {"title": ..., "author": ..., "dynasty": ..., "content": ..., "notes": ...}。
        """
        data = await self._get("/shici.php", {"msg": keyword, "n": str(index)})
        if not data:
            return None
        title = str(data.get("title", "") or "").strip()
        if not title:
            return None
        author = data.get("author") or {}
        return {
            "title": title,
            "author": str(author.get("name", "") or "").strip() if isinstance(author, dict) else "",
            "dynasty": str(data.get("dynasty", "") or "").strip(),
            "content": str(data.get("content", "") or "").strip(),
            "notes": str(data.get("notes", "") or "").strip(),
        }

    # ---------- 知识答题 ----------
    async def quiz_action(self, user_id: str, msg: str) -> Optional[dict]:
        """知识答题：开始游戏或作答。

        Args:
            user_id: 用户唯一标识。
            msg: 开始游戏 或 我答+选项。

        Returns:
            {"msg": ..., "option": ..., "answer": ...}。
        """
        data = await self._get("/game_dati.php", {"id": user_id, "msg": msg})
        if not data:
            return None
        dd = data.get("data") or {}
        if not dd.get("msg"):
            return None
        return {
            "msg": str(dd.get("msg", "")).strip(),
            "option": str(dd.get("option", "") or "").strip(),
            "answer": str(dd.get("answer", "") or "").strip(),
        }

    # ---------- 猜灯谜 ----------
    async def riddle_random(self, uid: str, festival: str = "", difficulty: str = "") -> Optional[dict]:
        """随机出一道灯谜。

        Args:
            uid: 用户唯一标识。
            festival: lantern/midautumn，可选。
            difficulty: easy/medium/hard，可选。

        Returns:
            {"id": ..., "title": ..., "type": ..., "festival": ..., "difficulty": ...}。
        """
        params: dict = {"uid": uid, "action": "random"}
        if festival:
            params["festival"] = festival
        if difficulty:
            params["difficulty"] = difficulty
        data = await self._get("/game_cdm.php", params)
        if not data:
            return None
        dd = data.get("data") or {}
        if not dd.get("title"):
            return None
        return {
            "id": dd.get("id"),
            "title": str(dd.get("title", "")).strip(),
            "type": str(dd.get("type", "") or "").strip(),
            "festival": str(dd.get("festival", "") or "").strip(),
            "difficulty": str(dd.get("difficulty", "") or "").strip(),
        }

    async def riddle_verify(self, uid: str, rid, answer: str) -> Optional[dict]:
        """验证灯谜答案。

        Args:
            uid: 用户唯一标识。
            rid: 灯谜 ID。
            answer: 用户答案。

        Returns:
            {"is_correct": bool, "correct_answer": ..., "msg": ..., "next_riddle": {...}}。
        """
        data = await self._get(
            "/game_cdm.php",
            {"uid": uid, "action": "verify", "rid": str(rid), "answer": answer},
        )
        if not data:
            return None
        dd = data.get("data") or {}
        return {
            "is_correct": bool(dd.get("is_correct")),
            "correct_answer": str(dd.get("correct_answer", "") or "").strip(),
            "msg": str(dd.get("msg", "") or "").strip(),
            "next_riddle": dd.get("next_riddle") or {},
        }
