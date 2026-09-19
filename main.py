import asyncio
import base64
import copy
import json
import os
import random
import re
import tempfile
import uuid
from datetime import datetime, time
from urllib.request import pathname2url

import aiohttp
from jinja2 import Template
from playwright.async_api import async_playwright

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools

try:
    from astrbot.api.web import json_response
    from astrbot.api.web import request as web_request
except ModuleNotFoundError:
    # 兼容未提供 astrbot.api.web 的旧版本：直接用 Quart 原语
    from quart import jsonify
    from quart import request as web_request

    def json_response(data=None, *, status_code=200):
        resp = jsonify(data)
        resp.status_code = status_code
        return resp


from .api.aa1_api import AA1API
from .api.alapi_api import ALAPIClient
from .api.bgm_api import BGMAPI
from .api.date_utils import days_until_date, days_until_weekday, get_current_date_info
from .api.duji_api import DujiAPI
from .api.english_api import EnglishAPI
from .api.history_api import HistoryAPI
from .api.hitokoto_api import HitokotoAPI
from .api.holiday_api import HolidayAPI
from .api.milora_api import MiloraAPI
from .api.tangdouz_api import TangdouzAPI
from .api.xiaoapi_api import XiaoapiAPI
from .api.zaobao_api import ZaobaoAPI

# 可自由排序的模块类型（摸鱼日历/历史上的今天/底栏引用为固定面板，不在此列）
# slots 预留后续“顶部/底部/自由区”约束；render 对应模板宏类型
MODULE_TYPE_META = {
    "anime": {
        "title": "今日新番",
        "count": 4,
        "icon": "./res/icon/bgm.png",
        "slots": ["body"],
        "render": "anime",
        "has_count": True,
    },
    "news": {
        "title": "60s读懂世界",
        "count": 10,
        "icon": "./res/icon/60.png",
        "slots": ["body"],
        "render": "news",
        "has_count": True,
    },
    "english": {
        "title": "每日英语",
        "count": 1,
        # 英语接口单次最多返回 5 个单词，条数上限收窄避免误导
        "count_max": 5,
        "icon": "./res/icon/hitokoto.png",
        "slots": ["body"],
        "render": "english",
        "has_count": True,
    },
    "essay": {
        "title": "每日一文",
        "count": 1,
        "icon": "./res/icon/game.png",
        "slots": ["body"],
        "render": "essay",
        "has_count": True,
    },
    "aidaily": {
        "title": "AI早报",
        "count": 10,
        "icon": "./res/icon/60.png",
        "slots": ["body"],
        "render": "aidaily",
        "has_count": True,
    },
    "hbox": {
        "title": "小黑盒游戏",
        "count": 6,
        "icon": "./res/icon/game.png",
        "slots": ["body"],
        "render": "hbox",
        "has_count": True,
    },
    "cartoon": {
        "title": "今日追番",
        "count": 6,
        "icon": "./res/icon/bgm.png",
        "slots": ["body"],
        "render": "cartoon",
        "has_count": True,
    },
    "shici": {
        "title": "每日诗词",
        "count": 1,
        "icon": "./res/icon/game.png",
        "slots": ["body"],
        "render": "shici",
    },
    "yulu": {
        "title": "语录",
        "count": 1,
        "icon": "./res/icon/hitokoto.png",
        "slots": ["body"],
        "render": "yulu",
    },
}

DEFAULT_MODULE_TITLES = {k: v["title"] for k, v in MODULE_TYPE_META.items()}
DEFAULT_MODULE_COUNTS = {
    k: v["count"] for k, v in MODULE_TYPE_META.items() if v.get("has_count")
}
MODULE_ICONS = {k: v["icon"] for k, v in MODULE_TYPE_META.items()}

# 各模块可配置的接口请求参数（编辑器「配置接口」面板）。
# key 为模块类型；value 为字段定义列表，供前端渲染表单与后端读取。
# 仅存放“业务请求参数”，key/token 等鉴权仍放在插件配置界面。
MODULE_PARAM_SCHEMA = {
    "aidaily": [
        {
            "key": "type",
            "label": "返回格式",
            "type": "select",
            "options": [
                {"value": "txt", "label": "纯文本"},
                {"value": "md", "label": "Markdown"},
                {"value": "image", "label": "渲染图"},
            ],
            "default": "txt",
        },
        {
            "key": "date",
            "label": "日期",
            "type": "text",
            "placeholder": "YYYY-MM-DD，留空当天",
            "default": "",
        },
    ],
    "cartoon": [
        {
            "key": "date",
            "label": "日期",
            "type": "text",
            "placeholder": "YYYYMMDD，留空当天",
            "default": "",
        },
    ],
    "shici": [
        {
            "key": "keyword",
            "label": "诗词关键词",
            "type": "text",
            "placeholder": "如：静夜思",
            "default": "静夜思",
        },
    ],
    "yulu": [
        {
            "key": "type",
            "label": "语录类型",
            "type": "select",
            "options": [
                {"value": "", "label": "随机"},
                {"value": "经典", "label": "经典"},
                {"value": "动漫", "label": "动漫"},
                {"value": "恋爱", "label": "恋爱"},
                {"value": "鼓励", "label": "鼓励"},
                {"value": "孤独", "label": "孤独"},
                {"value": "搞笑", "label": "搞笑"},
                {"value": "友情", "label": "友情"},
                {"value": "歌词", "label": "歌词"},
            ],
            "default": "",
        },
    ],
}

# 底栏短句来源：显示名与默认标题
QUOTE_SOURCE_LABELS = {
    "hitokoto": "今日一言",
    "duji": "毒鸡汤",
    "mingyan": "名人名言",
    "tiangou": "舔狗日记",
    "gaoxiao": "搞笑语录",
    "xiehouyu": "歇后语",
    "sjyy": "随机一言",
    "riddle": "随机谜语",
}

# 顶部模块候选来源（单选）：历史上的今天 / 每日英语 / 实时汇率
TOP_SOURCE_LABELS = {
    "history": "历史上的今天",
    "english": "每日英语",
    "exchange": "实时汇率",
}

# 中间模块类型分类：统一「中间模块」列表在编辑器里按分类组织可选类型
MODULE_CATEGORIES = {
    "番剧游戏": ["anime", "cartoon", "hbox"],
    "新闻资讯": ["news", "aidaily"],
    "文字内容": ["english", "essay", "shici", "yulu"],
}

