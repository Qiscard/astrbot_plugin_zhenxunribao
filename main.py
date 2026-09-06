import asyncio
import base64
import json
import random
import re
import uuid
from datetime import datetime, time
from pathlib import Path
from tempfile import gettempdir
from urllib.request import pathname2url

import aiohttp
from jinja2 import Template
from playwright.async_api import async_playwright

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain, filter, AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools

from .api.bgm_api import BGMAPI
from .api.date_utils import get_current_date_info
from .api.hitokoto_api import HitokotoAPI
from .api.holiday_api import HolidayAPI
from .api.zaobao_api import ZaobaoAPI
from .api.history_api import HistoryAPI
from .api.duji_api import DujiAPI


class ZhenxunReportPlugin(Star):
    """真寻日报插件。

    每日汇总今日新番、历史上的今天、世界新闻、摸鱼日历和今日一言/毒鸡汤，
    渲染成日报图片发送。支持 /日报 指令与定时推送。

    指令：
        /日报          生成并发送当日日报图片
        /日报群组ID    查看当前会话的 unified_msg_origin（用于定时推送配置）
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        self.plugin_dir = Path(__file__).parent.resolve()
        self.template_path = self.plugin_dir / "daily_news.html"

        # Shared aiohttp session for all API clients
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10)
        self.http_session = aiohttp.ClientSession(timeout=timeout)

        api_token = str(config.get("api_token", "") or "").strip()
        self.bgm_api = BGMAPI(session=self.http_session)
        self.hitokoto_api = HitokotoAPI(session=self.http_session, token=api_token)
        self.holiday_api = HolidayAPI(session=self.http_session, token=api_token)
        self.zaobao_api = ZaobaoAPI(session=self.http_session, token=api_token)
        self.history_api = HistoryAPI(session=self.http_session, token=api_token)
        self.duji_api = DujiAPI(session=self.http_session)

        self.push_task = None

        # Group id -> unified_msg_origin mapping, learned from /日报 usage
        self.group_umo_mapping = {}
        self._load_group_mapping()

        if config.get("enable_scheduled_push", False):
            self.push_task = asyncio.create_task(self._scheduled_push_task())
            logger.info("Scheduled push task initialized")

        logger.info("Zhenxun daily report plugin loaded")

    @filter.command("日报")
    async def daily_news(self, event: AstrMessageEvent):
        """Generate and send today's daily report image."""
        umo = event.unified_msg_origin
        logger.info(f"Daily report triggered, unified_msg_origin: {umo}")

        # Auto-learn the group's unified_msg_origin for scheduled push
        group_id = self._extract_group_id(umo)
        if group_id and group_id not in self.group_umo_mapping:
            self.group_umo_mapping[group_id] = umo
            self._save_group_mapping()
            logger.info(f"Learned unified_msg_origin for group {group_id}: {umo}")

        image_path = None
        try:
            image_path = await self._generate_daily_image()
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"Failed to generate daily report: {e}", exc_info=True)
            yield event.plain_result(f"生成日报时出错: {str(e)}")
        finally:
            if image_path and Path(image_path).exists():
                try:
                    Path(image_path).unlink()
                    logger.debug(f"Cleaned up temp image: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp image: {e}")

    @filter.command("日报群组ID")
    async def get_group_id(self, event: AstrMessageEvent):
        """Show the current session's unified_msg_origin for push config."""
        umo = event.unified_msg_origin
        logger.info(f"Query unified_msg_origin: {umo}")
        yield event.plain_result(
            f"📋 当前会话信息：\n"
            f"unified_msg_origin: {umo}\n\n"
            f"💡 请将此值添加到插件配置的「定时推送目标群组列表」中"
        )

    async def _generate_daily_image(self) -> str:
        """Fetch data, render the HTML template and screenshot it to a PNG.

        Returns:
            Path to the generated PNG image.
        """
        logger.info("Generating daily report")

        quote_mode = self.config.get("quote_mode", "hitokoto")
        max_anime_count = self.config.get("max_anime_count", 4)
        max_news_count = self.config.get("max_news_count", 10)
        max_holiday_count = self.config.get("max_holiday_count", 5)
        max_history_count = self.config.get("max_history_count", 8)

        date_info = get_current_date_info()
        anime_list, hitokoto_data, moyu_list, world_news, history_events, duji_text = (
            await self._fetch_all_data(
                max_anime_count=max_anime_count,
                max_news_count=max_news_count,
                max_holiday_count=max_holiday_count,
                max_history_count=max_history_count,
                quote_mode=quote_mode,
            )
        )

        template_data = {
            "date_info": date_info,
            "anime_list": anime_list or [],
            "hitokoto_data": hitokoto_data or {"hitokoto": "暂无", "from": "佚名"},
            "moyu_list": moyu_list or [],
            "world_news": world_news or [],
            "history_events": history_events or [],
            "duji_text": duji_text or "今天也要加油哦！",
            "quote_mode": quote_mode,
        }

        logger.info(
            f"Template data ready: anime={len(template_data['anime_list'])}, "
            f"holidays={len(template_data['moyu_list'])}, "
            f"news={len(template_data['world_news'])}, "
            f"history={len(template_data['history_events'])}"
        )

        html_template_str = self.template_path.read_text(encoding="utf-8")
        template = Template(html_template_str)
        rendered_html = template.render(**template_data)
        rendered_html = await self._embed_resources(rendered_html)

        style_fix = """
html, body {
  width: 578px;
  margin: 0;
  padding: 0;
  overflow-x: hidden;
}
"""
        rendered_html = rendered_html.replace("</style>", style_fix + "</style>", 1)

        image_path = await self._render_html_with_playwright(rendered_html)
        logger.info("Daily report generated")
        return image_path

    async def _fetch_all_data(
        self,
        max_anime_count: int,
        max_news_count: int,
        max_holiday_count: int,
        max_history_count: int,
        quote_mode: str,
    ):
        """Fetch all data sources concurrently.

        Only the quote source matching ``quote_mode`` is requested to avoid
        wasted API calls.

        Args:
            max_anime_count: Max anime entries to fetch.
            max_news_count: Max news entries to fetch.
            max_holiday_count: Max holiday entries to fetch.
            max_history_count: Max history events to fetch.
            quote_mode: "hitokoto" or "duji".

        Returns:
            Tuple of (anime_list, hitokoto_data, moyu_list, world_news,
            history_events, duji_text). Failed sources degrade to empty/neutral
            placeholders instead of fabricated sample data.
        """
        fetch_quote = (
            self.duji_api.get_today_duji_async()
            if quote_mode == "duji"
            else self.hitokoto_api.get_hitokoto_async()
        )
        results = await asyncio.gather(
            self.bgm_api.get_today_anime_async(max_count=max_anime_count),
            self.holiday_api.get_moyu_list_async(max_count=max_holiday_count),
            self.zaobao_api.get_world_news_async(max_count=max_news_count),
            self.history_api.get_today_history_async(max_count=max_history_count),
            fetch_quote,
            return_exceptions=True,
        )

        anime_list = results[0] if not isinstance(results[0], Exception) else []
        moyu_list = results[1] if not isinstance(results[1], Exception) else []
        world_news = results[2] if not isinstance(results[2], Exception) else []
        history_events = results[3] if not isinstance(results[3], Exception) else []

        hitokoto_data = {"hitokoto": "暂无", "from": "佚名"}
        duji_text = "今天也要加油哦！"
        if quote_mode == "duji":
            if not isinstance(results[4], Exception) and results[4]:
                duji_text = results[4]
        else:
            if not isinstance(results[4], Exception) and results[4]:
                hitokoto_data = results[4]
                from_value = str(hitokoto_data.get("from", "") or "").strip()
                if not from_value or from_value == "网络":
                    from_value = "佚名"
                hitokoto_data["from"] = from_value

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch data source (index {i}): {result}")

        logger.debug(
            f"Fetched raw data: anime={anime_list}, holidays={moyu_list}, "
            f"news={world_news}, history={history_events}"
        )

        return anime_list, hitokoto_data, moyu_list, world_news, history_events, duji_text

    def _file_to_base64(self, file_path: Path) -> str | None:
        """Encode a local resource file as a data URI for HTML embedding.

        Args:
            file_path: Path to the font/image file.

        Returns:
            Data URI string, or None when the file is missing or unreadable.
        """
        try:
            if not file_path.exists():
                logger.warning(f"Resource file not found: {file_path}")
                return None

            base64_data = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            mime_types = {
                ".otf": "font/opentype",
                ".ttf": "font/ttf",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".svg": "image/svg+xml",
            }
            mime_type = mime_types.get(file_path.suffix.lower(), "application/octet-stream")
            return f"data:{mime_type};base64,{base64_data}"
        except Exception as e:
            logger.warning(f"Failed to encode file to base64 {file_path}: {e}")
            return None

    async def _embed_resources(self, html_template: str) -> str:
        """Inline local fonts and images referenced by the template as data URIs."""
        def replace_font(match):
            file_path = self.plugin_dir / "res" / "font" / match.group(1)
            base64_uri = self._file_to_base64(file_path)
            if base64_uri:
                return f'url("{base64_uri}")'
            return match.group(0)

        html_template = re.sub(
            r'url\(["\']?\./res/font/([^"\')]+)["\']?\)',
            replace_font,
            html_template,
            flags=re.IGNORECASE,
        )

        def replace_image(match):
            filepath = match.group(1)
            if filepath.startswith("icon/") or filepath.startswith("image/"):
                file_path = self.plugin_dir / "res" / filepath
                base64_uri = self._file_to_base64(file_path)
                if base64_uri:
                    logger.debug(f"Embedded image as base64: {filepath}")
                    return f'src="{base64_uri}"'
                logger.warning(f"Failed to embed image: {filepath}")
            return match.group(0)

        html_template = re.sub(
            r'src=["\']\./res/([^"\']+)["\']',
            replace_image,
            html_template,
            flags=re.IGNORECASE,
        )

        return html_template

    async def _render_html_with_playwright(
        self, html_content: str, output_path: str | None = None
    ) -> str:
        """Render HTML to PNG using Playwright.

        Clarity is controlled by the BrowserContext device_scale_factor (DPR).

        Args:
            html_content: Rendered HTML string.
            output_path: Optional output PNG path; defaults to a temp file.

        Returns:
            Path to the generated PNG image.
        """
        temp_html_path = None
        context = None
        try:
            temp_html_path = Path(gettempdir()) / f"zhenxun_daily_{uuid.uuid4().hex}.html"
            temp_html_path.write_text(html_content, encoding="utf-8")

            if output_path is None:
                output_path = str(temp_html_path.with_suffix(".png"))

            # Higher DPR means sharper output but slower render and larger file
            dpr = int(self.config.get("render_dpr", 5))
            dpr = max(1, min(dpr, 6))

            async with async_playwright() as p:
                logger.info("Launching Playwright browser...")
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={"width": 1156, "height": 1000},
                        device_scale_factor=dpr,
                    )
                    page = await context.new_page()

                    file_url = f"file://{pathname2url(str(temp_html_path))}"
                    await page.goto(file_url, wait_until="networkidle")
                    await page.wait_for_timeout(2000)

                    wrapper = await page.query_selector(".wrapper")
                    if not wrapper:
                        raise Exception("Element .wrapper not found")

                    box = await wrapper.bounding_box()
                    if not box:
                        raise Exception("Cannot get bounding box of .wrapper")

                    # Resize viewport to fit the full content height
                    viewport_height = max(int(box["height"] * 1.2), 1000)
                    viewport_width = 1156
                    await page.set_viewport_size(
                        {"width": viewport_width, "height": viewport_height}
                    )

                    # Re-query after reflow
                    await page.wait_for_timeout(300)
                    wrapper = await page.query_selector(".wrapper")
                    if not wrapper:
                        raise Exception("Element .wrapper not found after viewport resize")

                    box = await wrapper.bounding_box()
                    if not box:
                        raise Exception(
                            "Cannot get bounding box of .wrapper after viewport resize"
                        )

                    logger.info(
                        f"Wrapper size: {int(box['width'])}x{int(box['height'])}, "
                        f"viewport: {viewport_width}x{viewport_height}, DPR={dpr}"
                    )

                    clip = {
                        "x": int(box["x"]),
                        "y": int(box["y"]),
                        "width": int(box["width"]),
                        "height": int(box["height"]),
                    }
                    await page.screenshot(path=output_path, type="png", clip=clip)

                    logger.info(f"Screenshot saved: {output_path}")
                    return output_path
                finally:
                    try:
                        if context:
                            await context.close()
                    finally:
                        await browser.close()

        except Exception as e:
            logger.error(f"Playwright rendering failed: {e}", exc_info=True)
            raise
        finally:
            if temp_html_path and temp_html_path.exists():
                try:
                    temp_html_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete temp HTML file: {e}")

    async def _scheduled_push_task(self):
        """Periodic scheduler for the daily push.

        Re-reads the config every cycle so config changes take effect within a
        minute, and guards against duplicate pushes with a last-push-date mark.
        """
        last_push_date = None
        while True:
            try:
                if not self.config.get("enable_scheduled_push", False):
                    last_push_date = None
                    await asyncio.sleep(60)
                    continue

                push_groups = self.config.get("scheduled_push_groups", [])
                if not push_groups:
                    logger.debug("Scheduled push enabled but no target groups configured")
                    await asyncio.sleep(60)
                    continue

                try:
                    hour, minute = map(
                        int, str(self.config.get("scheduled_push_time", "08:00")).split(":")
                    )
                    push_time = time(hour, minute)
                except (ValueError, AttributeError):
                    logger.error(
                        f"Invalid scheduled_push_time: "
                        f"{self.config.get('scheduled_push_time')}, falling back to 08:00"
                    )
                    push_time = time(8, 0)

                now = datetime.now()
                due = now >= datetime.combine(now.date(), push_time)
                if due and last_push_date != now.date():
                    last_push_date = now.date()
                    logger.info("Scheduled push triggered")
                    await self._push_daily_to_groups(push_groups)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.info("Scheduled push task cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduled push task error: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _push_daily_to_groups(self, group_list: list):
        """Push the daily report to configured sessions.

        All pushes go through ``context.send_message`` so every platform
        adapter is supported; entries may be unified_msg_origin strings or
        plain group ids previously learned from /日报 usage.

        Args:
            group_list: Push targets (unified_msg_origin or plain group id).
        """
        image_path = None
        try:
            logger.info(f"Generating daily report for push, targets: {len(group_list)}")
            image_path = await self._generate_daily_image()
            if not image_path or not Path(image_path).exists():
                logger.error(f"Daily report image missing: {image_path}")
                return

            greeting = await self._generate_greeting_text()

            success_count = 0
            for entry in group_list:
                umo = self._resolve_umo(entry)
                if not umo:
                    logger.warning(
                        f"Cannot resolve unified_msg_origin for push target '{entry}'. "
                        f"Send /日报 once in the target group so the plugin can learn it, "
                        f"or configure the full unified_msg_origin (see /日报群组ID)."
                    )
                    continue
                try:
                    chain = MessageChain()
                    if greeting:
                        chain.message(greeting)
                    chain.file_image(image_path)
                    sent = await self.context.send_message(umo, chain)
                    if sent:
                        success_count += 1
                        logger.info(f"Daily report pushed to session: {umo}")
                    else:
                        logger.warning(f"No matching platform for session: {umo}")
                except Exception as e:
                    logger.error(f"Failed to push to session {umo}: {e}", exc_info=True)

            logger.info(f"Scheduled push finished, success: {success_count}/{len(group_list)}")
        except Exception as e:
            logger.error(f"Scheduled push failed: {e}", exc_info=True)
        finally:
            if image_path and Path(image_path).exists():
                try:
                    Path(image_path).unlink()
                    logger.debug(f"Cleaned up temp image: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp image: {e}")

    def _resolve_umo(self, entry: str) -> str | None:
        """Resolve a configured push target to a unified_msg_origin.

        Args:
            entry: unified_msg_origin string, or a plain group id that was
                previously learned from /日报 usage.

        Returns:
            The unified_msg_origin, or None when it cannot be resolved.
        """
        entry = str(entry).strip()
        if ":" in entry:
            return entry
        return self.group_umo_mapping.get(self._extract_group_id(entry))

    def _load_group_mapping(self):
        """Load the group id -> unified_msg_origin mapping from the data dir."""
        try:
            mapping_file = StarTools.get_data_dir("astrbot_plugin_zhenxunribao") / "group_mapping.json"
            if mapping_file.exists():
                self.group_umo_mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
                logger.info(f"Loaded {len(self.group_umo_mapping)} group mappings")
        except Exception as e:
            logger.warning(f"Failed to load group mappings: {e}")
            self.group_umo_mapping = {}

    def _save_group_mapping(self):
        """Persist the group id -> unified_msg_origin mapping to the data dir."""
        try:
            mapping_file = StarTools.get_data_dir("astrbot_plugin_zhenxunribao") / "group_mapping.json"
            mapping_file.write_text(
                json.dumps(self.group_umo_mapping, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug(f"Saved {len(self.group_umo_mapping)} group mappings")
        except Exception as e:
            logger.warning(f"Failed to save group mappings: {e}")

    def _extract_group_id(self, group_id_str: str) -> str:
        """Extract the plain group id from various identifier formats.

        Args:
            group_id_str: A pure group id or a unified_msg_origin such as
                ``aiocqhttp:GroupMessage:123456789``.

        Returns:
            The extracted plain group id.
        """
        group_id_str = str(group_id_str).strip()

        if group_id_str.isdigit():
            return group_id_str

        if ':' in group_id_str:
            parts = group_id_str.split(':')
            if len(parts) >= 3:
                last_part = parts[-1]
                # Handle possible botid_groupid formats
                if '_' in last_part:
                    return last_part.split('_')[-1]
                return last_part

        return group_id_str

    async def _generate_greeting_text(self) -> str:
        """Generate the push greeting, via LLM when enabled.

        Returns:
            A short greeting text line (possibly empty on failure).
        """
        try:
            now = datetime.now()
            hour = now.hour
            date_info = get_current_date_info()

            moyu_list = []
            try:
                holiday_data = await self.holiday_api.get_moyu_list_async(max_count=1)
                if holiday_data:
                    moyu_list = holiday_data
            except Exception as e:
                logger.debug(f"Failed to fetch holidays for greeting: {e}")

            if not self.config.get("enable_ai_greeting", False):
                return self._get_default_greeting(hour, moyu_list)

            prompt_parts = [
                f"现在是{date_info['date_str']} {date_info['week_cn']}",
                f"时间是{hour}点",
            ]

            if moyu_list:
                holiday_names = [h.get('name', '') for h in moyu_list if h.get('name')]
                if holiday_names:
                    prompt_parts.append(f"即将到来的节日：{', '.join(holiday_names[:2])}")

            if date_info.get('cn_date_str') and date_info.get('cn_date_str') != '农历未知':
                prompt_parts.append(f"农历{date_info['cn_date_str']}")

            prompt = (
                f"{', '.join(prompt_parts)}。"
                f"请生成一句简短（15字以内）、温馨且富有创意的日报推送问候语。"
                f"要求：1. 结合时间或节日 2. 亲切自然 3. 带上真寻的口吻 4. 只返回问候语文本，不要其他内容"
            )

            try:
                provider_id = None
                if self.group_umo_mapping:
                    umo_for_provider = next(iter(self.group_umo_mapping.values()))
                    try:
                        provider_id = await self.context.get_current_chat_provider_id(
                            umo_for_provider
                        )
                    except Exception as e:
                        logger.debug(f"Failed to get chat provider for {umo_for_provider}: {e}")
                if not provider_id:
                    insts = self.context.provider_manager.get_insts()
                    if insts:
                        provider_id = insts[0].meta().id

                if provider_id:
                    llm_resp = await self.context.llm_generate(
                        chat_provider_id=provider_id,
                        prompt=prompt,
                    )
                    if llm_resp and hasattr(llm_resp, 'completion_text'):
                        greeting = llm_resp.completion_text.strip().strip('"').strip("'").strip()
                        if greeting and len(greeting) <= 50:
                            logger.info(f"AI generated greeting: {greeting}")
                            return f"📰 {greeting}\n"
            except Exception as e:
                logger.debug(f"AI greeting generation failed: {e}")

            return self._get_default_greeting(hour, moyu_list)

        except Exception as e:
            logger.warning(f"Failed to generate greeting: {e}")
            return "📰 真寻日报来啦~\n"

    def _get_default_greeting(self, hour: int, moyu_list: list) -> str:
        """Build a default (non-AI) greeting based on time of day and holidays.

        Args:
            hour: Current hour (0-23).
            moyu_list: Upcoming holidays, each with 'name' and 'days_left'.

        Returns:
            The greeting text line.
        """
        greetings = {
            "morning": ["早安！新的一天开始啦~", "早上好！今日份日报送达~", "早安！美好的一天从日报开始~"],
            "noon": ["中午好！午间日报来啦~", "中午好~来看看今天的资讯吧~", "午安！休息时刻看看日报~"],
            "afternoon": ["下午好！日报新鲜出炉~", "下午茶时间，看看日报吧~", "下午好！今日资讯已备好~"],
            "evening": ["晚上好！晚间日报送达~", "晚上好~睡前看看今日资讯吧~", "晚安前的日报时间~"],
        }

        if 5 <= hour < 11:
            period_greetings = greetings["morning"]
        elif 11 <= hour < 14:
            period_greetings = greetings["noon"]
        elif 14 <= hour < 18:
            period_greetings = greetings["afternoon"]
        else:
            period_greetings = greetings["evening"]

        if moyu_list:
            holiday = moyu_list[0]
            if holiday.get('name'):
                # days_left may be int or str depending on the data source
                try:
                    days_left = int(str(holiday.get('days_left', '')))
                except (TypeError, ValueError):
                    days_left = None
                if days_left == 0:
                    return f"📰 {holiday['name']}快乐！日报送上~\n"
                elif days_left is not None and days_left <= 3:
                    return f"📰 距离{holiday['name']}还有{days_left}天！日报来啦~\n"

        return f"📰 {random.choice(period_greetings)}\n"

    async def terminate(self):
        """Stop background tasks and release the shared HTTP session."""
        logger.info("Zhenxun daily report plugin unloading...")
        if self.push_task and not self.push_task.done():
            self.push_task.cancel()
            try:
                await self.push_task
            except asyncio.CancelledError:
                pass
            logger.info("Scheduled push task cancelled")
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("HTTP session closed")
