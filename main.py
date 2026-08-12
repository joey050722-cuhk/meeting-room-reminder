#!/usr/bin/env python3
"""
会议室预约提醒工具 - 主入口
==============================
支持命令行、Web界面（含在线编辑）、常驻闹钟三种模式
"""

import sys
import os
import time
import shutil
import json
import urllib.parse
import yaml as _yaml

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reminder import MeetingRoomReminder, setup_crontab


def cli_mode():
    """命令行模式"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='🏢 会议室预约提醒工具 - 帮你卡点抢会议室！',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python main.py --today              # 查看今天需要预约的会议室
  python main.py --calendar 3         # 查看未来3周的预约日历
  python main.py --setup-cron         # 设置每日自动提醒定时任务
  python main.py --web                # 启动Web界面(支持在线编辑配置)
  python main.py --alarm              # 常驻闹钟守护(到点弹窗+响铃)
        """
    )
    
    parser.add_argument('--config', '-c', 
                        default=os.path.join(os.path.dirname(__file__), 'config.yaml'),
                        help='配置文件路径')
    parser.add_argument('--today', '-t', action='store_true', 
                        help='查看今日提醒事项')
    parser.add_argument('--calendar', '-l', type=int, default=2, 
                        help='查看未来N周的预约日历 (默认2周)')
    parser.add_argument('--setup-cron', action='store_true', 
                        help='显示cron定时任务设置说明')
    parser.add_argument('--web', '-w', action='store_true', 
                        help='启动Web界面')
    parser.add_argument('--alarm', '-a', action='store_true',
                        help='常驻闹钟守护模式(到点自动弹窗+响铃)')
    parser.add_argument('--email-reminder', '-e', choices=['evening', 'final', 'auto'],
                        nargs='?', const='auto', default=None,
                        help='发送邮件提醒: evening=22:30晚间预告 / final=23:50临开抢 / auto=按时间判断')
    parser.add_argument('--reminder', '-r', choices=['evening', 'final', 'auto'],
                        nargs='?', const='auto', default=None,
                        help='统一提醒(企业微信+邮件): evening=22:30 / final=23:50')
    parser.add_argument('--meeting-calendar', '-m',
                        help='查询目标会议抢购时间线, 如: -m "NT WIP"')
    parser.add_argument('--port', '-p', type=int, default=8080, 
                        help='Web界面端口 (默认8080)')
    
    args = parser.parse_args()
    
    reminder = MeetingRoomReminder(args.config)
    
    if args.setup_cron:
        setup_crontab()
    elif args.meeting_calendar:
        print(reminder.format_meeting_calendar(meeting_name=args.meeting_calendar))
    elif args.reminder:
        reminder.send_reminders(args.reminder)
    elif args.email_reminder:
        reminder.email_reminder(args.email_reminder)
    elif args.alarm:
        alarm_mode(reminder)
    elif args.web:
        start_web_server(reminder, args.port)
    elif args.today:
        reminder.run_daily_check()
    else:
        reminder.show_calendar_view(args.calendar)