# 预设主题（方案A，参考 bot_menu 主题方案）：每个主题给出日报 :root 中
# 全部颜色变量（--pink-bg 背景 / --panel-bg 面板 / --panel-border 描边 /
# --title-pink 标题 / --text-* 文字），界面美化（圆角/阴影）沿用模板默认值。
# 第一个 key 为默认主题。
THEME_PRESETS = {
    "mahiro": {
        "label": "真寻粉",
        "colors": {
            "pink_bg": "#e8aebb",
            "panel_bg": "#ece7eb",
            "panel_border": "#ee97ae",
            "panel_border_deep": "#ea8aa3",
            "panel_tag_bg": "#fbf9fa",
            "title_pink": "#f39db4",
            "title_shadow": "#de839d",
            "title_white": "#fffafc",
            "text_main": "#252630",
            "text_soft": "#9f7687",
            "text_accent": "#ff8ca7",
        },
    },
    "sakura": {
        "label": "樱花粉",
        "colors": {
            "pink_bg": "#f4b9c9",
            "panel_bg": "#fbeef2",
            "panel_border": "#ef9fb6",
            "panel_border_deep": "#e68ba5",
            "panel_tag_bg": "#fff9fb",
            "title_pink": "#f491b0",
            "title_shadow": "#d97f9b",
            "title_white": "#fffdfe",
            "text_main": "#2b2b36",
            "text_soft": "#a6788c",
            "text_accent": "#ff6f9c",
        },
    },
    "lavender": {
        "label": "薰衣草紫",
        "colors": {
            "pink_bg": "#c3b3e8",
            "panel_bg": "#efeafb",
            "panel_border": "#a48ad9",
            "panel_border_deep": "#977bd1",
            "panel_tag_bg": "#faf8ff",
            "title_pink": "#9a86e0",
            "title_shadow": "#7f6bc7",
            "title_white": "#fdfcff",
            "text_main": "#2a2938",
            "text_soft": "#84769e",
            "text_accent": "#7c5cf0",
        },
    },
    "sky": {
        "label": "晴空蓝",
        "colors": {
            "pink_bg": "#a7c4e8",
            "panel_bg": "#e9f1fa",
            "panel_border": "#8fb3e0",
            "panel_border_deep": "#7ea6da",
            "panel_tag_bg": "#fafcff",
            "title_pink": "#7aa7e0",
            "title_shadow": "#5f8fc9",
            "title_white": "#fbfdff",
            "text_main": "#252c3a",
            "text_soft": "#6f86a5",
            "text_accent": "#4f8ef7",
        },
    },
    "mint": {
        "label": "薄荷绿",
        "colors": {
            "pink_bg": "#9fd4c2",
            "panel_bg": "#e9f7f2",
            "panel_border": "#7fc4ae",
            "panel_border_deep": "#6cb69f",
            "panel_tag_bg": "#f8fffc",
            "title_pink": "#6cbfa4",
            "title_shadow": "#4fa58a",
            "title_white": "#fbfffd",
            "text_main": "#24332e",
            "text_soft": "#6f9488",
            "text_accent": "#2fae8b",
        },
    },
    "gold": {
        "label": "暖阳橙",
        "colors": {
            "pink_bg": "#eec09a",
            "panel_bg": "#fbf1e6",
            "panel_border": "#e3ab7c",
            "panel_border_deep": "#d99c69",
            "panel_tag_bg": "#fffaf4",
            "title_pink": "#e3a26e",
            "title_shadow": "#c98755",
            "title_white": "#fffcf9",
            "text_main": "#322a23",
            "text_soft": "#a08169",
            "text_accent": "#f08a3c",
        },
    },
    "matcha": {
        "label": "抹茶绿",
        "colors": {
            "pink_bg": "#b5c99a",
            "panel_bg": "#f0f5e8",
            "panel_border": "#a3bd86",
            "panel_border_deep": "#93b174",
            "panel_tag_bg": "#fbfdf6",
            "title_pink": "#96b479",
            "title_shadow": "#7a9c5c",
            "title_white": "#fcfff8",
            "text_main": "#2b3226",
            "text_soft": "#82926e",
            "text_accent": "#6da63c",
        },
    },
    "midnight": {
        "label": "夜幕蓝",
        "colors": {
            "pink_bg": "#a8b2c8",
            "panel_bg": "#eef1f7",
            "panel_border": "#93a0bf",
            "panel_border_deep": "#8291b3",
            "panel_tag_bg": "#fafbfe",
            "title_pink": "#8898bd",
            "title_shadow": "#6c7ca4",
            "title_white": "#fcfdff",
            "text_main": "#282c38",
            "text_soft": "#75819d",
            "text_accent": "#5a7be8",
        },
    },
}

# 默认主题 key（THEME_PRESETS 第一项）
DEFAULT_THEME = next(iter(THEME_PRESETS))

# 主题颜色变量名 → 模板 CSS 变量名的映射（注入 :root 覆盖块时使用）
THEME_CSS_VAR_NAMES = {
    "pink_bg": "--pink-bg",
    "panel_bg": "--panel-bg",
    "panel_border": "--panel-border",
    "panel_border_deep": "--panel-border-deep",
    "panel_tag_bg": "--panel-tag-bg",
    "title_pink": "--title-pink",
    "title_shadow": "--title-shadow",
    "title_white": "--title-white",
    "text_main": "--text-main",
    "text_soft": "--text-soft",
    "text_accent": "--text-accent",
}

