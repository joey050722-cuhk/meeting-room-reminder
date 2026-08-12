#!/bin/bash
# 会议室邮件提醒 - 一键启用 + 测试脚本
# 用法: bash enable_email.sh
# 功能: 交互输入密码 → 写入配置 → 启用 → 发送测试邮件

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$PROJECT_DIR/config.yaml"
MAIN="$PROJECT_DIR/main.py"

echo "========================================================"
echo "   📧 会议室邮件提醒 - 启用 + 测试"
echo "========================================================"
echo ""
echo "收件人/发件人: jocelyn.zhong@hh.global"
echo "SMTP: smtp.office365.com:587 (已确认你的邮箱是Microsoft 365)"
echo ""

# 1. 获取密码（不回显）
echo -n "请输入邮箱密码或应用密码 (输入时不会显示): "
read -s PASSWORD
echo ""
if [ -z "$PASSWORD" ]; then
    echo "❌ 密码不能为空"
    exit 1
fi

# 2. 备份配置
TIMESTAMP=$(date +%Y%m%d%H%M%S)
cp "$CONFIG" "$CONFIG.$TIMESTAMP.bak"
echo "✅ 已备份原配置 → config.yaml.$TIMESTAMP.bak"

# 3. 写入密码并启用 (用python安全处理yaml)
python3 << PYEOF
import yaml, sys

with open("$CONFIG", 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

cfg.setdefault('email', {})
cfg['email']['enabled'] = True
cfg['email']['password'] = "$PASSWORD"
cfg['email']['sender'] = "jocelyn.zhong@hh.global"
cfg['email']['recipients'] = ["jocelyn.zhong@hh.global"]

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
echo "   🧪 正在发送测试邮件..."
echo "========================================================"

cd "$PROJECT_DIR"
python3 -c "
from reminder import MeetingRoomReminder
r = MeetingRoomReminder()
ok = r.send_email(
    '🧪 会议室提醒助手 - 测试邮件',
    '''这是一封测试邮件！

会议室预约提醒助手已配置成功，邮件通路正常。

今天可预约的会议会自动在 22:30 / 23:50 发提醒。
—— 会议室预约提醒助手
'''
)
import sys
sys.exit(0 if ok else 1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================================"
    echo "   ✅ 测试邮件已发送！请检查邮箱收件箱/垃圾箱"
    echo ""
    echo "   接下来请设置定时任务:"
    echo "   bash setup_reminder.sh    # 22:30 + 23:50 自动发提醒"
    echo "========================================================"
else
    echo ""
    echo "   ❌ 发送失败，可能原因:"
    echo "   1. 密码错误 → 重新运行本脚本"
    echo "   2. 公司禁用了SMTP认证 → 联系IT开通，或用应用密码"
    echo "   3. 两步验证未开 → 在Outlook安全设置生成应用密码"
    echo ""
    echo "   修改密码: 重新运行 bash enable_email.sh"
fi
