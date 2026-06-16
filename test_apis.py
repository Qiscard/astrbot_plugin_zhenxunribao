#!/usr/bin/env python3
"""
API 测试脚本
用于验证所有 API 接口是否正常工作
"""
import asyncio
import sys
import os
import logging

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
from api.bilibili_api import BilibiliAPI
from api.hitokoto_api import HitokotoAPI
from api.holiday_api import HolidayAPI
from api.ithome_rss import ITHomeRSS
from api.zaobao_api import ZaobaoAPI


async def test_bgm_api():
    """测试 Bangumi 新番 API"""
    print("\n" + "="*50)
    print("测试 Bangumi 新番 API")
    print("="*50)

    api = BGMAPI()
    try:
        result = await api.get_today_anime_async(max_count=3)
        if result and len(result) > 0:
            print(f"✅ 成功获取 {len(result)} 条新番数据")
            for i, anime in enumerate(result[:3], 1):
                print(f"  {i}. {anime.get('title', 'N/A')}")
        else:
            print("⚠️  未获取到新番数据（可能今天没有更新）")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        await api.close()


async def test_bilibili_api():
    """测试 Bilibili 热点 API"""
    print("\n" + "="*50)
    print("测试 Bilibili 热点 API")
    print("="*50)

    api = BilibiliAPI()
    try:
        result = await api.get_hotwords_async(max_count=4)
        if result and len(result) > 0:
            print(f"✅ 成功获取 {len(result)} 条热点数据")
            for i, hotword in enumerate(result, 1):
                print(f"  {i}. {hotword}")
        else:
            print("❌ 未获取到热点数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        await api.close()


async def test_hitokoto_api():
    """测试今日一言 API"""
    print("\n" + "="*50)
    print("测试今日一言 API")
    print("="*50)

    api = HitokotoAPI(token="")  # 不需要 Token
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
    finally:
        await api.close()


async def test_holiday_api():
    """测试节假日 API"""
    print("\n" + "="*50)
    print("测试节假日 API")
    print("="*50)

    api = HolidayAPI(token="")  # 不需要 Token
    try:
        result = await api.get_moyu_list_async(max_count=3)
        if result and len(result) > 0:
            print(f"✅ 成功获取 {len(result)} 条节假日数据")
            for i, holiday in enumerate(result, 1):
                days = holiday.get('days_left', 'N/A')
                print(f"  {i}. {holiday.get('name', 'N/A')} (还有 {days} 天)")
        else:
            print("❌ 未获取到节假日数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        await api.close()


async def test_ithome_rss():
    """测试 IT之家 RSS"""
    print("\n" + "="*50)
    print("测试 IT之家 RSS")
    print("="*50)

    api = ITHomeRSS()
    try:
        result = await api.get_it_news_async(max_count=5)
        if result and len(result) > 0:
            print(f"✅ 成功获取 {len(result)} 条IT资讯")
            for i, news in enumerate(result, 1):
                print(f"  {i}. {news[:60]}..." if len(news) > 60 else f"  {i}. {news}")
        else:
            print("❌ 未获取到IT资讯")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        await api.close()


async def test_zaobao_api():
    """测试早报/新闻 API"""
    print("\n" + "="*50)
    print("测试早报/新闻 API")
    print("="*50)

    api = ZaobaoAPI(token="")  # 不需要 Token
    try:
        result = await api.get_world_news_async(max_count=5)
        if result and len(result) > 0:
            print(f"✅ 成功获取 {len(result)} 条新闻")
            for i, news in enumerate(result, 1):
                print(f"  {i}. {news[:60]}..." if len(news) > 60 else f"  {i}. {news}")
        else:
            print("❌ 未获取到新闻数据")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        await api.close()


async def main():
    """运行所有测试"""
    print("\n" + "="*50)
    print("真寻日报插件 API 测试")
    print("="*50)
    print("正在测试所有 API 接口...")

    # 运行所有测试
    await test_bgm_api()
    await test_bilibili_api()
    await test_hitokoto_api()
    await test_holiday_api()
    await test_ithome_rss()
    await test_zaobao_api()

    print("\n" + "="*50)
    print("测试完成")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
