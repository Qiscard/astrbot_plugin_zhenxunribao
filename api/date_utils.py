"""
日期工具模块
用于获取当前日期、星期、农历等信息
"""

from datetime import datetime

# 星期映射
WEEKDAYS_CN = {
    0: "星期一",
    1: "星期二",
    2: "星期三",
    3: "星期四",
    4: "星期五",
    5: "星期六",
    6: "星期日",
}


def get_current_date_info() -> dict[str, str]:
    """
    获取当前日期信息

    Returns:
        {
            'week_cn': '星期一',
            'date_str': '2024-01-15',
            'cn_date_str': '腊月初五'
        }
    """
    now = datetime.now()

    # 星期
    week_cn = WEEKDAYS_CN[now.weekday()]

    # 日期字符串
    date_str = now.strftime("%Y-%m-%d")

    # 农历日期
    cn_date_str = get_lunar_date(now)

    return {"week_cn": week_cn, "date_str": date_str, "cn_date_str": cn_date_str}


def days_until_date(date_str: str) -> int | None:
    """计算距离目标日期的天数（支持正/倒计时）。

    Args:
        date_str: 目标日期。支持两种格式：
            - "YYYY-MM-DD"：一次性日期，过期后返回负数（正计时：过了 N 天）
            - "MM-DD"：每年循环的日期，自动取下一次出现的日期（始终为倒计时）

    Returns:
        带符号天数：目标在将来为正（还剩 N 天），已过期为负（过了 N 天，仅
        YYYY-MM-DD 一次性日期会出现），当天为 0；格式非法返回 None。
    """
    date_str = str(date_str).strip()
    if not date_str:
        return None
    today = datetime.now().date()
    try:
        if len(date_str) == 5 and date_str[2] == "-":
            # 每年循环：今年已过则取明年（循环日期永远代表“下一次”，始终倒计时）
            target = datetime.strptime(f"{today.year}-{date_str}", "%Y-%m-%d").date()
            if target < today:
                target = target.replace(year=today.year + 1)
            return (target - today).days
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        # 一次性日期：过期返回负数，供模板渲染“过了 N 天”
        return (target - today).days
    except ValueError:
        return None


def days_until_weekday(weekday: int) -> int:
    """计算距离目标星期的天数。

    Args:
        weekday: 目标星期，1=周一 ... 7=周日

    Returns:
        距离目标星期的天数（当天为 0，范围 0-6）。
    """
    return ((int(weekday) - 1) - datetime.now().weekday()) % 7


def get_lunar_date(date_obj: datetime) -> str:
    """
    获取农历日期
    优先使用 zhdate 库，如果未安装则返回"农历未知"

    Args:
        date_obj: 日期对象

    Returns:
        农历日期字符串，如 '腊月初五'，失败时返回 '农历未知'
    """
    try:
        from zhdate import ZhDate

        lunar = ZhDate.from_datetime(date_obj)
        lunar_months = [
            "",
            "正",
            "二",
            "三",
            "四",
            "五",
            "六",
            "七",
            "八",
            "九",
            "十",
            "冬",
            "腊",
        ]
        month_name = (
            lunar_months[lunar.lunar_month]
            if lunar.lunar_month < len(lunar_months)
            else str(lunar.lunar_month)
        )
        if lunar.lunar_day == 1:
            day_name = "初一"
        elif lunar.lunar_day <= 10:
            day_names = [
                "",
                "初一",
                "初二",
                "初三",
                "初四",
                "初五",
                "初六",
                "初七",
                "初八",
                "初九",
                "初十",
            ]
            day_name = day_names[lunar.lunar_day]
        elif lunar.lunar_day < 20:
            day_name = f"十{['', '一', '二', '三', '四', '五', '六', '七', '八', '九'][lunar.lunar_day - 10]}"
        elif lunar.lunar_day == 20:
            day_name = "二十"
        elif lunar.lunar_day < 30:
            day_name = f"廿{['', '一', '二', '三', '四', '五', '六', '七', '八', '九'][lunar.lunar_day - 20]}"
        else:
            day_name = "三十"
        return f"{month_name}月{day_name}"
    except ImportError:
        return "农历未知"
    except Exception:
        return "农历未知"
