# 真寻日报 (astrbot_plugin_zhenxunribao)

✨ 基于 AstrBot 的一个插件 ✨

小真寻记者为你献上今天报道！

> **小真寻也很可爱呀，也会很喜欢你！**

## 📖 介绍

这是一个从 [nonebot-plugin-zxreport](https://github.com/HibiKier/nonebot-plugin-zxreport) 移植到 AstrBot 的真寻日报插件。插件会每日为你汇总最新的资讯内容，包含今日新番、历史上的今天、世界新闻（60s读懂世界）、摸鱼日历和今日一言/毒鸡汤等内容。

## 💿 安装

### 通过 AstrBot 插件市场安装（推荐）

1. 在 AstrBot WebUI 中打开插件市场
2. 搜索 `astrbot_plugin_zhenxunribao` 或 `真寻日报`
3. 点击安装

### 手动安装

1. 克隆仓库到 AstrBot 插件目录：
```bash
cd AstrBot/data/plugins
git clone https://github.com/Qiscard/astrbot_plugin_zhenxunribao
```

2. 安装依赖：
```bash
cd astrbot_plugin_zhenxunribao
pip install -r requirements.txt
playwright install chromium
```

3. 在 AstrBot WebUI 的插件管理中启用插件

## ⚙️ 配置

在 AstrBot WebUI 的插件配置页面进行配置：

| 配置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `api_token` | str | `""` | ALAPI Token（可选），用于 60s读懂世界、历史上的今天等接口；在 [https://admin.alapi.cn/user/login](https://admin.alapi.cn/user/login) 注册后获取。留空时仅使用免费数据源，部分板块可能无数据 |
| `max_anime_count` | int | `4` | 今日新番最大显示数量，建议设置为4-8之间 |
| `max_news_count` | int | `10` | 60s读懂世界最大显示数量，建议设置为5-15之间 |
| `max_holiday_count` | int | `5` | 摸鱼日历最大显示数量，建议设置为3-10之间 |
| `max_history_count` | int | `8` | 历史上的今天最大显示数量，建议设置为5-15之间 |
| `quote_mode` | str | `"hitokoto"` | 底栏引用模式，`hitokoto`（今日一言）或 `duji`（毒鸡汤） |
| `render_dpr` | int | `5` | 渲染清晰度（DPR），越大越清晰但图片更大更慢，建议 3-6 |
| `enable_scheduled_push` | bool | `false` | 是否启用定时推送，启用后会在指定时间自动推送日报到配置的群组 |
| `scheduled_push_time` | str | `"08:00"` | 定时推送时间，HH:MM格式（24小时制），例如：`08:00` 表示每天早上8点 |
| `scheduled_push_groups` | list | `[]` | 定时推送目标会话列表，直接填写群号即可，如：`["957880653"]`，也支持完整的 unified_msg_origin 格式 |
| `enable_ai_greeting` | bool | `false` | 是否启用 AI 生成个性化问候语，启用后会调用 AstrBot 当前配置的大模型生成推送问候语 |

## 🎁 使用

### 手动生成日报

在QQ群或其他支持的平台中发送指令：
```
/日报
```

机器人将自动生成并发送当日日报图片。

### 获取会话ID（可选）

如果配置定时推送，可以在群内发送：
```
/日报群组ID
```

机器人会返回当前会话的 `unified_msg_origin`，将其添加到配置中即可。

> 💡 直接填写纯群号也可以，但插件需要先在该群触发过一次 `/日报` 才能学习到群号与会话的对应关系。填写完整的 `unified_msg_origin` 则无需学习。

### 定时推送

1. 在插件配置中启用 `enable_scheduled_push`
2. 设置 `scheduled_push_time`（推送时间，默认 08:00）
3. 在 `scheduled_push_groups` 中填写目标群号或 `unified_msg_origin`
4. 保存配置后定时任务自动生效（调度器每 30 秒检查一次配置，无需重载插件）

## 📋 依赖

- `aiohttp>=3.8.0` - 异步HTTP请求库
- `jinja2>=3.0.0` - HTML模板渲染引擎
- `playwright>=1.40.0` - 浏览器自动化，用于HTML转图片
- `zhdate>=0.1` - 农历日期计算支持

安装 Playwright 浏览器：
```bash
playwright install chromium
```

## 🖋 字体说明

本插件渲染日报图片时使用了 **HarmonyOS Sans** 字体文件以提升跨系统一致性与清晰度。

## ⚠️ 注意事项

1. **API Token 配置**：60s读懂世界与历史上的今天依赖 ALAPI（需配置 `api_token`）；未配置 Token 时新番、摸鱼日历、今日一言、毒鸡汤等免费数据源仍可正常获取，仅相关板块显示"暂无数据"
2. **Playwright 安装**：首次使用需要安装 Playwright 的 Chromium 浏览器，执行 `playwright install chromium`
3. **网络环境**：插件需要访问多个外部API，请确保网络连接正常
4. **数据可信**：数据源失败时，对应板块显示"暂未获取到数据"占位提示，**不会展示编造的示例数据**

## 🛠️ 技术实现

- 使用 **Jinja2** 渲染HTML模板
- 使用 **Playwright** 进行HTML到图片的转换，支持高 DPR 高清渲染（本地渲染，不上传数据到第三方渲染服务）
- 使用 **aiohttp** 异步获取多个数据源，带指数退避重试
- 资源文件通过 Base64 编码嵌入HTML，确保图片和字体正常显示
- 定时推送统一走 `context.send_message`，支持所有平台适配器（aiocqhttp、QQ官方API、Telegram等）

## 📝 功能特性

- 📺 **今日新番** - 显示今日更新的动画番剧信息（Bangumi 数据）
- 🌍 **60s读懂世界** - 每日新闻资讯（ALAPI，需 Token；备用：知乎日报）
- 📜 **历史上的今天** - 历史上的今天发生的事件（ALAPI，需 Token）
- 🐟 **摸鱼日历** - 显示节假日和重要日期倒计时
- 💬 **今日一言 / 毒鸡汤** - 每日一句精美文案，可切换模式
- 🤖 **AI 问候语** - 定时推送时可由 LLM 生成个性化问候语
- ⏰ **定时推送** - 每日定时推送到指定群组/会话

## 📝 更新日志

- `1.3.1` - 安全与兼容性修复：移除硬编码 Token 改为配置项（api_token）、修复 Provider 回退 API 调用、移除废弃的 @register 装饰器、定时推送统一改用 context.send_message（跨平台）、移除 API 失败时的编造兜底数据、修复日志中泄露 Token 的问题、对齐配置默认值
- 详细变更见 `CHANGELOG.md`

## 📄 许可证

本项目采用 [AGPL-3.0](LICENSE) 许可证。

## ❤ 致谢

- [nonebot-plugin-zxreport](https://github.com/HibiKier/nonebot-plugin-zxreport) - 原始项目，由 [HibiKier](https://github.com/HibiKier) 开发
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 优秀的机器人框架
- [ALAPI](https://www.alapi.cn/) - 提供API服务
- [Bangumi](https://bgm.tv/) - 番剧数据来源

## 📮 反馈与建议

如有问题或建议，欢迎提交 Issue 或 Pull Request！

仓库地址：[https://github.com/Qiscard/astrbot_plugin_zhenxunribao](https://github.com/Qiscard/astrbot_plugin_zhenxunribao)
