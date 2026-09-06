# Changelog

本文件记录真寻日报插件的 notable changes。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.3.1] - 2026-09-06

### 安全

- **移除硬编码的 ALAPI Token**：原 Token 曾硬编码在 `holiday_api.py`、`zaobao_api.py`、`history_api.py`、`hitokoto_api.py` 四个文件中，现全部改为从插件配置 `api_token` 读取（默认留空，仅使用免费数据源）。曾在日志中以 INFO 级别打印含 Token 的完整 URL 的问题一并修复。
- 如您使用过受影响版本，建议前往 [ALAPI 后台](https://admin.alapi.cn/user/login) 重置 Token。

### 变更

- **移除废弃的 `@register` 装饰器**：AstrBot 自 v3.5.19 起自动识别 `Star` 子类，该装饰器已废弃。
- **定时推送统一改走 `context.send_message`**：移除直接调用 OneBot `call_action("send_group_msg")` 的私有路径，推送现支持所有平台适配器（aiocqhttp、QQ 官方 API、Telegram 等）。推送目标支持完整 `unified_msg_origin` 或已学习映射的纯群号。
- **重写定时调度器**：改为 30 秒间隔检查循环，配置变更约 30 秒内生效（原先最坏滞后 24 小时）；修复插件重载时延迟启动任务未被跟踪、可能在卸载后继续推送的问题；以"最后推送日期"标记防止当日重复推送。
- **API 失败时不再展示编造数据**：移除假新闻、假新番、假历史事件、假节假日等兜底数据，失败板块显示"暂未获取到数据"占位提示。
- **AI 问候语兜底修复**：替换为实际存在的 `provider_manager.get_insts()` 接口（原 `get_all_providers()` 不存在，导致兜底逻辑静默失效）。
- **按引用模式按需请求**：`quote_mode` 为 `duji` 时不再请求今日一言，反之亦然。
- **临时文件名改用 `uuid4`**，路径处理全面 `pathlib` 化。
- **降低日志噪音**：原始数据与响应体日志降为 debug 级别。

### 文档

- README 与代码全面对齐：移除未实现的"B站热点 / IT资讯"功能描述、统一仓库地址、配置表与 `_conf_schema.json` 逐项一致、补充 `api_token` 说明。
- 重写 `test_apis.py` 以匹配当前 API 模块与签名。

## [1.3.0] 及更早版本

- 从 [nonebot-plugin-zxreport](https://github.com/HibiKier/nonebot-plugin-zxreport) 移植至 AstrBot，包含今日新番、60s读懂世界、历史上的今天、摸鱼日历、今日一言/毒鸡汤与定时推送等功能。更早版本的变更未在本文件中记录。
