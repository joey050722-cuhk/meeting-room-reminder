# 🏢 会议室预约提醒助手

> 帮你卡点抢会议室 · 配置实时变更 · 到点自动闹钟

## ✨ 功能特点

- 📅 **智能计算**：根据29楼会议室规则自动计算预订日期
- 🔔 **定时提醒**：支持每日自动检查并发送提醒（弹窗 + 声音）
- 🏛️ **大会议室优先**：自动识别需大会议室的会议（4大已按你的说明设为提前3天）
- 🔀 **多时段备选**：为每个会议生成多个备选时间段（±30分钟）
- 🌐 **Web界面**：可视化看板 + 在线编辑配置
- 🔄 **实时变更**：改配置无需重启，Web刷新即生效 / 在线编辑保存即生效
- 🕐 **自动闹钟**：到点桌面弹窗 + 声音提醒，支持常驻守护模式

## 📋 会议室规则（29楼）

| 会议室类型 | 提前天数 | 最长时长 |
|-----------|---------|---------|
| 2/3/4小 | 1天 | 1.5小时 |
| 5-9小 & 健身房 | 3天 | 1.5小时 |
| 10-13小 | 7天 | 1.5小时 |
| **4大** ⚠️ | **3天** | 2小时 |
| **5大** | **7天** | 2小时 |
| **6/7大** | **10天** | 2小时 |
| 3大&培训室&瑜伽室 | 10天 | 4小时 |

> ⚠️ **4大例外**：你特别说明4大实际需提前3天（与图片标注的7天不同），已单独配置。

## 🚀 快速开始

### 1. 查看今日提醒
```bash
python3 main.py --today
```

### 2. 查看未来N周日历
```bash
python3 main.py --calendar 2    # 未来2周
```

### 3. 启动Web界面
```bash
python3 main.py --web --port 8080
```
访问 http://localhost:8080 → 可视化看板 + ⚙️在线编辑配置 + 🔔浏览器闹钟

### 4. 常驻闹钟守护（适合电脑常开）
```bash
python3 main.py --alarm
```
每分钟监控，到点自动**桌面弹窗 + 声音闹钟**提醒你抢会议室。

## 🔄 实时变更配置（无需重启）

两种方式，都立即生效：

**方式A：直接改文件**
```bash
# 用任意编辑器修改 config.yaml
vi config.yaml
# Web界面刷新页面 / 命令行重跑即生效
```

**方式B：Web在线编辑（推荐）**
1. 打开 Web 界面 → 点 **⚙️ 编辑配置**
2. 修改 YAML（会议室规则 / 会议时间 / 提醒设置）
3. 点 **💾 保存并生效** → 系统自动备份旧配置并热重载

每次 Web 请求都会重新读取配置，所以外部改文件后**刷新页面即生效**。

## ⏰ 设置自动闹钟提醒

工具提供四级提醒，层层兜底：

| 级别 | 方式 | 说明 |
|------|------|------|
| 1 | 终端响铃 `\a` | 任何环境都有，最基础 |
| 2 | 桌面弹窗 | macOS `osascript` / Linux `notify-send` / Windows `BurntToast` / Python `plyer` |
| 3 | 声音闹钟 | 自动生成"叮咚"wav，跨平台播放（afplay/paplay/aplay/powershell） |
| 4 | 浏览器通知+声音 | Web界面点"🔔开启闹钟通知"，页面开着就响 |

### 自动每天提醒（推荐）
```bash
bash setup_reminder.sh              # 每天00:00自动弹窗+响铃
```
支持 cron / systemd timer（Linux）、launchd（macOS）。

### 常驻守护闹钟
```bash
bash setup_reminder.sh alarm       # 开机自启，后台常驻监控
```
使用 systemd service（Linux）/ LaunchAgent（macOS）。

### 手动测试闹钟声音
```bash
python3 -c "from reminder import MeetingRoomReminder; r=MeetingRoomReminder(); r.play_alarm_sound()"
```

## ⚙️ 配置说明

编辑 `config.yaml`：

### 添加新会议
```yaml
weekly_meetings:
  - name: "新会议"
    day_of_week: 4          # 0=周一, 1=周二, ..., 6=周日
    start_time: "14:00"
    end_time: "15:30"
    preferred_room_type: "large"   # large / small / any
    require_large: true            # 是否必须大会议室
```

### 修改提醒时间
```yaml
reminder_settings:
  reminder_time: "00:00"    # 凌晨几点提醒（卡点抢）
```

### 开关通知方式
```yaml
reminder_settings:
  notification:
    console: true
    desktop: true
    sound: true             # 声音闹钟开关
```

## 💻 Windows 一键部署（你的电脑）

```bat
双击 setup_windows.bat   （用管理员身份运行）
```
自动完成：
1. 安装依赖（pyyaml、python-dateutil、pywin32）
2. 创建3个定时任务：**22:30晚间预告 / 23:50临开抢 / 00:00每日检查**
3. 微信提醒自动推送（Server酱已配好你的SendKey）

## 🏢 会议室状态检查（解决抢冲突卡点）

抢之前跑一下，**自动查所有会议室忙闲**，不再肉眼翻日历、不怕和同事冲突：

```bash
# 单时间段（你的会议时间）
python check_rooms.py --date 8/19 --start 11:00 --end 12:00

# 多时间段矩阵（一次看多个备选时段 x 所有会议室）
python check_rooms.py --date 8/19 --start 10:00 --end 13:00 --step 30

# 只看大会议室
python check_rooms.py --date 8/19 --start 11:00 --end 12:00 --type large
```

