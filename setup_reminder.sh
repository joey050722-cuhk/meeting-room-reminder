#!/bin/bash
# 会议室预约提醒 - 定时任务一键设置脚本
# 支持两种模式:
#   1) daily  (默认) - 每天00:00跑一次，自动弹窗+响铃提醒（推荐）
#   2) alarm        - 常驻守护，电脑开机即后台监控，到点自动响铃

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SCRIPT="$PROJECT_DIR/main.py"
LOG_FILE="$PROJECT_DIR/cron.log"
MODE="${1:-daily}"

echo "========================================================"
echo "   🏢 会议室预约提醒 - 定时任务设置"
echo "========================================================"
echo ""
echo "项目目录: $PROJECT_DIR"
echo "模式: $MODE"
if [ "$MODE" = "daily" ]; then
    echo "提醒时间: 每天 00:00 (系统开放预订后5分钟)"
else
    echo "模式: 常驻守护 (电脑开机即后台运行)"
fi
echo ""

if [ "$MODE" = "alarm" ]; then
    setup_alarm
else
    setup_cron
fi

# ============================================================
# 模式1: 每日定时 (cron / systemd timer)
# ============================================================
setup_cron() {
    REMINDER_TIME="0 0 * * *"
    CRON_CMD="$REMINDER_TIME cd $PROJECT_DIR && /usr/bin/python3 $MAIN_SCRIPT --today >> $LOG_FILE 2>&1"

    if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl >/dev/null 2>&1; then
        setup_systemd_timer "$CRON_CMD"
    else
        setup_crontab_only "$CRON_CMD"
    fi
    # 邮件提醒定时任务（22:30 晚间预告 + 23:50 临开抢）
    setup_email_cron
}

# 预约日提醒: 22:30 晚间预告 + 23:50 临开抢（企业微信 + 邮件，按config启用渠道自动发送）
setup_email_cron() {
    echo ""
    echo "正在设置预约日提醒定时任务 (22:30 预告 / 23:50 临开抢)..."
    EVENING_CMD="30 22 * * * cd $PROJECT_DIR && /usr/bin/python3 $MAIN_SCRIPT --reminder evening >> $LOG_FILE 2>&1"
    FINAL_CMD="50 23 * * * cd $PROJECT_DIR && /usr/bin/python3 $MAIN_SCRIPT --reminder final >> $LOG_FILE 2>&1"
    
    if crontab -l 2>/dev/null | grep -q "reminder evening"; then
        echo "⚠️  预约日提醒任务已存在，跳过"
        return
    fi
    (crontab -l 2>/dev/null; echo "$EVENING_CMD"; echo "$FINAL_CMD") | crontab -
    if [ $? -eq 0 ]; then
        echo "✅ 预约日提醒已设置:"
        echo "   22:30 → 晚间预告 (企业微信/邮件)"
        echo "   23:50 → 临开抢 (企业微信/邮件)"
    else
        echo "❌ 预约日提醒设置失败"
    fi
}

setup_crontab_only() {
    local cmd="$1"
    echo "正在设置 cron 定时任务..."
    if crontab -l 2>/dev/null | grep -q "meeting-room-reminder"; then
        echo "⚠️  定时任务已存在，跳过"
        return
    fi
    (crontab -l 2>/dev/null; echo "$cmd") | crontab -
    if [ $? -eq 0 ]; then
        echo "✅ cron 定时任务设置成功!"
        echo "  查看: crontab -l | grep meeting-room-reminder"
        echo "  日志: tail -f $LOG_FILE"
    else
        echo "❌ cron 设置失败"
    fi
}

setup_systemd_timer() {
    local cmd="$1"
    echo "正在设置 systemd 定时任务..."
    if [ "$EUID" -ne 0 ]; then
        echo "⚠️  需要sudo权限: sudo $0"
        echo "正在尝试普通cron..."
        setup_crontab_only "$cmd"
        return
    fi
    SERVICE_FILE="/etc/systemd/system/meeting-reminder.service"
    TIMER_FILE="/etc/systemd/system/meeting-reminder.timer"
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Meeting Room Reminder
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 $MAIN_SCRIPT --today
WorkingDirectory=$PROJECT_DIR

[Install]
WantedBy=multi-user.target
EOF
    cat > "$TIMER_FILE" << EOF
[Unit]
Description=Run Meeting Room Reminder daily at 00:00

[Timer]
OnCalendar=*-*-* 00:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable meeting-reminder.timer
    systemctl start meeting-reminder.timer
    if systemctl is-active --quiet meeting-reminder.timer; then
        echo "✅ systemd 定时器设置成功并已启动!"
        echo "  状态: systemctl status meeting-reminder.timer"
        echo "  日志: journalctl -u meeting-reminder.service"
    else
        echo "❌ systemd 定时器启动失败，尝试cron..."
        setup_crontab_only "$cmd"
    fi
}

# ============================================================
# 模式2: 常驻闹钟守护 (systemd service 常驻 / launchd)
# ============================================================
setup_alarm() {
    echo "正在设置常驻闹钟守护进程..."

    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ "$EUID" -ne 0 ]; then
            echo "⚠️  需要sudo权限: sudo $0 alarm"
            return
        fi
        SERVICE_FILE="/etc/systemd/system/meeting-alarm.service"
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Meeting Room Alarm Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $MAIN_SCRIPT --alarm
WorkingDirectory=$PROJECT_DIR
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable meeting-alarm.service
        systemctl start meeting-alarm.service
        if systemctl is-active --quiet meeting-alarm.service; then
            echo "✅ 常驻闹钟守护已启动 (开机自启)!"
            echo "  状态: systemctl status meeting-alarm.service"
        else
            echo "❌ 启动失败"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        PLIST="$HOME/Library/LaunchAgents/com.meeting.alarm.plist"
        cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.meeting.alarm</string>
    <key>ProgramArguments</key>
    <array><string>/usr/bin/python3</string><string>$MAIN_SCRIPT</string><string>--alarm</string></array>
    <key>RunAtLoad</key><true/>
    <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
    <key>StandardOutPath</key><string>$LOG_FILE</string>
    <key>StandardErrorPath</key><string>$LOG_FILE</string>
</dict>
</plist>
EOF
        launchctl load "$PLIST"
        echo "✅ macOS 常驻闹钟已设置 (开机自启)!"
    else
        echo "⚠️  当前系统不支持常驻模式，请使用默认daily模式: $0 daily"
    fi
}

echo ""
echo "========================================================"
echo "   设置完成！$MODE 模式已激活"
echo ""
echo "   其他用法:"
echo "   bash $0            # 每日00:00提醒(默认)"
echo "   bash $0 alarm     # 常驻守护闹钟"
echo "========================================================"
