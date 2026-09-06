"""
API 基类模块
封装 HTTP Session 管理逻辑，供所有 API 类继承
"""
import asyncio
import aiohttp
from typing import Optional

from astrbot.api import logger


class BaseAPI:
    """API 基类 - 统一管理 HTTP Session"""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        初始化

        Args:
            session: 可选的 aiohttp.ClientSession，如果提供则复用
        """
        self._session = session
        self._own_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 session，如果已有则复用，否则创建新的"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._own_session = True
        return self._session

    async def _close_session(self):
        """关闭自己创建的 session"""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._own_session = False

    async def close(self):
        """释放本实例持有的连接资源（共享 session 不会被关闭）"""
        await self._close_session()

    def set_session(self, session: aiohttp.ClientSession):
        """设置新的 session（用于 session 重置）"""
        self._session = session
        self._own_session = False

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """带重试机制的 HTTP 请求

        Args:
            method: HTTP 方法 (GET/POST)
            url: 请求 URL
            max_retries: 最大重试次数（不含首次请求）
            retry_delay: 重试间隔（秒），每次重试翻倍
            **kwargs: 传递给 session.request() 的其他参数

        Returns:
            aiohttp.ClientResponse

        Raises:
            最后一次请求的异常
        """
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                session = await self._get_session()
                return await session.request(method, url, **kwargs)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                last_exception = e
                if attempt < max_retries:
                    delay = retry_delay * (2 ** attempt)
                    logger.debug(
                        f"请求失败 (第{attempt + 1}次): {url} - {e}，"
                        f"{delay:.1f}s 后重试..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        f"请求失败 (已重试{max_retries}次): {url} - {e}"
                    )
        raise last_exception  # type: ignore[misc]