def alarm_mode(reminder: MeetingRoomReminder):
    """
    常驻闹钟守护模式
    =================
    每分钟检查一次，当到达某会议的"提醒时间"(默认00:00)后，
    自动弹出桌面通知 + 播放闹钟声音提醒你去抢会议室。
    每天00:00由cron触发一次性提醒最可靠；此模式适合电脑常开时持续守护。
    """
    print("""
╔═══════════════════════════════════════════════════════════╗
║     🕐 会议室闹钟守护已启动                                ║
╠═══════════════════════════════════════════════════════════╣
║  到点会自动: 桌面弹窗通知 + 🔔 闹钟声音                    ║
║  配置实时生效: 改yaml无需重启                               ║
║  按 Ctrl+C 退出                                            ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    reminded = set()
    last_day = None
    
    try:
        while True:
            try:
                reminder.reload_config()  # 实时读取最新配置
                now = time.localtime()
                today = time.strftime('%Y-%m-%d', now)
                
                # 新的一天，清空已提醒记录
                if last_day != today:
                    reminded.clear()
                    last_day = today
                
                todays = reminder.get_today_reminders()
                for r in todays:
                    key = (r['meeting_name'], r['rule_name'], r['booking_date'])
                    if key not in reminded:
                        # 已到提醒时间(00:00)则触发
                        rt = r['reminder_datetime']
                        if isinstance(rt, str):
                            rt = time.strptime(rt, '%Y-%m-%d %H:%M:%S')
                        if time.mktime(now) >= time.mktime(rt):
                            text = reminder.format_reminder_text([r])
                            reminder.send_notification(
                                f"🔔 抢会议室闹钟：今天可约 {r['meeting_name']}",
                                text
                            )
                            reminded.add(key)
            except Exception as e:
                print(f"[闹钟异常] {e}")
            
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n\n👋 闹钟守护已停止")


def start_web_server(reminder: MeetingRoomReminder, port: int = 8080):
    """启动Web服务器（支持配置实时变更 & 在线编辑）"""
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    
    class ReminderHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.reminder = reminder
            super().__init__(*args, directory=os.path.dirname(__file__), **kwargs)
        
        def do_GET(self):
            # 🔄 每次请求都重新加载配置 → 配置文件实时变更无需重启
            try:
                self.reminder.reload_config()
            except Exception:
                pass
            
            parsed = urllib.parse.urlparse(self.path)
            
            if parsed.path == '/api/today':
                self.send_json(self.reminder.get_today_reminders())
            elif parsed.path == '/api/calendar':
                params = urllib.parse.parse_qs(parsed.query)
                weeks = int(params.get('weeks', [2])[0])
                self.send_json(self.reminder.get_all_reminders(weeks_ahead=weeks))
            elif parsed.path == '/api/rules':
                self.send_json(self.reminder.meeting_rules)
            elif parsed.path == '/api/meetings':
                self.send_json(self.reminder.weekly_meetings)
            elif parsed.path == '/api/config':
                # 返回当前配置文件原文（用于在线编辑预填）
                try:
                    with open(self.reminder.config_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    self.send_json({'config': text, 'path': self.reminder.config_path})
                except Exception as e:
                    self.send_json({'error': str(e)})
            elif parsed.path in ['/', '/index.html']:
                self.send_html()
            else:
                super().do_GET()
        
        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            
            if parsed.path == '/api/config':
                try:
                    length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(length).decode('utf-8')
                    payload = json.loads(body)
                    new_yaml = payload.get('config', '')
                    
                    # 校验yaml语法
                    _yaml.safe_load(new_yaml)
                    
                    # 备份旧配置
                    bak = (self.reminder.config_path + '.' + 
                           time.strftime('%Y%m%d%H%M%S') + '.bak')
                    shutil.copy(self.reminder.config_path, bak)
                    
                    # 写入新配置
                    with open(self.reminder.config_path, 'w', encoding='utf-8') as f:
                        f.write(new_yaml)
                    
                    # 立即热重载
                    self.reminder.reload_config()
                    
                    self.send_json({
                        'ok': True, 
                        'msg': '✅ 配置已保存并实时生效', 
                        'backup': os.path.basename(bak)
                    })
                except Exception as e:
                    self.send_json({'ok': False, 'msg': f'❌ 保存失败: {e}'})
            else:
                self.send_response(404)
                self.end_headers()
        
        def send_json(self, data):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            except TypeError as e:
                json_str = json.dumps({'error': str(e)}, ensure_ascii=False)
            self.wfile.write(json_str.encode('utf-8'))
        
        def send_html(self):
            html = generate_html_page()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        
        def log_message(self, format, *args):
            print(f"[Web] {args[0]}")
    
    server = HTTPServer(('0.0.0.0', port), ReminderHandler)
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║     🏢 会议室预约提醒工具 - Web界面                         ║
╠═══════════════════════════════════════════════════════════╣
║   服务地址: http://localhost:{port}                          ║
║                                                           ║
║   ✨ 新功能:                                               ║
║   - ⚙️ 在线编辑配置 (保存即生效，无需重启)                  ║
║   - 🔔 浏览器通知 + 声音闹钟                               ║
║   - 🔄 配置实时变更                                        ║
║                                                           ║
║   按 Ctrl+C 停止服务                                       ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
        server.server_close()


def generate_html_page():
    """生成HTML页面（含在线编辑 + 浏览器通知 + 声音闹钟）"""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏢 会议室预约提醒助手</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; color: white; font-size: 2.5em; margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2); }
        .subtitle { text-align: center; color: rgba(255,255,255,0.9); margin-bottom: 30px; font-size: 1.1em; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px; margin-bottom: 25px; }
        .stat-card { background: rgba(255,255,255,0.95); border-radius: 12px; padding: 18px;
            text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .stat-number { font-size: 2em; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; font-size: .9em; }
        .card { background: white; border-radius: 12px; padding: 25px; margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .card h2 { color: #333; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
        .reminder-item { border-left: 4px solid #667eea; padding: 15px; margin-bottom: 12px;
            background: #f8f9ff; border-radius: 0 8px 8px 0; transition: transform 0.2s; }
        .reminder-item:hover { transform: translateX(5px); }
        .reminder-item.urgent { border-left-color: #e74c3c; background: #fff5f5; }
        .reminder-item.large-room { border-left-color: #f39c12; }
        .meeting-name { font-weight: bold; font-size: 1.1em; color: #333; }
        .meeting-time { color: #666; margin-top: 5px; }
        .room-info { margin-top: 10px; padding: 8px 12px; background: white; border-radius: 6px; font-size: .95em; }
        .room-tag { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: .85em; margin-right: 5px; }
        .tag-large { background: #f39c12; color: white; }
        .tag-small { background: #3498db; color: white; }
        .tag-urgent { background: #e74c3c; color: white; animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
        .btn { display: inline-block; padding: 10px 18px; border: none; border-radius: 8px;
            cursor: pointer; font-size: .95em; margin: 5px; transition: all 0.2s; }
        .btn-primary { background: #667eea; color: white; }
        .btn-primary:hover { background: #5a6fd6; transform: translateY(-2px); }
        .btn-success { background: #27ae60; color: white; }
        .btn-warning { background: #e67e22; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .controls { text-align: center; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9ff; color: #667eea; font-weight: 600; }
        tr:hover { background: #f8f9ff; }
        .empty-state { text-align: center; padding: 40px; color: #999; }
        .empty-state .icon { font-size: 3em; margin-bottom: 10px; }
        .footer { text-align: center; color: rgba(255,255,255,0.8); padding: 20px; margin-top: 20px; }
        .time-slots { margin-top: 8px; font-size: .9em; color: #888; }
        .slot { display: inline-block; background: #e8f4f8; padding: 2px 8px; border-radius: 4px; margin: 2px; }
        .reload-badge { font-size: .8em; color: #27ae60; margin-left: 10px; }
        /* 模态框 */
        .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); }
        .modal-content { background: white; margin: 3% auto; padding: 25px; border-radius: 12px;
            width: 90%; max-width: 800px; max-height: 90vh; overflow-y: auto; }
        .modal-content h3 { margin-bottom: 15px; color: #333; }
        textarea#configEditor { width: 100%; height: 420px; font-family: 'Courier New', monospace;
            font-size: 13px; border: 1px solid #ddd; border-radius: 8px; padding: 12px; line-height: 1.5; }
        #saveMsg { margin: 10px 0; font-weight: bold; }
        .close { float: right; font-size: 28px; font-weight: bold; cursor: pointer; color: #aaa; }
        .close:hover { color: #333; }
        .toast { position: fixed; bottom: 30px; right: 30px; background: #27ae60; color: white;
            padding: 15px 25px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,.2);
            display: none; z-index: 200; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏢 会议室预约提醒助手</h1>
        <p class="subtitle">帮你卡点抢会议室 · 配置实时变更 · 到点自动闹钟 <span id="reloadBadge" class="reload-badge"></span></p>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-number" id="todayCount">-</div>
                <div class="stat-label">今日可预约</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="urgentCount">-</div>
                <div class="stat-label">紧急待办</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="weekCount">-</div>
                <div class="stat-label">本周待处理</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="totalMeetings">4</div>
                <div class="stat-label">固定会议数</div>
            </div>
        </div>
        
        <div class="controls">
            <button class="btn btn-primary" onclick="loadToday()">📅 今日提醒</button>
            <button class="btn btn-primary" onclick="loadCalendar(1)">📆 本周</button>
            <button class="btn btn-primary" onclick="loadCalendar(2)">📆 两周</button>
            <button class="btn btn-warning" onclick="openEditor()">⚙️ 编辑配置</button>
            <button class="btn btn-success" onclick="enableNotify()">🔔 开启闹钟通知</button>
            <button class="btn btn-primary" onclick="refresh()">🔄 刷新</button>
        </div>
        
        <div class="card">
            <h2>🔔 提醒事项 <span class="reload-badge" id="lastUpdate"></span></h2>
            <div id="remindersList">
                <div class="empty-state">
                    <div class="icon">⏳</div>
                    <p>加载中...</p>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>📋 会议室规则速查</h2>
            <table>
                <thead><tr><th>会议室类型</th><th>提前天数</th><th>最长时长</th></tr></thead>
                <tbody>
                    <tr><td>2/3/4小</td><td>1天</td><td>1.5小时</td></tr>
                    <tr><td>5-9小 & 健身房</td><td>3天</td><td>1.5小时</td></tr>
                    <tr><td>10-13小</td><td>7天</td><td>1.5小时</td></tr>
                    <tr><td style="color:#f39c12;font-weight:bold;">4大(例外)</td><td style="color:#e74c3c;font-weight:bold;">3天</td><td>2小时</td></tr>
                    <tr><td style="color:#f39c12;font-weight:bold;">5大</td><td style="color:#e74c3c;font-weight:bold;">7天</td><td>2小时</td></tr>
                    <tr><td style="color:#f39c12;font-weight:bold;">6/7大</td><td style="color:#e74c3c;font-weight:bold;">10天</td><td>2小时</td></tr>
                    <tr><td>3大&培训室&瑜伽室</td><td>10天</td><td>4小时</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>💡 提示：凌晨00:00系统开放预订，建议设置闹钟卡点抢！</p>
            <p>🔔 大会议室资源紧张，请务必提前关注预订日期</p>
            <p>⚙️ 修改配置后点"保存"即生效，无需重启；或命令行直接改 config.yaml</p>
        </div>
    </div>

    <!-- 配置编辑模态框 -->
    <div id="editModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeEditor()">&times;</span>
            <h3>⚙️ 编辑会议室提醒配置</h3>
            <p style="color:#666;font-size:.9em;margin-bottom:10px">
                修改会议室规则 / 会议时间 / 提醒设置后点"保存并生效"。系统会自动备份旧配置。
            </p>
            <textarea id="configEditor" spellcheck="false"></textarea>
            <div id="saveMsg"></div>
            <button class="btn btn-success" onclick="saveConfig()">💾 保存并生效</button>
            <button class="btn btn-primary" onclick="closeEditor()">取消</button>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
        let currentData = [];
        let notifyEnabled = false;

        // ---- 声音闹钟 (Web Audio API 生成"叮咚") ----
        function beep() {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const freqs = [880, 660, 880, 660];
                freqs.forEach((f, i) => {
                    const o = ctx.createOscillator(), g = ctx.createGain();
                    o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
                    const t = ctx.currentTime + i * 0.25;
                    g.gain.setValueAtTime(0.3, t);
                    g.gain.exponentialRampToValueAtTime(0.01, t + 0.22);
                    o.start(t); o.stop(t + 0.22);
                });
            } catch(e) { console.log('beep failed', e); }
        }

        function showToast(msg, isError) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.style.background = isError ? '#e74c3c' : '#27ae60';
            t.style.display = 'block';
            setTimeout(() => t.style.display = 'none', 3000);
        }

        async function loadToday() {
            const res = await fetch('/api/today');
            const data = await res.json();
            renderReminders(data, '今日提醒');
            updateStats(data);
            document.getElementById('lastUpdate').textContent = '已更新 ' + new Date().toLocaleTimeString();
        }

        async function loadCalendar(weeks) {
            const res = await fetch(`/api/calendar?weeks=${weeks}`);
            const data = await res.json();
            renderReminders(data, `未来${weeks}周预约计划`);
            updateStats(data);
        }

        function updateStats(data) {
            const today = new Date().toDateString();
            const todayItems = data.filter(d => new Date(d.reminder_datetime).toDateString() === today);
            const urgent = data.filter(d => d.days_until_booking <= 1);
            document.getElementById('todayCount').textContent = todayItems.length || '0';
            document.getElementById('urgentCount').textContent = urgent.length || '0';
            document.getElementById('weekCount').textContent = data.filter(d => d.days_until_booking <= 7).length || '0';
        }

        function renderReminders(data, title) {
            currentData = data;
            const container = document.getElementById('remindersList');
            if (!data || data.length === 0) {
                container.innerHTML = `<div class="empty-state"><div class="icon">✅</div><p>太棒了！近期无需预约会议室</p></div>`;
                return;
            }
            const grouped = {};
            data.forEach(item => {
                const date = item.booking_date;
                if (!grouped[date]) grouped[date] = [];
                grouped[date].push(item);
            });
            let html = '';
            let hasUrgent = false;
            for (const [date, items] of Object.entries(grouped)) {
                html += `<h3 style="margin:15px 0 10px;color:#667eea;">📌 ${date}</h3>`;
                items.forEach(item => {
                    const isUrgent = item.days_until_booking <= 1;
                    const isLarge = item.room_type === 'large';
                    const classes = ['reminder-item'];
                    if (isUrgent) { classes.push('urgent'); hasUrgent = true; }
                    if (isLarge) classes.push('large-room');
                    html += `
                        <div class="${classes.join(' ')}">
                            <div class="meeting-name">
                                ${item.meeting_name}
                                ${item.require_large ? '<span class="room-tag tag-urgent">必须大会议室</span>' : ''}
                                ${isUrgent ? '<span class="room-tag tag-urgent">紧急</span>' : ''}
                            </div>
                            <div class="meeting-time">📅 ${item.meeting_date} (${item.meeting_weekday}) ${item.meeting_time}</div>
                            <div class="room-info">
                                🚪 可选: ${item.rooms}
                                <span class="room-tag ${isLarge ? 'tag-large' : 'tag-small'}">${isLarge ? '大会议室' : '小会议室'}</span>
                                <br/>⏰ 提前${item.advance_days}天 | 最长${item.max_duration}小时
                                ${item.notes ? `<br/>📝 ${item.notes}` : ''}
                            </div>
                            <div class="time-slots">🔀 备选时段: <span class="slot">${item.meeting_time.split('-')[0]}起</span><span class="slot">±30分钟</span></div>
                        </div>`;
                });
            }
            container.innerHTML = html;
            // 有紧急项且开启通知 → 响铃+弹窗
            if (hasUrgent && notifyEnabled) {
                beep();
                notify('🔔 抢会议室提醒', '今天有可预约的会议室，快去抢！');
            }
        }

        function refresh() { loadToday(); }

        // ---- 浏览器通知 ----
        function enableNotify() {
            if (!("Notification" in window)) {
                showToast('当前浏览器不支持通知', true); return;
            }
            if (Notification.permission === 'granted') {
                notifyEnabled = true;
                showToast('🔔 闹钟通知已开启');
                beep();
            } else if (Notification.permission !== 'denied') {
                Notification.requestPermission().then(p => {
                    if (p === 'granted') {
                        notifyEnabled = true;
                        showToast('🔔 闹钟通知已开启');
                        beep();
                    }
                });
            }
        }

        function notify(title, body) {
            try { new Notification(title, {body, icon: '🔔'}); } catch(e) {}
        }

        // ---- 在线编辑配置 ----
        async function openEditor() {
            const res = await fetch('/api/config');
            const data = await res.json();
            document.getElementById('configEditor').value = data.config || '';
            document.getElementById('editModal').style.display = 'block';
            document.getElementById('saveMsg').textContent = '';
        }
        function closeEditor() { document.getElementById('editModal').style.display = 'none'; }

        async function saveConfig() {
            const yaml = document.getElementById('configEditor').value;
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({config: yaml})
            });
            const data = await res.json();
            const msg = document.getElementById('saveMsg');
            if (data.ok) {
                msg.style.color = '#27ae60';
                msg.textContent = data.msg + ' (备份: ' + data.backup + ')';
                showToast('✅ 配置已实时生效');
                setTimeout(closeEditor, 1200);
                refresh(); // 立即刷新看板
            } else {
                msg.style.color = '#e74c3c';
                msg.textContent = data.msg;
            }
        }

        // 点击模态框外部关闭
        window.onclick = (e) => { if (e.target === document.getElementById('editModal')) closeEditor(); };

        // 页面加载时自动获取数据
        loadToday();
        // 每60秒自动刷新（实时感知配置变更 & 新提醒）
        setInterval(loadToday, 60000);
    </script>
</body>
</html>'''


if __name__ == '__main__':
    cli_mode()
