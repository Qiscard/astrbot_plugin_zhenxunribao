# 真寻日报 (astrbot_plugin_zhenxunribao)

✨ 基于 AstrBot 的一个插件 ✨

小真寻记者为你献上今天报道！

> **小真寻也很可爱呀，也会很喜欢你！**

## 📖 介绍

这是一个从 [nonebot-plugin-zxreport](https://github.com/HibiKier/nonebot-plugin-zxreport) 移植到 AstrBot 的真寻日报插件。插件会每日为你汇总最新的资讯内容，布局为：摸鱼日历 + 顶部模块（固定位）+ 中间模块（统一列表，可自由添加/排序）+ 底部引用（固定位）。

内置内容：
- 顶部模块：历史上的今天 / 每日英语 / 实时汇率（单选；汇率一个源货币可配多个目标货币，英语可展示 1-5 个单词）
- 中间模块：按类型分类，自由添加、排序、隐藏
  - 番剧游戏：今日新番 / 今日追番 / 小黑盒游戏
  - 新闻资讯：60s读懂世界 / AI早报
  - 文字内容：每日英语 / 每日一文 / 每日诗词 / 语录
- 底部引用：今日一言 / 毒鸡汤 / 名人名言 / 舔狗日记 / 搞笑语录 / 歇后语 / 随机一言 / 随机谜语
- 主题：8 套预设主题一键换肤（背景 / 面板 / 描边 / 标题 / 文字配色整体联动）

日报内容优先走糖豆子（tangdouz）免费接口，ALAPI 仅作为备用通道。

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
| `alapi_token` | str | `""` | ALAPI Token（备用通道），用于免费接口失败后的备用请求。建议在 Schema 中以密文方式显示。 |
| `milora_api_key` | str | `""` | Milora API Key，用于 AI早报；模块的 type/date 参数在日报编辑器中配置。 |
| `render_dpr` | int | `5` | 渲染清晰度（DPR），运行时限制为 1-6，建议 3-6。 |
| `enable_scheduled_push` | bool | `false` | 是否启用定时推送，启用后会在指定时间自动推送日报到配置的群组 |
| `scheduled_push_time` | str | `"08:00"` | 定时推送时间，HH:MM格式（24小时制），例如：`08:00` 表示每天早上8点 |
| `scheduled_push_groups` | list | `[]` | 定时推送目标群组列表，直接填写群号即可，如：`["957880653", "123456789"]` |
| `enable_ai_greeting` | bool | `false` | 是否启用 AI 生成个性化问候语，启用后会调用 AstrBot 当前配置的大模型生成推送问候语 |

> 模块来源、条数、标题及摸鱼日历内容已迁移到数据目录的 `modules.json`，见下一节。

## 🧩 模块自定义配置（日报编辑器 / modules.json）

**推荐方式**：在 AstrBot WebUI 左侧边栏打开本插件的 **「日报编辑器」Page**，可视化调整固定模块与来源，支持一键保存与真实渲染预览。

**布局规则**：
- 摸鱼日历（左上）：位置固定，仅内容可配
- 顶部模块（右上）：从候选来源单选一个
- 中间模块：统一列表，按类型分类添加，数量不限、顺序可调、可隐藏
- 底部引用（底部）：来源可多选，每次随机取其一

各面板数据为空（获取失败或无内容）时自动隐藏；顶部模块始终保持在摸鱼日历侧方（摸鱼日历为空时显示占位）。

编辑器读写的是数据目录（`data/plugin_data/astrbot_plugin_zhenxunribao/modules.json`）中的 `modules.json`，插件每次生成日报时都会重新读取，**修改后立即生效，无需重载插件**。首次运行会自动生成默认配置：

```jsonc
{
  // 摸鱼日历：位置固定在左上角，标题可改，展示内容按顺序渲染（最多 10 条），默认为空
  "moyu_title": "摸鱼日历",
  "moyu_items": [
    // 三种计时项类型（prefix/suffix 为该行前后段文字，留空用默认「距离」「还剩」）：
    // holiday：自动取下一个法定节假日（多条 holiday 依次取后续节日）
    { "type": "holiday" },
    // weekend：周末倒计时，weekday 仅支持 6=周六 / 7=周日；name 不填则显示「周六/周日」
    { "type": "weekend", "name": "周六", "weekday": 6 },
    // custom：自定义计时，一次性日期过期自动变为「过了N天」（suffix 可自定义）
    //         "MM-DD" 为每年循环的日期（如生日、纪念日），始终显示「还剩N天」
    { "type": "custom", "name": "元旦", "date": "01-01" },
    // 自定义前后段文字示例：显示「离 国庆节 还有 N 天」
    { "type": "custom", "name": "国庆节", "date": "10-01", "prefix": "离", "suffix": "还有" },
    // custom 条目也可以省略 type，带 date 即可
    { "name": "项目上线", "date": "2026-01-01" }
  ],
  // 顶部来源：history / english / exchange
  "top_source": "history",
  "top_params": {},
  // 顶部来源为 english 时展示的单词数量（1-5，接口单次上限 5 个）
  "top_english_count": 1,
  // 汇率参数（仅 top_source=exchange 时生效）：一个源货币 + 多个目标货币（最多 6 个）
  "exchange_from": "USD",
  "exchange_targets": ["CNY", "JPY"],
  "exchange_amount": 100,
  // 主题（方案A）：mahiro/sakura/lavender/sky/mint/gold/matcha/midnight，编辑器「🎨 主题」可预览切换
  "theme": "mahiro",
  // 底部引用来源多选：hitokoto / duji / mingyan / tiangou / gaoxiao / xiehouyu / sjyy / riddle
  "quote_enabled": true,
  "quote_title": "",
  "quote_sources": ["hitokoto"],
  // 中间模块：统一列表，按顺序纵向排列；同类型可添加多个
  "modules": [
    // 类型分类：番剧游戏(anime/cartoon/hbox)、新闻资讯(news/aidaily)、文字内容(english/essay/shici/yulu)
    { "type": "anime", "enabled": true, "title": "今日新番", "count": 4 },
    // 带接口参数的模块（cartoon 可配 date，aidaily 可配 type/date）
    { "type": "cartoon", "enabled": true, "title": "今日追番", "count": 6, "params": { "date": "" } }
  ]
}
```

说明：
- 摸鱼日历、顶部模块、底部引用位置固定；中间模块为统一列表，可自由添加/排序/隐藏；
- 摸鱼日历计时项默认为空，可在编辑器中添加节假日 / 周末 / 自定义日期三类，每条均可自定义前后段文字（如「离」「还有」）；
- 顶部模块保持在摸鱼日历侧方，摸鱼日历为空时显示占位；
- 顶部来源为英语时可通过 `top_english_count` 展示 1-5 个单词（编辑器顶部模块弹窗内设置）；
- 主题为方案A预设换肤：编辑器工具栏「🎨 主题」或画布底部主题条打开选择卡片，选中即应用并自动保存，真实渲染同步生效；未知 `theme` 值自动回退默认主题；
- 各面板数据为空（获取失败或无内容）时自动隐藏，不影响其他面板；
- 旧版配置自动迁移：`history`/`quote`/`countdown` 模块条目转为对应固定位或摸鱼日历计时项；`mid1_*`/`mid2_*` 固定位转为中间模块列表前两项；旧 `weekly` 计时项更名为 `weekend`（仅周六/周日）；旧 `exchange_to` 单值迁移为 `exchange_targets` 列表；
- `alapi_token` 只用于 ALAPI 备用通道；Milora 的 AI早报使用 `milora_api_key`。
- 中间模块（含固定位时期的 `mid1_params`/`mid2_params`）的接口参数统一保存在各模块条目的 `params` 字段。
- `/AI早报`、`/追番` 等聊天命令使用命令默认参数，不读取日报编辑器中的模块参数；日报编辑器配置只影响日报图片生成。

## 🎁 使用

### 手动生成日报

在QQ群或其他支持的平台中发送指令：
```
/日报
```

机器人将自动生成并发送当日日报图片。

### 获取群组ID（可选）

如果直接填写群号无法推送，可以在群内发送：
```
/日报群组ID
```

机器人会返回当前会话的完整标识，将其添加到配置中即可。

### 定时推送

1. 在插件配置中启用 `enable_scheduled_push`
2. 设置 `scheduled_push_time`（推送时间，默认 08:00）
3. 在 `scheduled_push_groups` 中填写目标群号，如：`["957880653"]`
4. 保存配置并重载插件，定时任务将自动启动

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

本插件渲染日报图片时内嵌了 **Noto Sans SC**（正文）与 **SSFangTangTi**（标题）字体文件，保证跨系统渲染一致。字体文件体积较大（约 19MB），会在渲染时以 Base64 嵌入 HTML。

## ⚠️ 注意事项

1. **API Key/Token**：`milora_api_key` 仅用于 Milora；`alapi_token` 仅作为 ALAPI 备用通道。日报模块参数在日报编辑器配置，聊天命令使用自己的默认参数。
2. **Playwright 安装**：首次使用需要安装 Playwright 的 Chromium 浏览器，执行 `playwright install chromium`
3. **网络环境**：插件需要访问多个外部API，请确保网络连接正常
4. **群组ID获取**：配置定时推送时，可以通过在目标群内发送 `/日报` 后查看日志获取正确的群组ID格式
## 🛠️ 技术实现

- 使用 **Jinja2** 渲染HTML模板
- 使用 **Playwright** 进行HTML到图片的转换，支持 1-6 倍 DPR 高清渲染（默认 5）
- 使用 **aiohttp** 异步获取多个数据源
- 资源文件通过 Base64 编码嵌入HTML，确保图片和字体正常显示

## 📝 功能特性

- 📰 **顶部模块** - 历史上的今天 / 每日英语 / 实时汇率（单选固定位，汇率支持一个源货币配多个目标货币，英语可展示 1-5 个单词）
- 🧩 **中间模块** - 按类型分类的统一列表：番剧游戏 / 新闻资讯 / 文字内容，自由添加、排序、隐藏
- 💬 **底部引用** - 一言/毒鸡汤/名言/谜语/随机一言等（可多选，每次随机取其一）
- 🐟 **摸鱼日历** - 节假日 / 周末 / 自定义日期正倒计时，每条支持自定义前后段文字
- 🎨 **主题方案（方案A）** - 8 套预设主题一键换肤：真寻粉 / 樱花粉 / 薰衣草紫 / 晴空蓝 / 薄荷绿 / 暖阳橙 / 抹茶绿 / 夜幕蓝，背景、面板、描边、标题、文字配色整体联动
- 🎲 **随机谜语** - 日报仅展示谜面，答题请使用聊天命令
- 🎮 **小黑盒游戏** - 免费/折扣游戏与热门推荐
- 💱 **实时汇率** - 支持自定义换算金额、源货币与多个目标货币

## 📝 更新日志

### `1.7.0`

- **主题方案（方案A）**：新增 8 套预设主题（真寻粉 / 樱花粉 / 薰衣草紫 / 晴空蓝 / 薄荷绿 / 暖阳橙 / 抹茶绿 / 夜幕蓝），参考 bot_menu 插件的主题组织方式。编辑器工具栏「🎨 主题」或画布底部主题条打开预设卡片，选中即应用、自动保存，编辑画布与真实渲染同步换肤；渲染时通过注入 `:root` CSS 变量覆盖实现，未知主题值自动回退默认。
- **每日英语显示数量**：顶部来源为英语时新增「单词数量」设置（1-5，接口单次上限 5 个），一次可展示多个单词（含音标、释义与例句）；编辑画布同步按数量预览。
- **英语模块条数上限对齐**：中间模块每日英语条数上限由 30 收窄为 5，与接口实际返回能力一致（`count_max`）。

### `1.6.0`

- **中间模块统一列表**：中部模块1/中部模块2 与附加模块合并为统一的「中间模块」，按类型分类（番剧游戏 / 新闻资讯 / 文字内容）自由添加、排序、隐藏；同类型也可添加多个。旧 `mid1_*`/`mid2_*` 固定位配置自动迁移为列表前两项。
- **摸鱼日历编辑器字段排序**：计时项编辑栏按「类型 → 前缀 → 自定义内容 → 后缀 → 自定义时间」排列。
- **顶部模块位置固定**：顶部模块始终保持在摸鱼日历侧方，摸鱼日历为空时显示占位提示。
- **汇率编辑优化**：目标货币改为逐项列表编辑（添加/排序/删除），各目标货币互不干扰，均与源货币独立换算。
- **小黑盒游戏成为独立模块类型**：可与其他模块一样自由添加多个。

### `1.5.0`

- **字体精简**：移除从未参与渲染的 HarmonyOS Sans 双字体与 Noto Sans SC Black（约 26MB）；英文标题改用站酷方糖体（SSFangTangTi），嵌入 HTML 体积减少约 55%。
- **摸鱼日历**：默认不再预置任何计时项（完全为空）；每条计时项的前段文字（默认「距离」）与后段文字（默认「还剩」）均可自定义；「周期」类型更名为「周末」，仅可选择周六/周日。
- **实时汇率**：支持一个源货币同时配置多个目标货币（最多 6 个），旧 `exchange_to` 单值自动迁移。
- **编辑器**：所有修改（含接口参数选择）即时自动保存，无需点击「完成」；面板与弹窗命名明确区分「固定位」与「附加模块」。
- **移除自定义倒计时模块**：其自定义日期功能并入摸鱼日历（旧 countdown 条目自动迁移为摸鱼日历自定义计时项）。
- **移除每日人民日报接口**：该接口仅返回 PDF 链接，无法在日报图片中直接查看。
- **文档同步**：修正字体说明、候选来源列表与配置示例。

### `1.4.0`

- **配置边界统一**：插件配置只保留 API Key/Token、渲染、定时推送与 AI 问候语；日报布局与接口参数统一由日报编辑器维护。
- **固定模块位支持接口参数**：中部模块1（今日追番）可配置 `date`；中部模块2（AI早报）可配置 `type`/`date`，人民日报可配置 `date`；参数会真实传入接口。
- **编辑器增强**：固定模块位弹窗新增「配置接口」区域；模块类型改为由后端元数据驱动；底部引用恢复多选；自动保存失败时给出提示。
- **修复重复渲染**：顶部来源选择每日英语时，不再同时出现在顶部面板和自由模块区。
- **修复配置健壮性**：非法 `modules` / `moyu_items` / 倒计时条目不再导致生成失败；模块数量统一限制；移除诗词、语录等单条接口的无效条数配置。
- **修复渲染**：顶部面板按实际类型使用对应样式与图标；汇率数据异常不再中断整张日报渲染。
- **文档同步**：修正 Milora/ALAPI 说明、DPR 范围，统一版本号。

### `1.3.1`

- 支持固定模块位布局与候选来源；日报编辑器 Page 支持画布编辑与真实预览。

## 📄 许可证

本项目采用 [AGPL-3.0](LICENSE) 许可证。

## ❤ 致谢

- [nonebot-plugin-zxreport](https://github.com/HibiKier/nonebot-plugin-zxreport) - 原始项目，由 [HibiKier](https://github.com/HibiKier) 开发
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 优秀的机器人框架
- [ALAPI](https://www.alapi.cn/) - 提供API服务
- [Bangumi](https://bgm.tv/) - 番剧数据来源
- [糖豆子](https://www.tangdouz.com/) - 免费汇率/游戏/一言/谜语接口

## 📮 反馈与建议

如有问题或建议，欢迎提交 Issue 或 Pull Request！

仓库地址：[https://github.com/Qiscard/astrbot_plugin_zhenxunribao](https://github.com/Qiscard/astrbot_plugin_zhenxunribao)