输出示例（矩阵模式，✅=空闲 ❌=占用）：
```
时间段        4大   5大   6大   7大   2小   3小
10:00-10:30   ✅    ✅    ❌    ✅    ✅    ✅
10:30-11:00   ❌    ✅    ❌    ✅    ✅    ✅
11:00-11:30   ✅    ✅    ❌    ✅    ❌    ✅
```

**前提**（一次性配置）：
1. 电脑安装并登录 Outlook（Exchange账号）
2. `pip install pywin32`
3. 在 `config.yaml` 的 `room_emails` 段填入实际会议室资源邮箱（Outlook添加会议室时能看到，形如 `xxx@hh.global`）

## 📱 手机版提醒（放到手机里，打开就提醒）

一个自包含的 `mobile_reminder.html`，内置全部规则和计算逻辑，**离线也能用**：

| 功能 | 说明 |
|------|------|
| 🔥 今日要抢 | 预约日当天高亮显示（红色） |
| ⏰ 明日预告 | 提前一天显示 |
| 📅 未来7天 | 全部安排一览 |
| ⏳ 倒计时 | 距下次开抢/提醒的实时倒计时 |
| 🔔 到点提醒 | 通知 + "叮咚"声音 + 手机震动 |
| 🧪 测试按钮 | 随时测试闹钟效果 |

### 安装到手机（像App一样）
1. 把 `mobile_reminder.html` 传到手机：
   - 微信"文件传输助手"发送给自己 → 手机打开
   - 或邮件发给自己 → 手机收件箱打开
   - 或连接电脑拷贝到手机存储
2. 手机浏览器打开该文件
3. 添加到主屏幕：
   - **iPhone**：Safari → 分享 → "添加到主屏幕"
   - **Android**：Chrome/Edge → 菜单 → "添加到主屏幕"
4. 点主屏幕图标打开，点 **🔔开启到点提醒** 授权通知

> ⚠️ 提醒触发条件：页面需保持打开（可后台）。想更保险可叠加邮件提醒（手机邮件App会推送）。
> 页面内 `CONFIG` 段可自行修改会议时间和规则（与 config.yaml 保持同步）。

## 💬 企业微信提醒（推荐！无需密码）

用企业微信群机器人，**手机App会推送群消息**，配置只要1分钟：

### 启用步骤
1. 企业微信建一个群（如"会议室预约提醒"），把你自己拉进群
2. 群设置 → **群机器人** → 添加机器人 → 复制 **Webhook 地址**
3. 打开 `config.yaml`，填入 webhook 并启用：
```yaml
wecom:
  enabled: true            # ← 改为 true
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"
```
4. 设置定时任务（22:30 + 23:50 自动发群消息）：
```bash
bash setup_reminder.sh
```

### 手动测试
```bash
python3 main.py --reminder evening   # 晚间预告
python3 main.py --reminder final     # 临开抢
```

> 📌 `--reminder` 是统一提醒命令：企业微信和邮件**哪个配置了发哪个**，都配了都发。
> 企业微信消息为 markdown 格式，标题加粗、会议时间/会议室分条列出、开抢时间高亮。

## 📧 邮件提醒（Outlook/Office365）

预约日当天自动发两封邮件到你的邮箱，**标明会议主题及时间**：

| 时间 | 邮件标题 | 内容 |
|------|---------|------|
| **22:30** | 🌙 明晨开抢提醒 | 预告：明天凌晨可预约哪些会议 |
| **23:50** | 🚨 临开抢！ | 10分钟后开抢，立即准备 |

### 启用步骤（只需1步填密码）

1. 打开 `config.yaml`，找到 `email` 段：
```yaml
email:
  enabled: false            # ← 改为 true
  smtp_server: "smtp.office365.com"
  smtp_port: 587
  sender: "jocelyn.zhong@hh.global"
  password: ""              # ← 填入邮箱密码或"应用密码"
  recipients:
    - "jocelyn.zhong@hh.global"
```
2. 密码获取（任选其一）：
   - **应用密码**（推荐，安全）：登录 outlook.com → 安全设置 → 开启两步验证 → 生成应用密码
   - **邮箱密码**：如果未开两步验证，可直接用邮箱登录密码
3. 设置定时任务（每天22:30/23:50自动发）：
```bash
bash setup_reminder.sh      # 会同时配置邮件提醒两条cron
```

### 手动测试
```bash
python3 main.py --email-reminder evening   # 发晚间预告邮件
python3 main.py --email-reminder final     # 发临开抢邮件
```

> 💡 你的邮箱域名 hh.global 已确认是 Microsoft 365（Exchange Online），SMTP 配置已默认填好，填密码即可用。

## 📁 文件结构

```
meeting-room-reminder/
├── main.py              # 主入口（CLI + Web + 闹钟守护）
├── reminder.py          # 核心逻辑（计算 + 通知 + 声音）
├── config.yaml          # 配置文件（可实时变更）
├── setup_reminder.sh    # 定时任务一键设置
├── assets/
│   └── alarm.wav        # 自动生成的提示音
├── output/              # 提醒记录
└── README.md
```

## 💡 使用技巧

1. **大会议室紧张**：4大(3天)/5大(7天)/6-7大(10天)，务必提前关注
2. **备选时段**：首选被占可试 ±30分钟
3. **卡点抢**：系统凌晨开放预订，设闹钟卡点
4. **多约**：重要会议可同时约多个时段再取消多余
5. **配置实时改**：Web在线编辑最方便，保存即生效

## 🔧 依赖安装

```bash
pip3 install pyyaml python-dateutil
```
可选增强：
```bash
pip3 install plyer        # 跨平台桌面通知
```

---

**祝你每次都能约到心仪的会议室！🎉**
