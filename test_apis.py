#!/usr/bin/env python3
"""
API 测试脚本
用于验证所有 API 接口是否正常工作

用法:
    python test_apis.py [ALAPI_TOKEN]

ALAPI_TOKEN 可选，用于测试需要 Token 的备用/主数据源接口。
"""
import asyncio
import sys
import os
import logging

import aiohttp

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# 模拟 astrbot.api.logger
class MockLogger:
    def info(self, msg):
        logging.info(msg)
    def debug(self, msg):
        logging.debug(msg)
    def warning(self, msg):
        logging.warning(msg)
    def error(self, msg, exc_info=False):
        logging.error(msg, exc_info=exc_info)

# 创建一个临时的 astrbot 模块结构
sys.modules['astrbot'] = type(sys)('astrbot')
sys.modules['astrbot.api'] = type(sys)('astrbot.api')
sys.modules['astrbot'].api = sys.modules['astrbot.api']
sys.modules['astrbot.api'].logger = MockLogger()

# 添加插件目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.bgm_api import BGMAPI
from api.hitokoto_api import HitokotoAPI
from api.holiday_api import HolidayAPI
from api.history_api import HistoryAPI
from api.zaobao_api import ZaobaoAPI
from api.duji_api import DujiAPI


async def test_bgm_api(session):
    """测试 Bangumi 新番 API"""
    print("\n" + "="*50)
    print("测试 Bangumi 新番 API")
    print("="*50)

    api = BGMAPI(session=session)
    try:
        result = await api.get_today_anime_async(max_count=3)
        if result:
            print(f"✅ 成功获取 {len(result)} 条新番数据")
            for i, anime in enumerate(result[:3], 1):
                print(f"  {i}. {anime.get('title', 'N/A')}")
        else:
            print("⚠️  未获取到新番数据（可能今天没有更新）")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def test_hitokoto_api(session, token):
    """测试今日一言 API"""
    print("\n" + "="*50)
    print("测试今日一言 API")
    print("="*50)

    api = HitokotoAPI(session=session, token=token)
    try:
        result = await api.get_hitokoto_async()
        if result and result.get('hitokoto'):
            print(f"✅ 成功获取一言数据")
            print(f"  内容: {result['hitokoto']}")
            print(f"  出处: {result['from']}")
        else:
            print("❌ 未获取到一言数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def test_holiday_api(session, token):
    """测试节假日 API"""
    print("\n" + "="*50)
    print("测试节假日 API")
    print("="*50)

    api = HolidayAPI(session=session, token=token)
    try:
        result = await api.get_moyu_list_async(max_count=3)
        if result:
            print(f"✅ 成功获取 {len(result)} 条节假日数据")
            for i, holiday in enumerate(result, 1):
                days = holiday.get('days_left', 'N/A')
                print(f"  {i}. {holiday.get('name', 'N/A')} (还有 {days} 天)")
        else:
            print("❌ 未获取到节假日数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def test_history_api(session, token):
    """测试历史上的今天 API（需要 ALAPI Token）"""
    print("\n" + "="*50)
    print("测试历史上的今天 API")
    print("="*50)

    if not token:
        print("⚠️  未提供 ALAPI Token，跳过测试")
        return

    api = HistoryAPI(session=session, token=token)
    try:
        result = await api.get_today_history_async(max_count=3)
        if result:
            print(f"✅ 成功获取 {len(result)} 条历史事件")
            for i, event in enumerate(result, 1):
                print(f"  {i}. {event.get('year', 'N/A')}年 {event.get('title', 'N/A')}")
        else:
            print("❌ 未获取到历史事件数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def test_zaobao_api(session, token):
    """测试早报/新闻 API"""
    print("\n" + "="*50)
    print("测试早报/新闻 API")
    print("="*50)

    api = ZaobaoAPI(session=session, token=token)
    try:
        result = await api.get_world_news_async(max_count=5)
        if result:
            print(f"✅ 成功获取 {len(result)} 条新闻")
            for i, news in enumerate(result, 1):
                print(f"  {i}. {news[:60]}..." if len(news) > 60 else f"  {i}. {news}")
        else:
            print("❌ 未获取到新闻数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def test_duji_api(session):
    """测试毒鸡汤 API"""
    print("\n" + "="*50)
    print("测试毒鸡汤 API")
    print("="*50)

    api = DujiAPI(session=session)
    try:
        result = await api.get_today_duji_async()
        if result:
            print(f"✅ 成功获取毒鸡汤")
            print(f"  内容: {result[:60]}")
        else:
            print("❌ 未获取到毒鸡汤数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def main():
    """运行所有测试"""
    token = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    print("\n" + "="*50)
    print("真寻日报插件 API 测试")
    print("="*50)
    print("正在测试所有 API 接口...")

    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await test_bgm_api(session)
        await test_hitokoto_api(session, token)
        await test_holiday_api(session, token)
        await test_history_api(session, token)
        await test_zaobao_api(session, token)
        await test_duji_api(session)

    print("\n" + "="*50)
    print("测试完成")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
