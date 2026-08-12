#!/bin/bash
# 企业微信提醒 - 一键启用 + 测试脚本
# 用法: bash enable_wecom.sh
# 功能: 交互输入Webhook → 写入配置 → 启用 → 发送测试消息

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$PROJECT_DIR/config.yaml"

echo "========================================================"
echo "   💬 企业微信提醒 - 启用 + 测试"
echo "========================================================"
echo ""
echo "准备Webhook地址（企业微信里获取）："
echo "  1. 建一个群（如: 会议室预约提醒）"
echo "  2. 群设置 → 群机器人 → 添加机器人"
echo "  3. 复制 Webhook 地址"
echo ""

# 1. 获取Webhook
echo -n "请粘贴Webhook地址: "
read -r WEBHOOK
if [ -z "$WEBHOOK" ]; then
    echo "❌ Webhook不能为空"
    exit 1
fi
# 简单校验格式
if [[ "$WEBHOOK" != https://qyapi.weixin.qq.com* ]]; then
    echo "❌ Webhook地址格式不对，应以 https://qyapi.weixin.qq.com 开头"
    exit 1
fi

# 2. 备份配置
TIMESTAMP=$(date +%Y%m%d%H%M%S)
cp "$CONFIG" "$CONFIG.$TIMESTAMP.bak"
echo "✅ 已备份原配置 → config.yaml.$TIMESTAMP.bak"

# 3. 写入webhook并启用
python3 << PYEOF
import yaml

with open("$CONFIG", 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

cfg.setdefault('wecom', {})
cfg['wecom']['enabled'] = True
cfg['wecom']['webhook_url'] = "$WEBHOOK"

with open("$CONFIG", 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

print("✅ 配置已写入并启用")
PYEOF

if [ $? -ne 0 ]; then
    echo "❌ 写入配置失败"
    exit 1
fi

echo ""
echo "========================================================"
echo "   🧪 正在发送测试消息到企业微信群..."
echo "========================================================"

cd "$PROJECT_DIR"
python3 -c "
from reminder import MeetingRoomReminder
r = MeetingRoomReminder()
# 发送一条测试消息（同时展示今日可预约的会议）
todays = r.get_today_booking_items()
content = '## 🧪 会议室提醒助手已连接\n> 企业微信群机器人配置成功，消息通道正常！\n\n'
if todays:
    content += '**今日可预约的会议：**\n'
    for i, t in enumerate(todays[:3], 1):
        content += f'**{i}. {t[\"meeting_name\"]}**\n'
        content += f'> 🗓️ {t[\"meeting_date\"]}({t[\"meeting_weekday\"]}) {t[\"meeting_time\"]}\n'
        content += f'> 🚪 {t[\"rooms\"]}（提前{t[\"advance_days\"]}天）\n\n'
else:
    content += '今天没有可预约的会议，看看目标会议吧：\n'
    content += '> python3 main.py -m \"NT WIP\"\n'
content += '---\n'
content += '**⏰ 每日提醒**：22:30 晚间预告 / 23:50 临开抢'
ok = r.send_wecom(content)
import sys
sys.exit(0 if ok else 1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================================"
    echo "   ✅ 测试消息已发送！请查看企业微信群"
    echo ""
    echo "   接下来设置定时任务:"
    echo "   bash setup_reminder.sh    # 22:30 + 23:50 自动提醒"
    echo "========================================================"
else
    echo ""
    echo "   ❌ 发送失败，可能原因:"
    echo "   1. Webhook地址复制不完整 → 重新运行本脚本"
    echo "   2. 机器人被移除 → 重新添加"
    echo ""
    echo "   修改Webhook: 重新运行 bash enable_wecom.sh"
fi