# modules.json 不存在时写入的默认配置
DEFAULT_MODULE_CONFIG = {
    "moyu_title": "摸鱼日历",
    # 摸鱼日历固定展示在左上角，按顺序展示计时项（最多 10 条），默认留空由用户自行添加。
    # 类型：holiday=下一个法定节假日；custom=自定义计时(YYYY-MM-DD 一次性 / MM-DD 每年循环)；
    #      weekend=周末（weekday 仅支持 6=周六 / 7=周日）
    # 每条计时项可自定义前段文字 prefix（默认「距离」）与后段文字 suffix（默认「还剩」）。
    "moyu_items": [],
    # 历史上的今天固定展示在摸鱼日历右侧
    "history_enabled": True,
    "history_title": "历史上的今天",
    "history_count": 4,
    # 顶部模块：与摸鱼日历同行，从候选来源中单选一个展示
    # （history/english/exchange；history_* 字段为 history 来源的参数）
    "top_source": "history",
    "top_params": {},
    # 顶部来源为 english 时展示的单词数量（1-5，接口单次上限 5 个）
    "top_english_count": 1,
    # 实时汇率参数：一个源货币，可配置多个目标货币（最多 6 个）
    "exchange_from": "USD",
    "exchange_targets": ["CNY"],
    "exchange_amount": 100,
    # 主题：THEME_PRESETS 中的预设 key（方案A，界面美化沿用模板默认值）
    "theme": DEFAULT_THEME,
    # 底栏引用固定展示在日报底部，quote_sources 可多选（每次随机取其一）
    "quote_enabled": True,
    "quote_title": "",
    "quote_sources": ["hitokoto"],
    # 中间模块：统一列表，按顺序纵向排列（类型见 MODULE_CATEGORIES 分类）
    "modules": [
        {"type": "anime", "enabled": True, "title": "今日新番", "count": 4},
        {"type": "news", "enabled": True, "title": "60s读懂世界", "count": 10},
    ],
}



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

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(plugin_dir, "daily_news.html")
        self.plugin_dir = plugin_dir
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_zhenxunribao")

        # 创建共享的 aiohttp ClientSession，供所有 API 类复用
        # 设置连接级超时，防止 TCP 握手阶段无限挂起
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10)
        self.http_session = aiohttp.ClientSession(timeout=timeout)

        self.bgm_api = BGMAPI(session=self.http_session)
        self.alapi_token = str(config.get("alapi_token", "") or "").strip()
        self.alapi = ALAPIClient(session=self.http_session, token=self.alapi_token)
        self.hitokoto_api = HitokotoAPI(session=self.http_session, token=self.alapi_token)
        self.holiday_api = HolidayAPI(
            session=self.http_session, token=self.alapi_token
        )
        self.zaobao_api = ZaobaoAPI(session=self.http_session, token=self.alapi_token)
        self.history_api = HistoryAPI(
            session=self.http_session, token=self.alapi_token
        )
        self.duji_api = DujiAPI(session=self.http_session, token=self.alapi_token)
        self.aa1_api = AA1API(session=self.http_session)
        self.english_api = EnglishAPI(session=self.http_session)
        # Milora：key 仅来自插件配置；业务请求参数（type/date）在编辑器按模块配置
        self.milora_api = MiloraAPI(
            session=self.http_session,
            api_key=str(config.get("milora_api_key", "") or "").strip(),
        )
        self.xiaoapi_api = XiaoapiAPI(session=self.http_session)
        self.tangdouz_api = TangdouzAPI(session=self.http_session)

        self.push_task = None

        # 猜灯谜：uid -> 当前灯谜 id（用于作答校验）
        self._riddle_state = {}

        # 群号到 unified_msg_origin 的映射，用于定时推送
        self.group_umo_mapping = {}
        self._load_group_mapping()

        # 注册日报编辑器 Page 的 Web API
        self._register_web_apis(context)

        # 启动定时推送任务（使用延迟启动，等待平台适配器就绪）
        if config.get("enable_scheduled_push", False):
            asyncio.create_task(self._delayed_start_scheduler())
            logger.info("定时推送任务正在初始化...")

        logger.info("真寻日报插件已加载")

    async def _delayed_start_scheduler(self):
        """延迟启动定时推送调度器"""
        try:
            # 等待 15 秒让系统完全初始化
            await asyncio.sleep(15)

            # 取消已存在的旧任务（防止重复）
            if self.push_task and not self.push_task.done():
                self.push_task.cancel()
                try:
                    await self.push_task
                except asyncio.CancelledError:
                    pass

            # 确保 HTTP session 可用
            if self.http_session is None or self.http_session.closed:
                timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10)
                self.http_session = aiohttp.ClientSession(timeout=timeout)
                # 重新初始化 API 客户端的 session
                self._reinit_api_sessions()

            self.push_task = asyncio.create_task(self._scheduled_push_task())
            logger.info("定时推送任务已启动（延迟初始化）")
        except Exception as e:
            logger.error(f"启动定时推送任务失败: {e}", exc_info=True)

    def _reinit_api_sessions(self):
        """重新初始化 API 客户端的 session"""
        self.bgm_api.set_session(self.http_session)
        self.alapi.set_session(self.http_session)
        self.hitokoto_api.set_session(self.http_session)
        self.holiday_api.set_session(self.http_session)
        self.zaobao_api.set_session(self.http_session)
        self.history_api.set_session(self.http_session)
        self.duji_api.set_session(self.http_session)
        self.aa1_api.set_session(self.http_session)
        self.english_api.set_session(self.http_session)
        self.milora_api.set_session(self.http_session)
        self.xiaoapi_api.set_session(self.http_session)
        self.tangdouz_api.set_session(self.http_session)

    @filter.command("日报")
    async def daily_news(self, event: AstrMessageEvent):
        """生成日报"""
        # 输出 unified_msg_origin 并自动保存映射
        umo = event.unified_msg_origin
        logger.info(f"日报命令触发，unified_msg_origin: {umo}")

        # 自动学习群组的 unified_msg_origin
        group_id = self._extract_group_id(umo)
        if group_id and group_id not in self.group_umo_mapping:
            self.group_umo_mapping[group_id] = umo
            self._save_group_mapping()
            logger.info(f"已学习群组 {group_id} 的 unified_msg_origin: {umo}")

        image_path = None
        try:
            image_path = await self._generate_daily_image()
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成日报时出错: {e}", exc_info=True)
            yield event.plain_result(f"生成日报时出错: {str(e)}")
        finally:
            # 清理临时图片文件
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.debug(f"已清理临时图片文件: {image_path}")
                except Exception as e:
                    logger.warning(f"清理临时图片文件失败: {e}")

    @filter.command("日报群组ID")
    async def get_group_id(self, event: AstrMessageEvent):
        """获取当前会话的群组ID，用于配置定时推送"""
        umo = event.unified_msg_origin
        logger.info(f"获取群组ID，unified_msg_origin: {umo}")
        yield event.plain_result(
            f"📋 当前会话信息：\n"
            f"unified_msg_origin: {umo}\n\n"
            f"💡 请将此值添加到插件配置的「定时推送目标群组列表」中"
        )

    @filter.command("歇后语")
    async def xiehouyu(self, event: AstrMessageEvent):
        """获取一条随机歇后语（ALAPI 接口）"""
        try:
            data = await self.alapi.get_xiehouyu()
            if data and data.get("riddle"):
                yield event.plain_result(
                    f"🔮 {data['riddle']}\n👉 {data.get('answer', '')}"
                )
            else:
                yield event.plain_result("❌ 歇后语获取失败，请稍后再试")
        except Exception as e:
            logger.error(f"歇后语获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 歇后语获取失败: {e}")

    @filter.command("AI早报")
    async def milora_aidaily_cmd(self, event: AstrMessageEvent):
        """获取 Milora AI早报，使用命令默认参数，不读取日报模块配置。"""
        try:
            data = await self.milora_api.get_aidaily(max_count=12)
            if not data:
                yield event.plain_result("❌ AI早报获取失败，请稍后再试")
                return
            if data.get("type") == "image" and data.get("image_url"):
                yield event.plain_result(
                    f"📰 AI早报 {data.get('date') or ''}\n{data['image_url']}"
                )
                return
            lines = data.get("items") or []
            head = f"📰 AI早报 {data.get('date') or ''}".strip()
            body = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(lines))
            yield event.plain_result(f"{head}\n{body}" if body else head)
        except Exception as e:
            logger.error(f"AI早报获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ AI早报获取失败: {e}")

    @filter.command("追番")
    async def cartoon_cmd(self, event: AstrMessageEvent):
        """获取腾讯动漫今日更新列表。"""
        try:
            data = await self.xiaoapi_api.get_cartoon_updates()
            if not data or not data.get("items"):
                yield event.plain_result("❌ 今日追番获取失败，请稍后再试")
                return
            head = f"🎬 今日追番 {data.get('today') or ''}（{data.get('today_week') or ''}）"
            lines = [
                f"{i + 1}. {it['title']}（{it.get('type') or ''}）"
                f"{(' ' + it.get('up_time') or '') if it.get('up_time') else ''}"
                for i, it in enumerate(data["items"])
            ]
            yield event.plain_result(f"{head}\n" + "\n".join(lines))
        except Exception as e:
            logger.error(f"追番获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 追番获取失败: {e}")

    @filter.command("诗词")
    async def shici_cmd(self, event: AstrMessageEvent, keyword: str = ""):
        """搜索并返回一首诗词。"""
        kw = (keyword or "").strip() or "静夜思"
        try:
            data = await self.xiaoapi_api.get_shici(kw)
            if not data:
                yield event.plain_result(f"❌ 没找到「{kw}」相关诗词")
                return
            author = data.get("author") or ""
            dynasty = data.get("dynasty") or ""
            head = f"📜 {data['title']}"
            if author:
                head += f"　{author}" + (f"·{dynasty}" if dynasty else "")
            yield event.plain_result(f"{head}\n{data.get('content') or ''}")
        except Exception as e:
            logger.error(f"诗词获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 诗词获取失败: {e}")

    @filter.command("语录")
    async def yulu_cmd(self, event: AstrMessageEvent, keyword: str = ""):
        """获取一条语录，可选类型：经典/动漫/恋爱/鼓励/孤独/搞笑/友情/歌词。"""
        t = (keyword or "").strip()
        try:
            data = await self.xiaoapi_api.get_yulu(t)
            if not data:
                yield event.plain_result("❌ 语录获取失败，请稍后再试")
                return
            text = data["text"]
            author = data.get("author") or ""
            from_ = data.get("from") or ""
            tail = author
            if from_:
                tail = f"{author}《{from_}》" if author else f"《{from_}》"
            yield event.plain_result(f"💬 {text}\n—— {tail}" if tail else f"💬 {text}")
        except Exception as e:
            logger.error(f"语录获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 语录获取失败: {e}")

    @filter.command("答题")
    async def quiz_cmd(self, event: AstrMessageEvent, keyword: str = ""):
        """知识答题：发送「答题」开始，发送「答题 我答+选项」作答。"""
        uid = str(event.unified_msg_origin or "default")
        msg = (keyword or "").strip() or "开始游戏"
        try:
            data = await self.xiaoapi_api.quiz_action(uid, msg)
            if not data:
                yield event.plain_result("❌ 答题获取失败，请稍后再试")
                return
            reply = data.get("msg") or ""
            if data.get("option"):
                reply += "\n" + data["option"]
            yield event.plain_result(f"🧠 {reply}")
        except Exception as e:
            logger.error(f"答题获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 答题获取失败: {e}")

    @filter.command("灯谜")
    async def riddle_cmd(self, event: AstrMessageEvent, keyword: str = ""):
        """猜灯谜：发送「灯谜」随机出题，发送「灯谜 答案」作答。"""
        uid = str(event.unified_msg_origin or "default")
        kw = (keyword or "").strip()
        try:
            if not kw:
                data = await self.xiaoapi_api.riddle_random(uid)
                if not data:
                    yield event.plain_result("❌ 灯谜获取失败，请稍后再试")
                    return
                self._riddle_state[uid] = data["id"]
                yield event.plain_result(
                    f"🏮 灯谜：{data['title']}\n（难度：{data.get('difficulty') or '未知'}）\n回复「灯谜 你的答案」作答"
                )
                return
            rid = self._riddle_state.get(uid)
            if rid is None:
                yield event.plain_result("❌ 请先发送「灯谜」开始")
                return
            data = await self.xiaoapi_api.riddle_verify(uid, rid, kw)
            if not data:
                yield event.plain_result("❌ 作答失败，请稍后再试")
                return
            if data["is_correct"]:
                reply = "🎉 答对啦！"
            else:
                reply = f"❌ 答错啦，正确答案是：{data['correct_answer']}"
            if data.get("msg"):
                reply += f"\n{data['msg']}"
            yield event.plain_result(reply)
        except Exception as e:
            logger.error(f"灯谜获取失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 灯谜获取失败: {e}")

    def _normalize_module_config(self, raw: dict) -> dict:
        """校验并归一化模块配置，与默认配置合并。

        Args:
            raw: 来自 modules.json 或编辑器提交的原始配置。

        Returns:
            归一化后的模块配置。
        """
        cfg = copy.deepcopy(DEFAULT_MODULE_CONFIG)
        if not isinstance(raw, dict):
            raw = {}
        raw_keys = set(raw.keys())
        for key in DEFAULT_MODULE_CONFIG:
            if raw.get(key) is not None:
                cfg[key] = copy.deepcopy(raw[key])

        # 摸鱼日历展示条数限制在 1-10
        if isinstance(cfg["moyu_items"], list):
            cfg["moyu_items"] = [
                it for it in cfg["moyu_items"] if isinstance(it, dict)
            ][:10]
        else:
            cfg["moyu_items"] = []

        if not isinstance(cfg.get("modules"), list):
            cfg["modules"] = []

        known_types = set(DEFAULT_MODULE_TITLES)

        # 旧版配置迁移：中部模块1/2 固定位并入统一中间模块列表（置于最前）
        if "mid1_source" in raw_keys or "mid2_source" in raw_keys:
            if "modules" not in raw_keys:
                cfg["modules"] = []
            existing_types = {
                m.get("type") for m in cfg["modules"] if isinstance(m, dict)
            }
            migrated = []
            for prefix in ("mid1", "mid2"):
                mtype = str(raw.get(f"{prefix}_source") or "").strip()
                # 该类型已在 modules 列表（或前一个槽位已迁移）时不重复迁移
                if mtype not in known_types or mtype in existing_types:
                    continue
                entry = {"type": mtype, "enabled": True}
                entry["title"] = (
                    str(raw.get(f"{prefix}_title") or "").strip()
                    or DEFAULT_MODULE_TITLES[mtype]
                )
                try:
                    count = int(raw.get(f"{prefix}_count") or 0)
                except (TypeError, ValueError):
                    count = 0
                if count >= 1:
                    entry["count"] = count
                params = raw.get(f"{prefix}_params")
                if isinstance(params, dict) and params:
                    entry["params"] = copy.deepcopy(params)
                migrated.append(entry)
                existing_types.add(mtype)
            cfg["modules"] = migrated + list(cfg["modules"])
            for prefix in ("mid1", "mid2"):
                for key in (
                    f"{prefix}_source",
                    f"{prefix}_title",
                    f"{prefix}_count",
                    f"{prefix}_params",
                ):
                    cfg.pop(key, None)

        valid_modules = []
        for raw_module in cfg["modules"]:
            if not isinstance(raw_module, dict):
                continue
            m = copy.deepcopy(raw_module)
            mtype = m.get("type")
            if mtype == "history":
                # 旧版配置迁移：历史上的今天已改为固定面板
                if "history_enabled" not in raw_keys:
                    cfg["history_enabled"] = bool(m.get("enabled", True))
                if "history_title" not in raw_keys and m.get("title"):
                    cfg["history_title"] = str(m["title"])
                if "history_count" not in raw_keys and m.get("count"):
                    cfg["history_count"] = m["count"]
                continue
            if mtype == "quote":
                # 旧版配置迁移：底栏引用已改为固定面板
                if "quote_enabled" not in raw_keys:
                    cfg["quote_enabled"] = bool(m.get("enabled", True))
                if "quote_sources" not in raw_keys and m.get("mode"):
                    cfg["quote_sources"] = [m["mode"]]
                continue
            if mtype == "countdown":
                # 旧版配置迁移：自定义倒计时已并入摸鱼日历，条目转为 custom 计时项
                legacy_items = m.get("items")
                if isinstance(legacy_items, list):
                    for item in legacy_items[:10]:
                        if not isinstance(item, dict):
                            continue
                        entry = {"type": "custom"}
                        if item.get("name"):
                            entry["name"] = str(item["name"])
                        if item.get("date"):
                            entry["date"] = str(item["date"])
                        if len(entry) > 1:
                            cfg["moyu_items"].append(entry)
                continue
            if mtype not in known_types:
                logger.warning(f"忽略非法模块配置: {m}")
                continue
            m["enabled"] = bool(m.get("enabled", True))
            m["title"] = str(m.get("title") or DEFAULT_MODULE_TITLES[mtype])
            if mtype in DEFAULT_MODULE_COUNTS:
                # 条数上限按模块能力取 count_max，其余模块统一最多 30 条
                count_max = MODULE_TYPE_META[mtype].get("count_max", 30)
                try:
                    m["count"] = max(
                        1,
                        min(int(m.get("count", DEFAULT_MODULE_COUNTS[mtype])), count_max),
                    )
                except (TypeError, ValueError):
                    m["count"] = DEFAULT_MODULE_COUNTS[mtype]
            # 归一化接口请求参数（仅带请求参数的模块才写入 params 字段）
            if mtype in MODULE_PARAM_SCHEMA:
                m["params"] = self._normalize_module_params(mtype, m.get("params"))
            else:
                m.pop("params", None)
            valid_modules.append(m)
        cfg["modules"] = valid_modules

        # 摸鱼日历计时项：清洗类型/自定义文字，兼容旧版 weekly 名称，最多 10 条
        valid_moyu = []
        for item in cfg["moyu_items"]:
            itype = item.get("type")
            if itype == "weekly":
                # 旧版字段迁移：weekly 更名为 weekend，仅保留周六/周日
                itype = "weekend"
            if itype is None:
                itype = "custom" if item.get("date") else "holiday"
            entry = {"type": itype}
            if itype == "weekend":
                try:
                    weekday = int(item.get("weekday", 6))
                except (TypeError, ValueError):
                    weekday = 6
                entry["weekday"] = weekday if weekday in (6, 7) else 6
            if itype in ("custom", "weekend"):
                entry["name"] = str(item.get("name") or "").strip()
                entry["prefix"] = str(item.get("prefix") or "").strip()
                entry["suffix"] = str(item.get("suffix") or "").strip()
            if itype == "custom":
                entry["date"] = str(item.get("date") or "").strip()
            valid_moyu.append(entry)
        cfg["moyu_items"] = valid_moyu[:10]

        cfg["history_enabled"] = bool(cfg["history_enabled"])
        cfg["history_title"] = str(cfg["history_title"] or "历史上的今天")
        try:
            cfg["history_count"] = max(1, int(cfg.get("history_count", 4)))
        except (TypeError, ValueError):
            cfg["history_count"] = 4

        # ---- 顶部模块位：单选来源校验 ----
        if cfg.get("top_source") not in TOP_SOURCE_LABELS:
            # 旧版配置迁移：未设置 top_source 但启用了历史面板 → 沿用历史
            cfg["top_source"] = "history"
        cfg["top_params"] = self._normalize_module_params(
            cfg["top_source"], cfg.get("top_params")
        )
        # 每日英语单词展示数量：1-5（接口单次最多 5 个单词）
        try:
            cfg["top_english_count"] = max(1, min(int(cfg.get("top_english_count", 1)), 5))
        except (TypeError, ValueError):
            cfg["top_english_count"] = 1
        # 主题：仅接受预设 key，未知值回退默认主题
        cfg["theme"] = (
            cfg.get("theme") if cfg.get("theme") in THEME_PRESETS else DEFAULT_THEME
        )
        if cfg["top_source"] != "history":
            # 选择了英语/汇率来源时，顶部展示新来源而非历史面板
            cfg["history_enabled"] = False
        # 实时汇率参数：一个源货币 + 多个目标货币
        cfg["exchange_from"] = (
            str(cfg.get("exchange_from") or "USD").strip().upper()[:3] or "USD"
        )
        if "exchange_targets" in raw_keys:
            raw_targets = cfg.get("exchange_targets")
        elif "exchange_to" in raw_keys:
            # 旧版配置迁移：仅配置了 exchange_to 单值 → 目标货币列表
            raw_targets = [raw.get("exchange_to")]
        else:
            raw_targets = cfg.get("exchange_targets")
        targets = []
        for t in raw_targets:
            code = str(t or "").strip().upper()[:3]
            if code and code not in targets and code != cfg["exchange_from"]:
                targets.append(code)
        cfg["exchange_targets"] = targets[:6]
        cfg.pop("exchange_to", None)
        try:
            cfg["exchange_amount"] = max(0.01, float(cfg.get("exchange_amount", 100)))
        except (TypeError, ValueError):
            cfg["exchange_amount"] = 100.0

        cfg["quote_enabled"] = bool(cfg["quote_enabled"])
        cfg["quote_title"] = str(cfg.get("quote_title") or "")
        sources = cfg["quote_sources"]
        if not isinstance(sources, list):
            sources = []
        sources = [s for s in sources if s in QUOTE_SOURCE_LABELS]
        cfg["quote_sources"] = sources or ["hitokoto"]
        return cfg

    @staticmethod
    def _normalize_module_params(mtype: str, raw) -> dict:
        """按模块类型归一化接口请求参数，缺失字段补默认值。

        Args:
            mtype: 模块类型。
            raw: 原始 params 字典，可为 None。

        Returns:
            归一化后的参数字典（仅含该模块 schema 中声明的字段）。
        """
        schema = MODULE_PARAM_SCHEMA.get(mtype) or []
        if not isinstance(raw, dict):
            raw = {}
        out = {}
        for field in schema:
            key = field["key"]
            val = raw.get(key)
            if val is None or str(val).strip() == "":
                val = field.get("default", "")
            out[key] = str(val).strip()
        return out

    def _load_module_config(self) -> dict:
        """读取模块配置 modules.json（每次生成都重新读取，修改后无需重载插件）。

        Returns:
            校验合并后的模块配置。
        """
        cfg_file = os.path.join(self.data_dir, "modules.json")
        raw = {}
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                logger.warning(f"读取 modules.json 失败，使用默认模块配置: {e}")

        cfg = self._normalize_module_config(raw)

        if not os.path.exists(cfg_file):
            self._save_module_config(cfg)
            logger.info(f"已生成默认模块配置文件: {cfg_file}")
        return cfg

    def _save_module_config(self, cfg: dict):
        """保存模块配置到数据目录的 modules.json。

        Args:
            cfg: 模块配置字典。
        """
        try:
            cfg_file = os.path.join(self.data_dir, "modules.json")
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存 modules.json 失败: {e}")

    def _register_web_apis(self, context: Context) -> None:
        """注册日报编辑器 Page 所需的 Web API。"""
        base = "/astrbot_plugin_zhenxunribao"
        routes = [
            (f"{base}/modules", self.api_get_modules, ["GET"], "Get daily news module config"),
            (f"{base}/modules/save", self.api_save_modules, ["POST"], "Save daily news module config"),
            (f"{base}/meta", self.api_get_meta, ["GET"], "Get module types and api param schema"),
            (f"{base}/preview", self.api_preview, ["POST"], "Render daily news preview image"),
        ]
        for route, handler, methods, desc in routes:
            context.register_web_api(route, handler, methods, desc)

    async def api_get_modules(self):
        """返回当前模块配置（modules.json 内容）。"""
        return json_response(self._load_module_config())

    async def api_get_meta(self):
        """返回编辑器所需的模块元数据：类型、分类、图标、接口参数 schema、短句来源、
        顶部模块位的候选来源，以及预设主题列表。"""
        return json_response(
            {
                "module_types": MODULE_TYPE_META,
                "module_categories": MODULE_CATEGORIES,
                "icons": MODULE_ICONS,
                "param_schema": MODULE_PARAM_SCHEMA,
                "quote_sources": QUOTE_SOURCE_LABELS,
                "top_sources": TOP_SOURCE_LABELS,
                "theme_presets": THEME_PRESETS,
            }
        )


    async def api_save_modules(self):
        """保存编辑器提交的模块配置。"""
        try:
            payload = await web_request.json(default=None)
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            return json_response(
                {"status": "error", "message": "请求体必须为 JSON 对象"}
            )
        cfg = self._normalize_module_config(payload)
        self._save_module_config(cfg)
        logger.info("已通过日报编辑器保存模块配置")
        return json_response(cfg)



    async def api_preview(self):
        """渲染一张日报预览图，返回 base64 data URL。"""
        image_path = None
        try:
            image_path = await self._generate_daily_image()
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()
            return json_response({"image": f"data:image/png;base64,{image_b64}"})
        except Exception as e:
            logger.error(f"生成日报预览失败: {e}", exc_info=True)
            return json_response({"status": "error", "message": f"生成预览失败: {e}"})
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

    def _resolve_timer_rows(
        self, items: list, holiday_pool: list | None = None
    ) -> list:
        """把摸鱼日历计时项配置解析为展示行。

        Args:
            items: 计时项列表，每项为
                {"type": "holiday"|"custom"|"weekend", "name", "prefix", "suffix", ...}。
            holiday_pool: 节假日数据（按顺序供 holiday 类型计时项消费），无则为 None。

        Returns:
            展示行列表，每项为
            {"name": ..., "days": ..., "prefix": ..., "suffix": ...}：
            suffix 默认按正/倒计时取「过了」或「还剩」，可由计时项自定义。
        """
        rows = []
        next_holiday = 0
        for item in items:
            # 兼容省略 type 的旧配置：带 date 即视为自定义计时
            itype = item.get("type") or ("custom" if item.get("date") else "holiday")
            if itype == "weekly":
                itype = "weekend"
            row = None
            if itype == "holiday":
                if holiday_pool and next_holiday < len(holiday_pool):
                    holiday = holiday_pool[next_holiday]
                    next_holiday += 1
                    row = {
                        "name": holiday.get("name") or "节假日",
                        "days": str(abs(int(holiday.get("days_left", 0)))),
                        "countup": False,
                    }
            elif itype == "custom":
                days = days_until_date(item.get("date", ""))
                if days is not None:
                    row = {
                        "name": item.get("name") or "自定义计时",
                        "days": str(abs(days)),
                        "countup": days < 0,
                    }
            elif itype == "weekend":
                weekday = item.get("weekday", 6)
                try:
                    weekday = int(weekday)
                except (TypeError, ValueError):
                    weekday = 6
                if weekday not in (6, 7):
                    weekday = 6
                row = {
                    "name": item.get("name") or ("周六" if weekday == 6 else "周日"),
                    "days": str(days_until_weekday(weekday)),
                    "countup": False,
                }
            else:
                logger.warning(f"忽略无法解析的计时项: {item}")
                continue
            if row:
                # 前后段文字可自定义，留空则使用默认文案
                row["prefix"] = item.get("prefix") or "距离"
                row["suffix"] = item.get("suffix") or ("过了" if row["countup"] else "还剩")
                row.pop("countup", None)
                rows.append(row)
        return rows

    async def _fetch_quote_text(self, source: str) -> dict | None:
        """获取底栏短句内容，免费接口失败时走 ALAPI 兜底。

        Args:
            source: 短句来源，见 QUOTE_SOURCE_LABELS。

        Returns:
            {"title": ..., "text": ..., "from": ...}，来源不可用返回 None。
        """
        title = QUOTE_SOURCE_LABELS.get(source, "今日一言")
        text, from_ = None, ""

        if source == "hitokoto":
            try:
                data = await self.hitokoto_api.get_hitokoto_async()
            except Exception:
                data = None
            if isinstance(data, dict) and data.get("hitokoto"):
                text = str(data["hitokoto"]).strip()
                from_ = str(data.get("from", "") or "").strip()
                if not from_ or from_ == "网络":
                    from_ = "佚名"
        elif source == "duji":
            text = await self.duji_api.get_today_duji_async()
            text = text.strip() if text else ""
        elif source == "sjyy":
            # 糖豆子随机一言（纯文本接口）
            text = await self.tangdouz_api.get_random_quote()
            text = text.strip() if text else ""
        elif source == "riddle":
            # 随机谜语：日报只展示谜面，答案不展示
            data = await self.tangdouz_api.get_riddle()
            if data:
                text = data.get("mimian") or ""
                from_ = data.get("type") or ""
        elif source == "xiehouyu":
            # 歇后语无免费通道，直接走 ALAPI
            text, from_ = await self.alapi.get_quote_text("xiehouyu")
        else:
            # mingyan / tiangou / gaoxiao：aa1.cn 免费接口为主
            text = await self.aa1_api.get_text_async(source)
            if not text and source == "mingyan":
                # 名人名言 ALAPI 兜底
                text, from_ = await self.alapi.get_quote_text("mingyan")

        if not text:
            return None
        return {
            "title": title,
            "text": text,
            "from": from_,
            # 谜语来源用专用谜面样式渲染（不套引号），其余短句走引用样式
            "is_riddle": source == "riddle",
        }

    async def _generate_daily_image(self) -> str:
        logger.info("开始生成日报")

        module_cfg = self._load_module_config()
        date_info = get_current_date_info()
        (
            moyu_rows,
            history_events,
            module_views,
            quote_data,
            exchange_data,
        ) = await self._fetch_all_data(module_cfg)

        # 顶部模块视图：根据 top_source 组装（english/exchange 复用 module_views 渲染）
        top_view = None
        top_source = module_cfg.get("top_source")
        if top_source == "history":
            top_view = (
                {
                    "type": "history",
                    "title": module_cfg["history_title"],
                    "events": history_events,
                }
                if history_events
                else None
            )
        elif top_source == "english":
            for v in module_views:
                if v["type"] == "english":
                    top_view = v
                    break
        elif top_source == "exchange" and exchange_data:
            top_view = {
                "type": "exchange",
                "title": "实时汇率",
                "data": exchange_data,
            }

        template_data = {
            "date_info": date_info,
            "moyu_rows": moyu_rows,
            "moyu_title": module_cfg.get("moyu_title") or "摸鱼日历",
            "top_view": top_view,
            "top_source": top_source,
            "history_title": module_cfg.get("history_title") or "历史上的今天",
            "other_modules": [
                view for view in module_views if view.get("slot") != "top"
            ],
            "quote": quote_data,
            "icons": MODULE_ICONS,
        }

        logger.info(
            f"模块数据准备完成: 摸鱼计时={len(moyu_rows)}条, "
            f"顶部={top_source}:{top_view is not None}, "
            f"模块={[v['type'] for v in module_views]}, 底栏引用={'有' if quote_data else '无'}"
        )

        try:
            with open(self.template_path, encoding="utf-8") as f:
                html_template_str = f.read()
        except Exception as e:
            logger.error(f"读取模板文件失败: {e}", exc_info=True)
            raise

        template = Template(html_template_str)
        rendered_html = template.render(**template_data)

        # 主题方案A：注入预设主题的 CSS 变量覆盖块，替换模板 :root 中的颜色。
        # 该块与 :root 同时存在时按层叠顺序覆盖同优先级变量。
        theme = THEME_PRESETS.get(
            module_cfg.get("theme"), THEME_PRESETS[DEFAULT_THEME]
        )
        theme_vars = ";".join(
            f"{THEME_CSS_VAR_NAMES[key]}:{theme['colors'][key]}"
            for key in THEME_CSS_VAR_NAMES
        )
        theme_override = f"<style>:root{{{theme_vars}}}</style>"
        rendered_html = rendered_html.replace("</head>", theme_override + "</head>", 1)

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
        logger.info("日报生成成功")
        return image_path

    async def _fetch_all_data(self, module_cfg: dict):
        """按模块配置并发抓取数据并组装为模板视图。

        Args:
            module_cfg: _load_module_config 返回的模块配置。

        Returns:
            (moyu_rows, history_events, module_views, quote_data, exchange_data)：
            摸鱼日历展示行、历史事件列表、模块视图、底部引用和汇率数据。
            顶部来源通过 slot 标记，避免重复进入自由模块视图。
        """
        modules = [m for m in module_cfg["modules"] if m["enabled"]]

        # 摸鱼日历：仅当存在节假日计时项时才请求节假日数据
        holiday_count = sum(
            1 for it in module_cfg["moyu_items"] if it.get("type") == "holiday"
        )
        holiday_pool = []
        if holiday_count:
            try:
                holiday_pool = await self.holiday_api.get_moyu_list_async(
                    max_count=holiday_count
                )
            except Exception as e:
                logger.warning(f"节假日数据获取失败: {e}")

        # 固定面板与可排序模块统一并发抓取：(类型, 对应模块配置或 None, 协程)
        tasks = []
        if module_cfg["top_source"] == "history" and module_cfg["history_enabled"]:
            tasks.append(
                (
                    "history",
                    None,
                    self.history_api.get_today_history_async(
                        max_count=module_cfg["history_count"]
                    ),
                )
            )
        elif module_cfg["top_source"] == "english":
            tasks.append(
                (
                    "english",
                    {
                        "title": "每日英语",
                        "count": module_cfg["top_english_count"],
                        "slot": "top",
                    },
                    self.english_api.get_words_async(
                        max_count=module_cfg["top_english_count"]
                    ),
                )
            )
        elif module_cfg["top_source"] == "exchange":
            targets = module_cfg.get("exchange_targets") or []
            for target in targets:
                tasks.append(
                    (
                        "exchange",
                        {"to": target},
                        self.tangdouz_api.get_exchange_rate(
                            from_currency=module_cfg["exchange_from"],
                            to_currency=target,
                            amount=module_cfg["exchange_amount"],
                        ),
                    )
                )
        if module_cfg["quote_enabled"]:
            source = random.choice(module_cfg["quote_sources"])
            tasks.append(("quote", None, self._fetch_quote_text(source)))

        # ---- 中间模块：统一列表，按顺序并发抓取 ----
        for m in modules:
            mtype = m["type"]
            if mtype == "anime":
                tasks.append(
                    (
                        "anime",
                        m,
                        self.bgm_api.get_today_anime_async(max_count=m["count"]),
                    )
                )
            elif mtype == "news":
                tasks.append(
                    (
                        "news",
                        m,
                        self.zaobao_api.get_world_news_async(max_count=m["count"]),
                    )
                )
            elif mtype == "english":
                tasks.append(
                    (
                        "english",
                        m,
                        self.english_api.get_words_async(max_count=m["count"]),
                    )
                )
            elif mtype == "essay":
                tasks.append(
                    (
                        "essay",
                        m,
                        self.alapi.get_daily_essay(),
                    )
                )
            elif mtype == "aidaily":
                params = m.get("params") or {}
                tasks.append(
                    (
                        "aidaily",
                        m,
                        self.milora_api.get_aidaily(
                            max_count=m.get("count", 10),
                            rtype=params.get("type", ""),
                            date=params.get("date", ""),
                        ),
                    )
                )
            elif mtype == "hbox":
                tasks.append(
                    (
                        "hbox",
                        m,
                        self.tangdouz_api.get_hot_games(max_count=m["count"]),
                    )
                )
            elif mtype == "cartoon":
                params = m.get("params") or {}
                tasks.append(
                    (
                        "cartoon",
                        m,
                        self.xiaoapi_api.get_cartoon_updates(
                            date_str=params.get("date", "")
                        ),
                    )
                )
            elif mtype == "shici":
                params = m.get("params") or {}
                tasks.append(
                    (
                        "shici",
                        m,
                        self.xiaoapi_api.get_shici(
                            params.get("keyword", "") or "静夜思"
                        ),
                    )
                )
            elif mtype == "yulu":
                params = m.get("params") or {}
                tasks.append(
                    (
                        "yulu",
                        m,
                        self.xiaoapi_api.get_yulu(params.get("type", "")),
                    )
                )
            else:
                # countdown 等纯配置模块无需网络请求
                tasks.append((mtype, m, asyncio.sleep(0, result=None)))

        results = await asyncio.gather(
            *(coro for _, _, coro in tasks), return_exceptions=True
        )

        history_events: list = []
        quote_data = None
        module_views = []
        exchange_rows: list = []
        for (kind, m, _), res in zip(tasks, results):
            if isinstance(res, Exception):
                logger.warning(f"{kind} 数据获取失败: {res}")
                res = None
            if kind == "history":
                history_events = res or []
            elif kind == "exchange":
                if isinstance(res, dict) and res.get("result") is not None:
                    exchange_rows.append(res)
            elif kind == "quote":
                quote_data = res
            else:
                data = res if res is not None else []
                if kind == "hbox":
                    data = (res or {}).get("games") if isinstance(res, dict) else None
                elif kind == "cartoon" and isinstance(data, dict):
                    data["items"] = (data.get("items") or [])[: max(1, int(m.get("count", 6)))]
                elif kind in ("essay", "shici", "yulu") and isinstance(data, dict):
                    data = [data]
                if data:
                    module_views.append(
                        {
                            "type": kind,
                            "title": m["title"],
                            "data": data,
                            **({"slot": m["slot"]} if m.get("slot") else {}),
                        }
                    )
                else:
                    logger.warning(f"模块 {kind}({m['title']}) 无数据，本次跳过")

        exchange_data = None
        if exchange_rows:
            exchange_data = {
                "from": module_cfg["exchange_from"],
                "amount": module_cfg["exchange_amount"],
                "rows": exchange_rows,
            }

        moyu_rows = self._resolve_timer_rows(
            module_cfg["moyu_items"], holiday_pool=holiday_pool
        )
        return moyu_rows, history_events, module_views, quote_data, exchange_data

    def _file_to_base64(self, file_path: str) -> str | None:
        try:
            if not os.path.exists(file_path):
                logger.warning(f"资源文件不存在: {file_path}")
                return None

            with open(file_path, "rb") as f:
                file_data = f.read()
                base64_data = base64.b64encode(file_data).decode("utf-8")

                ext = os.path.splitext(file_path)[1].lower()
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
                mime_type = mime_types.get(ext, "application/octet-stream")

                return f"data:{mime_type};base64,{base64_data}"
        except Exception as e:
            logger.warning(f"转换文件到base64失败 {file_path}: {e}")
            return None

    async def _embed_resources(self, html_template: str) -> str:
        def replace_font(match):
            filename = match.group(1)
            file_path = os.path.join(self.plugin_dir, "res", "font", filename)
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
                file_path = os.path.join(self.plugin_dir, "res", filepath)
                base64_uri = self._file_to_base64(file_path)
                if base64_uri:
                    logger.debug(f"转换图片为base64: {filepath}")
                    return f'src="{base64_uri}"'
                else:
                    logger.warning(f"图片转换为base64失败: {filepath}")
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

        提升清晰度的关键：使用 BrowserContext 的 device_scale_factor (DPR)。
        """
        temp_html_path = None
        context = None
        try:
            temp_dir = tempfile.gettempdir()
            temp_html_path = os.path.join(
                temp_dir,
                f"zhenxun_daily_{uuid.uuid4().hex}.html",
            )
            with open(temp_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            if output_path is None:
                output_path = temp_html_path.replace(".html", ".png")

            # DPR (device scale factor): 越大越清晰，但图片更大、渲染更慢
            dpr = int(self.config.get("render_dpr", 4))
            dpr = max(1, min(dpr, 6))

            async with async_playwright() as p:
                logger.info("启动Playwright浏览器...")
                browser = await p.chromium.launch(headless=True)
                try:
                    # 用 context 设置 DPR 提升截图清晰度
                    context = await browser.new_context(
                        viewport={"width": 1156, "height": 1000},
                        device_scale_factor=dpr,
                    )
                    page = await context.new_page()

                    file_url = f"file://{pathname2url(temp_html_path)}"
                    await page.goto(file_url, wait_until="networkidle")
                    await page.wait_for_timeout(2000)

                    wrapper = await page.query_selector(".wrapper")
                    if not wrapper:
                        raise Exception("未找到.wrapper元素")

                    box = await wrapper.bounding_box()
                    if not box:
                        raise Exception("无法获取.wrapper元素的bounding box")

                    wrapper_width = int(box["width"])
                    wrapper_height = int(box["height"])

                    # 动态设置 viewport，避免超长内容截图不完整（留余量）
                    viewport_height = max(int(wrapper_height * 1.2), 1000)
                    viewport_width = 1156
                    await page.set_viewport_size(
                        {"width": viewport_width, "height": viewport_height}
                    )

                    # viewport 调整后重新查询元素和 bounding box
                    await page.wait_for_timeout(300)  # 等待 reflow 完成
                    wrapper = await page.query_selector(".wrapper")
                    if not wrapper:
                        raise Exception("未找到.wrapper元素(viewport调整后)")

                    box = await wrapper.bounding_box()
                    if not box:
                        raise Exception(
                            "无法获取.wrapper元素的bounding box(viewport调整后)"
                        )

                    logger.info(
                        f"Wrapper宽高: {int(box['width'])}x{int(box['height'])}, "
                        f"viewport: {viewport_width}x{viewport_height}, DPR={dpr}"
                    )

                    # 使用 clip 精确裁剪，避免 body absolute 定位导致的大片空白
                    clip = {
                        "x": int(box["x"]),
                        "y": int(box["y"]),
                        "width": int(box["width"]),
                        "height": int(box["height"]),
                    }
                    await page.screenshot(
                        path=output_path,
                        type="png",
                        clip=clip,
                    )

                    logger.info(f"截图完成: {output_path}")
                    return output_path
                finally:
                    try:
                        if context:
                            await context.close()
                    finally:
                        await browser.close()

        except Exception as e:
            logger.error(f"Playwright渲染失败: {e}", exc_info=True)
            raise
        finally:
            if temp_html_path and os.path.exists(temp_html_path):
                try:
                    os.remove(temp_html_path)
                except Exception as e:
                    logger.warning(f"删除临时HTML文件失败: {e}")

    async def _scheduled_push_task(self):
        """定时推送调度器。

        每个周期重新读取配置，使配置变更能较快生效；使用当日推送标记
        避免同一天重复推送。
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
                    logger.debug("定时推送已启用，但未配置目标群组")
                    await asyncio.sleep(60)
                    continue

                push_time_str = self.config.get("scheduled_push_time", "08:00")
                try:
                    hour, minute = map(int, str(push_time_str).split(":"))
                    push_time = time(hour, minute)
                except (ValueError, AttributeError):
                    logger.error(
                        f"定时推送时间格式错误: {push_time_str}，使用默认时间08:00"
                    )
                    push_time = time(8, 0)

                now = datetime.now()
                due = now >= datetime.combine(now.date(), push_time)
                if due and last_push_date != now.date():
                    last_push_date = now.date()
                    logger.info("开始执行定时推送")
                    await self._push_daily_to_groups(push_groups)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.info("定时推送任务已取消")
                break
            except Exception as e:
                logger.error(f"定时推送任务出错: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _push_daily_to_groups(self, group_list: list):
        """向配置的目标会话推送日报。

        统一通过 context.send_message 发送，兼容所有平台适配器；目标可以
        是 unified_msg_origin，也可以是 /日报 使用中学习到的纯群号。

        Args:
            group_list: 推送目标列表（unified_msg_origin 或纯群号）。
        """
        image_path = None
        try:
            logger.info(f"开始生成日报图片，目标数量: {len(group_list)}")
            image_path = await self._generate_daily_image()
            if not image_path or not os.path.exists(image_path):
                logger.error(f"日报图片生成失败或文件不存在: {image_path}")
                return

            greeting = await self._generate_greeting_text()

            success_count = 0
            for entry in group_list:
                umo = self._resolve_umo(entry)
                if not umo:
                    logger.warning(
                        f"无法解析推送目标 '{entry}' 的 unified_msg_origin。"
                        f"请先在目标群发送 /日报 让插件学习，或直接配置完整 "
                        f"unified_msg_origin（见 /日报群组ID）。"
                    )
                    continue
                try:
                    message_chain = MessageChain()
                    if greeting:
                        message_chain.message(greeting)
                    message_chain.file_image(image_path)
                    sent = await self.context.send_message(umo, message_chain)
                    if sent:
                        success_count += 1
                        logger.info(f"成功推送日报到会话: {umo}")
                    else:
                        logger.warning(f"没有匹配的平台可以发送到会话: {umo}")
                except Exception as e:
                    logger.error(f"推送到会话 {umo} 时出错: {e}", exc_info=True)

            logger.info(f"定时推送完成，成功: {success_count}/{len(group_list)}")
        except Exception as e:
            logger.error(f"定时推送日报失败: {e}", exc_info=True)
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.debug(f"已清理临时图片文件: {image_path}")
                except Exception as e:
                    logger.warning(f"清理临时图片文件失败: {e}")

    def _resolve_umo(self, entry: str) -> str | None:
        """把配置的推送目标解析为 unified_msg_origin。

        Args:
            entry: unified_msg_origin 字符串，或此前从 /日报 学习到的纯群号。

        Returns:
            解析出的 unified_msg_origin；无法解析时返回 None。
        """
        entry = str(entry).strip()
        if ":" in entry:
            return entry
        return self.group_umo_mapping.get(self._extract_group_id(entry))

    def _load_group_mapping(self):
        """从文件加载群号到 unified_msg_origin 的映射"""
        try:
            import json

            # 使用标准数据目录，避免写入插件源码目录
            data_dir = StarTools.get_data_dir("astrbot_plugin_zhenxunribao")
            mapping_file = os.path.join(data_dir, "group_mapping.json")
            if os.path.exists(mapping_file):
                with open(mapping_file, encoding="utf-8") as f:
                    self.group_umo_mapping = json.load(f)
                logger.info(f"已加载 {len(self.group_umo_mapping)} 个群组映射")
        except Exception as e:
            logger.warning(f"加载群组映射失败: {e}")
            self.group_umo_mapping = {}

    def _save_group_mapping(self):
        """保存群号到 unified_msg_origin 的映射到文件"""
        try:
            import json

            # 使用标准数据目录，避免写入插件源码目录
            data_dir = StarTools.get_data_dir("astrbot_plugin_zhenxunribao")
            mapping_file = os.path.join(data_dir, "group_mapping.json")
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump(self.group_umo_mapping, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存 {len(self.group_umo_mapping)} 个群组映射")
        except Exception as e:
            logger.warning(f"保存群组映射失败: {e}")

    def _extract_group_id(self, group_id_str: str) -> str:
        """从配置中提取纯群号，支持多种格式"""
        group_id_str = str(group_id_str).strip()

        # 如果是纯数字，直接返回
        if group_id_str.isdigit():
            return group_id_str

        # 尝试从 unified_msg_origin 格式中提取群号
        # 格式如: aiocqhttp:GroupMessage:123456789 或 default:GroupMessage:xxx_123456789
        if ":" in group_id_str:
            parts = group_id_str.split(":")
            if len(parts) >= 3:
                last_part = parts[-1]
                # 处理可能的 botid_groupid 格式
                if "_" in last_part:
                    return last_part.split("_")[-1]
                return last_part

        return group_id_str

    async def _generate_greeting_text(self) -> str:
        """使用 AI 生成个性化的推送文本"""
        try:
            # 获取当前时间和节日信息
            from datetime import datetime

            now = datetime.now()
            hour = now.hour
            date_info = get_current_date_info()

            # 获取节假日信息
            moyu_list = []
            try:
                holiday_data = await self.holiday_api.get_moyu_list_async(max_count=1)
                if holiday_data and len(holiday_data) > 0:
                    moyu_list = holiday_data
            except:
                pass

            # 检查是否启用 AI 生成问候语
            if not self.config.get("enable_ai_greeting", False):
                return self._get_default_greeting(hour, moyu_list)

            # 构建 prompt
            prompt_parts = [
                f"现在是{date_info['date_str']} {date_info['week_cn']}",
                f"时间是{hour}点",
            ]

            if moyu_list:
                holiday_names = [h.get("name", "") for h in moyu_list if h.get("name")]
                if holiday_names:
                    prompt_parts.append(
                        f"即将到来的节日：{', '.join(holiday_names[:2])}"
                    )

            if (
                date_info.get("cn_date_str")
                and date_info.get("cn_date_str") != "农历未知"
            ):
                prompt_parts.append(f"农历{date_info['cn_date_str']}")

            prompt = (
                f"{', '.join(prompt_parts)}。"
                f"请生成一句简短（15字以内）、温馨且富有创意的日报推送问候语。"
                f"要求：1. 结合时间或节日 2. 亲切自然 3. 带上真寻的口吻 4. 只返回问候语文本，不要其他内容"
            )

            # 尝试获取 LLM 提供商
            try:
                # 获取默认的聊天提供商
                umo_for_provider = None
                # 尝试从已学习的群映射里取一个会话ID，以便获取当前会话默认聊天模型
                if self.group_umo_mapping:
                    umo_for_provider = next(iter(self.group_umo_mapping.values()))
                provider_id = (
                    await self.context.get_current_chat_provider_id(
                        umo=umo_for_provider
                    )
                    if umo_for_provider
                    else None
                )
                if not provider_id:
                    # 如果没有，取平台供应商实例中的第一个
                    insts = self.context.provider_manager.get_insts()
                    if insts:
                        provider_id = insts[0].meta().id

                if provider_id:
                    llm_resp = await self.context.llm_generate(
                        chat_provider_id=provider_id,
                        prompt=prompt,
                    )

                    if llm_resp and hasattr(llm_resp, "completion_text"):
                        greeting = llm_resp.completion_text.strip()
                        # 清理可能的引号
                        greeting = greeting.strip('"').strip("'").strip()
                        if greeting and len(greeting) <= 50:
                            logger.info(f"AI 生成问候语: {greeting}")
                            return f"📰 {greeting}\n"
            except Exception as e:
                logger.debug(f"AI 生成问候语失败: {e}")

            # 回退到默认问候语
            return self._get_default_greeting(hour, moyu_list)

        except Exception as e:
            logger.warning(f"生成问候语出错: {e}")
            return "📰 真寻日报来啦~\n"

    def _get_default_greeting(self, hour: int, moyu_list: list) -> str:
        """获取默认问候语（无 AI 时使用）"""
        # 根据时间段选择问候语
        greetings = {
            "morning": [
                "早安！新的一天开始啦~",
                "早上好！今日份日报送达~",
                "早安！美好的一天从日报开始~",
            ],
            "noon": [
                "中午好！午间日报来啦~",
                "中午好~来看看今天的资讯吧~",
                "午安！休息时刻看看日报~",
            ],
            "afternoon": [
                "下午好！日报新鲜出炉~",
                "下午茶时间，看看日报吧~",
                "下午好！今日资讯已备好~",
            ],
            "evening": [
                "晚上好！晚间日报送达~",
                "晚上好~睡前看看今日资讯吧~",
                "晚安前的日报时间~",
            ],
        }

        # 判断时间段
        if 5 <= hour < 11:
            period_greetings = greetings["morning"]
        elif 11 <= hour < 14:
            period_greetings = greetings["noon"]
        elif 14 <= hour < 18:
            period_greetings = greetings["afternoon"]
        else:
            period_greetings = greetings["evening"]

        # 如果有节日信息，添加节日问候
        if moyu_list and len(moyu_list) > 0:
            holiday = moyu_list[0]
            if holiday.get("name"):
                days_left = holiday.get("days", "")
                if days_left == "0":
                    return f"📰 {holiday['name']}快乐！日报送上~\n"
                elif days_left and int(days_left) <= 3:
                    return f"📰 距离{holiday['name']}还有{days_left}天！日报来啦~\n"

        # 随机选择一个问候语
        import random

        return f"📰 {random.choice(period_greetings)}\n"

    async def terminate(self):
        logger.info("真寻日报插件正在卸载...")
        # 取消定时推送任务
        if self.push_task and not self.push_task.done():
            self.push_task.cancel()
            try:
                await self.push_task
            except asyncio.CancelledError:
                pass
            logger.info("定时推送任务已取消")
        # 关闭共享的 HTTP session
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("HTTP session 已关闭")
