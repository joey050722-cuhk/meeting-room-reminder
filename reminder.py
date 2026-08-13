#!/usr/bin/env python3
"""
会议室预约提醒工具 - 核心逻辑
===============================
功能：
1. 读取会议配置
2. 计算每个会议的预订提醒时间
3. 生成提醒通知
4. 支持多时间段备选策略
"""

import yaml
from datetime import datetime, timedelta
from dateutil import parser
import json
import os
import subprocess
import shutil
import wave
import struct
import threading
import time

# 尝试导入通知库
try:
    from plyer import notification as desktop_notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


class MeetingRoomReminder:
    """会议室预约提醒核心类"""

    def __init__(self, config_path: str = None):
        """初始化，加载配置文件"""
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        
        self.config_path = os.path.abspath(config_path)
        self._load_config()

    def _load_config(self):
        """从文件加载配置（内部方法，支持热重载）"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.meeting_rules = self.config['meeting_room_rules']
            self.weekly_meetings = self.config['weekly_meetings']
    self.special_meetings = self.config.get('special_meetings', [])
    self.settings = self.config['reminder_settings']

    def reload_config(self):
        """🔄 实时重新加载配置文件（修改yaml后无需重启即可生效）"""
        self._load_config()
        return True

    def get_next_weekday(self, target_weekday: int, from_date: datetime = None) -> datetime:
        """
        获取下一个指定星期几的日期
        target_weekday: 0=周一, 1=周二, ..., 6=周日
        """
        if from_date is None:
            from_date = datetime.now()
        
        days_ahead = target_weekday - from_date.weekday()
        if days_ahead <= 0:  # 目标日已过或就是今天，取下周
            days_ahead += 7
        
        return from_date + timedelta(days=days_ahead)

    def calculate_booking_dates(self, meeting: dict) -> list:
        """
        计算会议的预订日期和对应的提醒时间
        返回：[(会议日期, 预订日期, 会议室规则, 提醒时间), ...]
        """
        results = []
        meeting_date = self.get_next_weekday(meeting['day_of_week'])
        
        # 解析会议时间
        start_time = datetime.strptime(meeting['start_time'], '%H:%M').time()
        duration = meeting.get('duration_hours', 1.0)
        
        # 确定需要的会议室类型
        preferred_type = meeting.get('preferred_room_type', 'any')
        require_large = meeting.get('require_large', False)
        
        # 根据会议需求匹配会议室规则
        applicable_rules = []
        for rule_name, rule in self.meeting_rules.items():
            room_type = rule.get('room_type', 'small')
            
            if require_large and room_type != 'large':
                continue
            
            if preferred_type == 'large' and room_type == 'large':
                applicable_rules.append((rule_name, rule))
            elif preferred_type == 'any':
                applicable_rules.append((rule_name, rule))
            elif preferred_type == 'large' and room_type != 'large':
                # 大会议室抢不到时的备选
                applicable_rules.append((rule_name, rule))
        
        # 按优先级排序（提前天数越少越优先处理）
        applicable_rules.sort(key=lambda x: x[1]['priority'])
        
        for rule_name, rule in applicable_rules:
            advance_days = rule['advance_days']
            booking_date = meeting_date - timedelta(days=advance_days)
            
            # 提醒时间：预订日的凌晨设定时间
            reminder_time = datetime.strptime(self.settings['reminder_time'], '%H:%M').time()
            reminder_datetime = datetime.combine(booking_date.date(), reminder_time)
            
            results.append({
                'meeting_name': meeting['name'],
                'meeting_date': meeting_date.strftime('%Y-%m-%d %A'),
                'meeting_time': f"{meeting['start_time']}-{meeting['end_time']}",
                'booking_date': booking_date.strftime('%Y-%m-%d %A'),
                'rule_name': rule_name,
                'rooms': rule['rooms'],
                'advance_days': advance_days,
                'max_duration': rule['max_duration_hours'],
                'room_type': rule.get('room_type', 'small'),
                'reminder_time': reminder_datetime.strftime('%Y-%m-%d %H:%M'),
                'is_urgent': (booking_date.date() - datetime.now().date()).days <= 1
            })
        
        return results

    def get_all_reminders(self, weeks_ahead: int = 2, include_past: bool = False) -> list:
        """
        获取未来N周内所有需要提醒的会议预订
        include_past=True 时不过滤已过提醒时间的项（邮件22:30/23:50提醒用）
        """
        all_reminders = []
        
        for meeting in self.weekly_meetings:
            # 获取未来几周的该会议
            for week in range(weeks_ahead + 1):
                base_date = datetime.now() + timedelta(weeks=week)
                meeting_date = self.get_next_weekday(meeting['day_of_week'], base_date)
                
                # 临时修改会议日期用于计算
                original_calc = self.calculate_booking_dates
                
                start_time = datetime.strptime(meeting['start_time'], '%H:%M').time()
                duration = meeting.get('duration_hours', 1.0)
                
                preferred_type = meeting.get('preferred_room_type', 'any')
                require_large = meeting.get('require_large', False)
                
                applicable_rules = []
                for rule_name, rule in self.meeting_rules.items():
                    room_type = rule.get('room_type', 'small')
                    
                    if require_large and room_type != 'large':
                        continue
                    
                    if preferred_type == 'large' and room_type == 'large':
                        applicable_rules.append((rule_name, rule))
                    elif preferred_type == 'any':
                        applicable_rules.append((rule_name, rule))
                    elif preferred_type != 'large':
                        applicable_rules.append((rule_name, rule))
                
                applicable_rules.sort(key=lambda x: x[1]['priority'])
                
                for rule_name, rule in applicable_rules:
                    advance_days = rule['advance_days']
                    booking_date = meeting_date - timedelta(days=advance_days)
                    
                    reminder_time = datetime.strptime(self.settings['reminder_time'], '%H:%M').time()
                    reminder_datetime = datetime.combine(booking_date.date(), reminder_time)
                    
                    all_reminders.append({
                        'meeting_name': meeting['name'],
                        'meeting_date': meeting_date.strftime('%Y-%m-%d'),
                        'meeting_weekday': ['周一','周二','周三','周四','周五','周六','周日'][meeting_date.weekday()],
                        'meeting_time': f"{meeting['start_time']}-{meeting['end_time']}",
                        'booking_date': booking_date.strftime('%Y-%m-%d'),
                        'booking_weekday': ['周一','周二','周三','周四','周五','周六','周日'][booking_date.weekday()],
                        'rule_name': rule_name,
                        'rooms': ', '.join(rule['rooms']),
                        'advance_days': advance_days,
                        'max_duration': rule['max_duration_hours'],
                        'room_type': rule.get('room_type', 'small'),
                        'reminder_datetime': reminder_datetime,
                        'require_large': meeting.get('require_large', False),
                        'notes': meeting.get('notes', ''),
                        'days_until_booking': (booking_date.date() - datetime.now().date()).days
                    })
        
        # 按提醒时间排序
        all_reminders.sort(key=lambda x: x['reminder_datetime'])
        
        if not include_past:
            # 默认过滤掉已经过去的（闹钟/常规提醒用）
            now = datetime.now()
            all_reminders = [r for r in all_reminders if r['reminder_datetime'] >= now]
        
        return all_reminders

    def get_today_reminders(self) -> list:
        """获取今天需要提醒的预订事项"""
        all_reminders = self.get_all_reminders()
        today = datetime.now().date()
        
        today_reminders = [
            r for r in all_reminders 
            if r['reminder_datetime'].date() == today
        ]
        
        return today_reminders

    def get_today_booking_items(self) -> list:
        """
        获取今天(预约日)所有可预约的会议预订项
        ⚠️ 不过滤已过提醒时间的项 —— 供22:30/23:50邮件提醒使用
        （此时当天00:00已过，但仍是预约日，需要照常提醒）
        """
        all_items = self.get_all_reminders(weeks_ahead=6, include_past=True)
        today = datetime.now().strftime('%Y-%m-%d')
        return [r for r in all_items if r['booking_date'] == today]

    def get_meeting_booking_calendar(self, meeting_name: str = None,
                                     meeting_date: str = None,
                                     focus_future_days: int = 14) -> list:
        """
        📅 目标会议抢购时间线（以会议为中心，显示哪天能抢哪个会议室）
        参数: meeting_name 会议名（模糊匹配）；meeting_date 'YYYY-MM-DD'
        focus_future_days: 只看未来N天内的可抢窗口（默认14天）
        返回: 按可抢时间排序的列表
        """
        all_items = self.get_all_reminders(weeks_ahead=6, include_past=True)

        # 匹配会议（名称）
        if meeting_name:
            all_items = [r for r in all_items if meeting_name.lower() in r['meeting_name'].lower()]
        # 匹配会议日期
        if meeting_date:
            all_items = [r for r in all_items if r['meeting_date'] == meeting_date]

        # 只看未来N天内可抢的（含今天）
        now = datetime.now().date()
        future = []
        for r in all_items:
            bd = datetime.strptime(r['booking_date'], '%Y-%m-%d').date()
            days = (bd - now).days
            if -3 <= days <= focus_future_days:  # 保留最近3天(已错过)作参考
                future.append(r)
        future.sort(key=lambda x: x['reminder_datetime'])
        return future

    def format_meeting_calendar(self, meeting_name: str = None,
                                meeting_date: str = None) -> str:
        """格式化输出目标会议抢购时间线（按会议分组，聚焦未来窗口）"""
        items = self.get_meeting_booking_calendar(meeting_name, meeting_date)
        if not items:
            return f"未找到会议: {meeting_name or ''} {meeting_date or ''}"

        now = datetime.now().date()
        lines = []

        # 按会议分组
        groups = {}
        for t in items:
            key = f"{t['meeting_name']}|{t['meeting_date']}|{t['meeting_weekday']}|{t['meeting_time']}"
            groups.setdefault(key, []).append(t)

        for key, group in groups.items():
            name, mdate, mweekday, mtime = key.split('|')
            lines.append(f"📅 会议：{name}  {mdate}({mweekday}) {mtime}")
            lines.append("-" * 52)

            missed = [t for t in group if (datetime.strptime(t['booking_date'], '%Y-%m-%d').date() - now).days < 0]
            upcoming = [t for t in group if (datetime.strptime(t['booking_date'], '%Y-%m-%d').date() - now).days >= 0]

            if missed:
                rooms = '、'.join(t['rooms'] for t in missed)
                lines.append(f"  ⚠️ 已错过: {rooms}（提前{missed[0]['advance_days']}天窗口）")

            for t in upcoming:
                days = (datetime.strptime(t['booking_date'], '%Y-%m-%d').date() - now).days
                if days == 0:
                    status = "🔥 今天00:00开抢"
                elif days == 1:
                    status = "⏰ 明天00:00开抢"
                else:
                    status = f"📋 {days}天后00:00"
                room_type = "🏛️大" if t.get('room_type') == 'large' else "🚪小"
                lines.append(f"  {t['booking_date']}({t['booking_weekday']}) → {t['rooms']} {room_type} [{status}]")

            lines.append("")

        lines.append("💡 大会议室窗口：5大(7天)/4大(3天)/6-7大(10天)，盯紧最近的 📋 标注！")
        return "\n".join(lines)

    def generate_backup_time_slots(self, meeting: dict) -> list:
        """
        为单个会议生成备选时间段
        返回：[(开始时间, 结束时间), ...]
        """
        slots = []
        base_start = datetime.strptime(meeting['start_time'], '%H:%M')
        duration_minutes = int(meeting.get('duration_hours', 1.0) * 60)
        
        strategy = self.settings.get('backup_strategy', {})
        if strategy.get('enabled', True):
            offsets = strategy.get('time_slots', [{'offset_minutes': 0}])
        else:
            offsets = [{'offset_minutes': 0}]
        
        for offset in offsets[:self.settings.get('backup_strategy', {}).get('max_attempts', 3)]:
            offset_min = offset.get('offset_minutes', 0)
            new_start = base_start + timedelta(minutes=offset_min)
            new_end = new_start + timedelta(minutes=duration_minutes)
            
            # 确保时间在合理范围内（8:00-20:00）
            if 8 <= new_start.hour < 20 and 8 <= new_end.hour <= 20:
                slots.append({
                    'start': new_start.strftime('%H:%M'),
                    'end': new_end.strftime('%H:%M'),
                    'offset': offset_min
                })
        
        return slots
    def format_daily_checklist(self) -> str:
        """
        📋 今晚需要预约的会议室清单（用户定制格式）
        明天00:00要抢的：固定会议大会议室 + 特殊会议 + 备用小会议室
        """
        weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        items = []

        # === 1a. 明天可抢的周期性固定会议大会议室 ===
        for meeting in self.weekly_meetings:
            mday_of_week = meeting['day_of_week']
            delta_days = (mday_of_week - today.weekday()) % 7
            if delta_days == 0:
                delta_days = 7
            first_meeting = today + timedelta(days=delta_days)
            if first_meeting < tomorrow:
                first_meeting += timedelta(days=7)
            week_offset = 0
            while week_offset < 4:
                meeting_date = first_meeting + timedelta(weeks=week_offset)
                matched_large = []
                matched_special = []
                for rule_name, rule in self.meeting_rules.items():
                    adv = rule['advance_days']
                    rtype = rule.get('room_type', 'small')
                    if meeting_date - timedelta(days=adv) == tomorrow:
                        rooms_str = '、'.join(rule['rooms'])
                        if rtype == 'large':
                            matched_large.append(rooms_str)
                        elif rtype == 'special':
                            matched_special.append(rooms_str)
                if matched_large or matched_special:
                    rooms_all = matched_large + matched_special
                    items.append({
                        'date': meeting_date, 'weekday': weekday_cn[meeting_date.weekday()],
                        'name': meeting['name'], 'rooms': '；'.join(rooms_all),
                        'time': f"{meeting['start_time']}-{meeting['end_time']}"
                    })
                week_offset += 1

        # === 1b. 明天可抢的特殊会议 ===
        for meeting in self.special_meetings:
            try:
                mdate = datetime.strptime(meeting['date'], '%Y-%m-%d')
            except Exception:
                continue
            matched_large = []
            matched_special = []
            for rule_name, rule in self.meeting_rules.items():
                adv = rule['advance_days']
                rtype = rule.get('room_type', 'small')
                if mdate - timedelta(days=adv) == tomorrow:
                    rooms_str = '、'.join(rule['rooms'])
                    if rtype == 'large':
                        matched_large.append(rooms_str)
                    elif rtype == 'special':
                        matched_special.append(rooms_str)
            if matched_large or matched_special:
                rooms_all = matched_large + matched_special
                items.append({
                    'date': mdate, 'weekday': weekday_cn[mdate.weekday()],
                    'name': meeting['name'], 'rooms': '；'.join(rooms_all),
                    'time': f"{meeting['start_time']}-{meeting['end_time']}"
                })

        # === 2. 明天可约的备用小会议室 ===
        backup_time_str = "11:00-12:00, 15:00-16:00"
        backup_by_date = {}
        for rule_name, rule in self.meeting_rules.items():
            rtype = rule.get('room_type', 'small')
            if rtype == 'large' or rtype == 'special':
                continue
            adv = rule['advance_days']
            max_date = tomorrow + timedelta(days=adv)
            if max_date not in backup_by_date:
                backup_by_date[max_date] = {
                    'date': max_date, 'weekday': weekday_cn[max_date.weekday()],
                    'rooms': '、'.join(rule['rooms']), 'time': backup_time_str
                }
            else:
                backup_by_date[max_date]['rooms'] += '；' + '、'.join(rule['rooms'])
        for d in sorted(backup_by_date.keys()):
            b = backup_by_date[d]
            items.append({
                'date': d, 'weekday': b['weekday'], 'name': '预备会议室',
                'rooms': b['rooms'], 'time': b['time']
            })

        # 排序：会议优先，预备在后；同组按日期
        items.sort(key=lambda x: (x['name'] == '预备会议室', x['date']))

        lines = []
        lines.append("# 今晚需要预约的会议室清单")
        lines.append("")
        if not items:
            lines.append("（今晚没有需要预约的会议）")
            lines.append("")
        else:
            for i, it in enumerate(items, 1):
                lines.append(f"{i}. **{it['date']}（{it['weekday']}）｜{it['name']}**")
                lines.append(f"   - 会议室：{it['rooms']}")
                lines.append(f"   - 时段：{it['time']}")
                lines.append("")
        lines.append("备注：6/7大、3大/培训/瑜伽 提前10天；5大、10-13小 提前7天；4大、5-9小/健身房 提前3天；2-4小 提前1天。")
        return "\n".join(lines)


    def format_reminder_text(self, reminders: list) -> str:
        """格式化提醒文本"""
        if not reminders:
            return "📅 近期无需预约会议室"
        
        lines = ["=" * 60]
        lines.append("🏢 会议室预约提醒")
        lines.append("=" * 60)
        lines.append(f"📅 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        
        # 按预订日期分组
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in reminders:
            grouped[r['booking_date']].append(r)
        
        for booking_date in sorted(grouped.keys()):
            lines.append(f"📌 【{booking_date}】需预约:")
            lines.append("-" * 50)
            
            for r in grouped[booking_date]:
                urgency = "🔥" if r['days_until_booking'] <= 1 else "📋"
                large_mark = "🏛️大" if r['room_type'] == 'large' else "🚪小"
                required = " ⚠️必须" if r.get('require_large') else ""
                
                lines.append(f"  {urgency} {r['meeting_name']} ({r['meeting_weekday']} {r['meeting_time']})")
                lines.append(f"     → 会议日期: {r['meeting_date']}")
                lines.append(f"     → 可选会议室: {r['rooms']} {large_mark}{required}")
                lines.append(f"     → 提前天数: {r['advance_days']}天 | 最长可订: {r['max_duration']}小时")
                
                if r.get('notes'):
                    lines.append(f"     📝 {r['notes']}")
                
                # 备选时间段
                backup_slots = self.generate_backup_time_slots(
                    next(m for m in self.weekly_meetings if m['name'] == r['meeting_name'])
                )
                if len(backup_slots) > 1:
                    slot_str = " | ".join([f"{s['start']}-{s['end']}" for s in backup_slots])
                    lines.append(f"     🔀 备选时段: {slot_str}")
                
                lines.append("")
        
        lines.append("=" * 60)
        lines.append("💡 提示: 凌晨卡点抢！建议提前准备好要约的时间段")
        
        return "\n".join(lines)

    # ============================================================
    #  声音闹钟 & 桌面弹窗（跨平台）
    # ============================================================
    def _ensure_alarm_sound(self) -> str:
        """确保提示音文件存在，返回wav路径（首次运行自动生成）"""
        assets_dir = os.path.join(os.path.dirname(self.config_path), 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        wav_path = os.path.join(assets_dir, 'alarm.wav')
        
        if os.path.exists(wav_path):
            return wav_path
        
        # 生成一段"叮咚-叮咚"提示音
        try:
            import math
            sample_rate = 44100
            frames = []
            # 两段"叮-咚"，每段0.25s
            for freq in [880, 660, 880, 660]:
                for i in range(int(sample_rate * 0.22)):
                    t = i / sample_rate
                    # 带衰减包络，避免爆音
                    env = math.exp(-3 * t)
                    val = int(32767 * 0.6 * env * math.sin(2 * math.pi * freq * t))
                    frames.append(struct.pack('<h', val))
                # 间隔
                frames.append(struct.pack('<h', 0) * 1000)
            
            with wave.open(wav_path, 'w') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(b''.join(frames))
        except Exception as e:
            print(f"[生成提示音失败] {e}")
        
        return wav_path

    def play_alarm_sound(self):
        """🔔 播放闹钟声音（多后端自动降级）"""
        wav = self._ensure_alarm_sound()
        if not os.path.exists(wav):
            # 退化方案：终端响铃
            print("\a\a\a", end='', flush=True)
            return
        
        played = False
        # 1) macOS
        if shutil.which('afplay'):
            try:
                subprocess.run(['afplay', wav], check=False, timeout=5)
                played = True
            except Exception:
                pass
        # 2) Windows
        elif shutil.which('powershell'):
            try:
                subprocess.run(['powershell', '-c',
                                f'(New-Object Media.SoundPlayer "{wav}").PlaySync()'],
                               check=False, timeout=5)
                played = True
            except Exception:
                pass
        # 3) Linux (paplay/aplay)
        elif shutil.which('paplay') or shutil.which('aplay'):
            player = shutil.which('paplay') or shutil.which('aplay')
            try:
                subprocess.run([player, wav], check=False, timeout=5)
                played = True
            except Exception:
                pass
        # 4) 终端响铃兜底
        if not played:
            print("\a\a\a", end='', flush=True)

    def _desktop_popup(self, title: str, message: str):
        """跨平台桌面弹窗（尽力而为，失败不影响主流程）"""
        # 1) plyer
        if HAS_PLYER:
            try:
                desktop_notification.notify(
                    title=title, message=message[:200],
                    app_name="会议室助手", timeout=10
                )
                return True
            except Exception:
                pass
        # 2) macOS osascript 弹对话框
        if shutil.which('osascript'):
            try:
                script = f'display notification "{message[:150]}" with title "{title}" sound name "Glass"'
                subprocess.run(['osascript', '-e', script], check=False, timeout=5)
                return True
            except Exception:
                pass
        # 3) Linux notify-send
        if shutil.which('notify-send'):
            try:
                subprocess.run(['notify-send', title, message[:200]],
                               check=False, timeout=5)
                return True
            except Exception:
                pass
        # 4) Windows powershell toast
        if shutil.which('powershell'):
            try:
                ps = f'''
$toast = New-BurntToastNotification -Text "{title}", "{message[:150]}" -ErrorAction SilentlyContinue
'''
                subprocess.run(['powershell', '-c', ps], check=False, timeout=5)
                return True
            except Exception:
                pass
        return False

    def send_notification(self, title: str, message: str, with_alarm: bool = True):
        """发送通知（控制台 + 桌面弹窗 + 声音 + 文件保存）"""
        # 控制台输出（高亮）
        if self.settings['notification'].get('console', True):
            print("\n" + "=" * 60)
            print(f"🔔 {title}")
            print("=" * 60)
            print(message)
            print("=" * 60 + "\n")
            # 终端响铃（即使没有桌面环境也有提示）
            if with_alarm:
                print("\a", end='', flush=True)
        
        # 桌面弹窗
        if self.settings['notification'].get('desktop', True):
            self._desktop_popup(title, message)
        
        # 声音闹钟
        if with_alarm and self.settings['notification'].get('sound', True):
            try:
                self.play_alarm_sound()
            except Exception as e:
                print(f"[闹钟播放失败] {e}")
        
        # 保存到文件
        output_dir = os.path.join(os.path.dirname(self.config_path), 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(output_dir, f'reminder_{timestamp}.txt')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"{title}\n{'='*60}\n")
            f.write(message)
        
        print(f"[已保存] {output_file}")

    # ============================================================
    #  邮件提醒（Outlook/Office365）
    # ============================================================
    def _email_config(self) -> dict:
        """读取邮件配置，未启用返回 None"""
        email_cfg = self.config.get('email', {})
        if not email_cfg.get('enabled'):
            return None
        return email_cfg

    def send_email(self, subject: str, body: str) -> bool:
        """
        发送邮件（SMTP，支持 Outlook/Office365）
        返回 True=发送成功，False=失败/未配置
        """
        email_cfg = self._email_config()
        if not email_cfg:
            print("⚠️  邮件提醒未启用：请在 config.yaml 的 email 段填入密码并 enabled: true")
            return False

        sender = email_cfg.get('sender', '')
        password = email_cfg.get('password', '')
        recipients = email_cfg.get('recipients', [])
        server_host = email_cfg.get('smtp_server', 'smtp.office365.com')
        server_port = int(email_cfg.get('smtp_port', 587))

        if not password:
            print("⚠️  邮件密码为空：请在 config.yaml 的 email.password 填入（Outlook安全设置中生成应用密码）")
            return False
        if not recipients:
            print("⚠️  收件人为空：请在 config.yaml 的 email.recipients 配置")
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.header import Header

            msg = MIMEText(body, 'plain', 'utf-8')
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = sender
            msg['To'] = ', '.join(recipients)
            msg['X-Priority'] = '1'  # 高优先级

            with smtplib.SMTP(server_host, server_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, recipients, msg.as_string())

            print(f"✅ 邮件已发送: {subject} → {', '.join(recipients)}")
            return True
        except Exception as e:
            print(f"❌ 邮件发送失败: {e}")
            return False

    def _build_email_body(self, reminders: list, phase: str) -> str:
        """生成邮件正文，标明会议主题、时间、会议室"""
        lines = []
        lines.append("🔔 会议室预约提醒")
        lines.append("=" * 50)
        lines.append(f"📅 日期: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("")

        if phase == 'evening':
            lines.append("🌙 晚间预告：明天凌晨将开放预订，请提前准备！")
        else:
            lines.append("🚨 临开抢提醒：距离开抢不到10分钟，请立即准备！")
        lines.append("")

        lines.append("📋 今日可预约的会议：")
        lines.append("-" * 50)

        for i, r in enumerate(reminders, 1):
            req = " ⚠️必须大会议室" if r.get('require_large') else ""
            lines.append(f"{i}. 【{r['meeting_name']}】{req}")
            lines.append(f"   会议时间: {r['meeting_date']} ({r['meeting_weekday']}) {r['meeting_time']}")
            lines.append(f"   可选会议室: {r['rooms']} (提前{r['advance_days']}天可订)")
            if r.get('notes'):
                lines.append(f"   备注: {r['notes']}")
            lines.append("")

        lines.append("⏰ 开抢时间：每天 00:00（临近第二天零点开放）")
        lines.append("🏢 建议：大会议室优先，可同时预约多个备选时段")
        lines.append("")
        lines.append("—— 会议室预约提醒助手 自动发送")

        return "\n".join(lines)

    def email_reminder(self, phase: str = 'auto'):
        """
        发送预约日邮件提醒
        phase: 'evening'=晚间预告(22:30) / 'final'=临开抢(23:50) / 'auto'=按当前时间判断
        """
        if phase == 'auto':
            phase = 'final' if datetime.now().hour >= 23 else 'evening'

        # 获取今天的预订事项（预约日当天，22:30/23:50运行）
        todays = self.get_today_booking_items()
        if not todays:
            print(f"✅ [{phase}] 今天没有可预约的会议，无需发邮件")
            return False

        email_cfg = self._email_config()
        if not email_cfg:
            print("⚠️  邮件提醒未启用，跳过")
            return False

        # 邮件标题（标明会议主题）
        meeting_names = '、'.join(sorted(set(r['meeting_name'] for r in todays)))
        if phase == 'evening':
            subject = f"🌙 明晨开抢提醒：{meeting_names} 可预约"
        else:
            subject = f"🚨 临开抢！{meeting_names} 10分钟后开抢"

        body = self._build_email_body(todays, phase)
        return self.send_email(subject, body)

    # ============================================================
    #  企业微信提醒（群机器人 Webhook）
    # ============================================================
    def _wecom_config(self) -> dict:
        """读取企业微信配置，未启用返回 None"""
        cfg = self.config.get('wecom', {})
        if not cfg.get('enabled'):
            return None
        return cfg

    def send_wecom(self, content: str) -> bool:
        """
        发送企业微信群消息（markdown格式）
        返回 True=成功，False=失败/未配置
        """
        cfg = self._wecom_config()
        if not cfg:
            print("⚠️  企业微信提醒未启用：请在 config.yaml 的 wecom 段填入 webhook_url 并 enabled: true")
            return False

        url = cfg.get('webhook_url', '')
        if not url:
            print("⚠️  企业微信 webhook_url 为空，请在 config.yaml 配置")
            return False

        try:
            import urllib.request
            payload = json.dumps({
                "msgtype": "markdown",
                "markdown": {"content": content}
            }, ensure_ascii=False).encode('utf-8')

            req = urllib.request.Request(url, data=payload,
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            if result.get('errcode') == 0:
                print("✅ 企业微信消息已发送")
                return True
            else:
                print(f"❌ 企业微信发送失败: {result.get('errmsg', '未知错误')} (errcode={result.get('errcode')})")
                return False
        except Exception as e:
            print(f"❌ 企业微信发送异常: {e}")
            return False

    def _build_wecom_body(self, reminders: list, phase: str) -> str:
        """生成企业微信markdown消息体，标明会议主题及时间"""
        meeting_names = '、'.join(sorted(set(r['meeting_name'] for r in reminders)))
        lines = []
        if phase == 'evening':
            lines.append(f"## 🌙 明晨开抢提醒：{meeting_names}")
            lines.append("> 明天凌晨将开放预订，请提前准备！")
        else:
            lines.append(f"## 🚨 临开抢！{meeting_names} 10分钟后开抢")
            lines.append("> **立即准备抢会议室！**")

        lines.append(f"**📅 日期**：{datetime.now().strftime('%m月%d日')}")
        lines.append("")
        lines.append("**📋 今日可预约的会议：**")

        for i, r in enumerate(reminders, 1):
            req = " ⚠️必须大会议室" if r.get('require_large') else ""
            lines.append(f"**{i}. {r['meeting_name']}**{req}")
            lines.append(f"> 🗓️ 会议时间：{r['meeting_date']}({r['meeting_weekday']}) {r['meeting_time']}")
            lines.append(f"> 🚪 可选：{r['rooms']}（提前{r['advance_days']}天可订）")
            if r.get('notes'):
                lines.append(f"> 📝 {r['notes']}")
            lines.append("")

        lines.append(f"**⏰ 开抢时间**：明天 <font color=\"warning\">00:00</font>")
        lines.append("🏢 建议：大会议室优先，可同时预约多个备选时段")

        # 重点提示：下一场大会议室窗口
        try:
            large_next = [r for r in reminders if r.get('room_type') == 'large']
            if large_next:
                # 找最近的一场大会议室会议
                lines.append("")
                lines.append(f"**🔥 重点**：{large_next[0]['meeting_name']} 的 {large_next[0]['rooms']} 在 {large_next[0]['booking_date']} 00:00 开抢，别错过！")
        except Exception:
            pass

        return "\n".join(lines)

    def wecom_reminder(self, phase: str = 'auto'):
        """发送预约日企业微信提醒（evening=晚间预告/final=临开抢）"""
        if phase == 'auto':
            phase = 'final' if datetime.now().hour >= 23 else 'evening'

        todays = self.get_today_booking_items()
        if not todays:
            print(f"✅ [{phase}] 今天没有可预约的会议，无需发送")
            return False

        if not self._wecom_config():
            print("⚠️  企业微信提醒未启用，跳过")
            return False

        content = self._build_wecom_body(todays, phase)
        return self.send_wecom(content)

    # ============================================================
    #  微信推送（Server酱 / PushPlus —— 无需建群，推到个人微信）
    # ============================================================
    def send_serverchan(self, title: str, content: str = '') -> bool:
        """
        Server酱3 微信推送
        获取key: 微信扫码登录 https://sct.ftqq.com → 复制SendKey
        """
        cfg = self.config.get('serverchan', {})
        if not (cfg.get('enabled') or os.environ.get('SENDKEY')):
            print("⚠️  微信推送(Server酱)未启用：请在 config.yaml 填入 sendkey")
            return False
        key = os.environ.get('SENDKEY') or cfg.get('sendkey', '')
        if not key:
            print("⚠️  Server酱 sendkey 为空（可用环境变量 SENDKEY 或 config.yaml）")
            return False

        try:
            import urllib.request
            import urllib.parse
            url = f"https://sctapi.ftqq.com/{key}.send"
            data = urllib.parse.urlencode({
                'title': title,
                'desp': content[:8000]
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            if result.get('code') == 0:
                print("✅ 微信推送(Server酱)已发送")
                return True
            else:
                print(f"❌ Server酱发送失败: {result.get('message')}")
                return False
        except Exception as e:
            print(f"❌ Server酱发送异常: {e}")
            return False

    def send_pushplus(self, title: str, content: str = '') -> bool:
        """
        PushPlus 微信推送
        获取token: 微信扫码关注 https://www.pushplus.plus → 一对一推送里复制token
        """
        cfg = self.config.get('pushplus', {})
        if not cfg.get('enabled'):
            print("⚠️  微信推送(PushPlus)未启用：请在 config.yaml 填入 token")
            return False
        token = cfg.get('token', '')
        if not token:
            print("⚠️  PushPlus token 为空")
            return False

        try:
            import urllib.request
            import urllib.parse
            url = "https://www.pushplus.plus/send"
            data = urllib.parse.urlencode({
                'token': token,
                'title': title,
                'content': content[:8000]
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            if result.get('code') == 200:
                print("✅ 微信推送(PushPlus)已发送")
                return True
            else:
                print(f"❌ PushPlus发送失败: {result.get('msg')}")
                return False
        except Exception as e:
            print(f"❌ PushPlus发送异常: {e}")
            return False

        def send_wechat(self, title: str, content: str = '') -> bool:
        """发送微信推送：Server酱 / PushPlus 哪个配了发哪个（含环境变量，云端场景）"""
        sent = False
        if self.config.get('serverchan', {}).get('enabled') or os.environ.get('SENDKEY'):
            sent = self.send_serverchan(title, content) or sent
        if self.config.get('pushplus', {}).get('enabled') or os.environ.get('PUSHPLUS_TOKEN'):
            sent = self.send_pushplus(title, content) or sent
        return sent

    def _build_wechat_content(self, reminders: list, phase: str) -> str:
        """生成微信推送正文（纯文本，标明会议主题及时间）"""
        meeting_names = '、'.join(sorted(set(r['meeting_name'] for r in reminders)))
        lines = []
        if phase == 'evening':
            lines.append(f"🌙 明晨开抢提醒：{meeting_names}")
            lines.append("明天凌晨将开放预订，请提前准备！")
        else:
            lines.append(f"🚨 临开抢！{meeting_names} 10分钟后开抢")
            lines.append("立即准备抢会议室！")

        lines.append(f"📅 日期：{datetime.now().strftime('%m月%d日')}")
        lines.append("")
        lines.append("📋 今日可预约的会议：")
        for i, r in enumerate(reminders, 1):
            req = " ⚠️必须大会议室" if r.get('require_large') else ""
            lines.append(f"{i}. 【{r['meeting_name']}】{req}")
            lines.append(f"   🗓️ {r['meeting_date']}({r['meeting_weekday']}) {r['meeting_time']}")
            lines.append(f"   🚪 {r['rooms']}（提前{r['advance_days']}天可订）")
            if r.get('notes'):
                lines.append(f"   📝 {r['notes']}")
            lines.append("")

        lines.append("⏰ 开抢时间：每天 00:00")
        lines.append("🏢 大会议室优先，可同时约多个备选时段")
        return "\n".join(lines)

    def send_reminders(self, phase: str = 'auto'):
        """
        统一提醒入口：按 config 中启用的渠道发送（企业微信 / 微信推送 / 邮件）
        phase: evening(22:30) / final(23:50) / auto
        """
        if phase == 'auto':
            phase = 'final' if datetime.now().hour >= 23 else 'evening'

        todays = self.get_today_booking_items()
        if not todays:
            print(f"✅ [{phase}] 今天没有可预约的会议，无需提醒")
            return

        sent = 0
        # 企业微信
        if self._wecom_config():
            content = self._build_wecom_body(todays, phase)
            if self.send_wecom(content):
                sent += 1
        # 微信推送 (Server酱 / PushPlus) —— 晚间统一发"今晚清单"
    sc_enabled = self.config.get('serverchan', {}).get('enabled') or os.environ.get('SENDKEY')
    pp_enabled = self.config.get('pushplus', {}).get('enabled') or os.environ.get('PUSHPLUS_TOKEN')
    if sc_enabled or pp_enabled:
        if phase == 'evening':
            if self.send_wechat("📋 今晚需要预约的会议室清单", self.format_daily_checklist()):
                sent += 1
        else:
            meeting_names = '、'.join(sorted(set(r['meeting_name'] for r in todays)))
            title = f"🚨 临开抢！{meeting_names} 10分钟后开抢"
            if self.send_wechat(title, self._build_wechat_content(todays, phase)):
                sent += 1
        # 邮件
        if self._email_config():
            meeting_names = '、'.join(sorted(set(r['meeting_name'] for r in todays)))
            if phase == 'evening':
                subject = f"🌙 明晨开抢提醒：{meeting_names} 可预约"
            else:
                subject = f"🚨 临开抢！{meeting_names} 10分钟后开抢"
            if self.send_email(subject, self._build_email_body(todays, phase)):
                sent += 1

        if sent == 0:
            print("⚠️  未配置任何提醒渠道（企业微信/微信推送/邮件），请在 config.yaml 启用")

    def run_daily_check(self):
        """每日检查入口"""
        print(f"\n🔄 开始每日检查... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        
        # 获取今天需要提醒的事项
        today_reminders = self.get_today_reminders()
        
        if today_reminders:
            text = self.format_reminder_text(today_reminders)
            self.send_notification(
                "🔔 会议室预约提醒 - 今天可以预约啦！",
                text
            )
        else:
            # 显示近期待办
            upcoming = self.get_all_reminders()[:5]  # 接下来5个提醒
            if upcoming:
                text = self.format_reminder_text(upcoming)
                self.send_notification(
                    "📋 近期会议室预约计划",
                    text
                )
            else:
                print("\n✅ 近期无需要预约的会议室")

    def show_calendar_view(self, weeks: int = 2):
        """显示日历视图"""
        reminders = self.get_all_reminders(weeks_ahead=weeks)
        text = self.format_reminder_text(reminders)
        self.send_notification(f"📆 未来{weeks}周会议室预约日历", text)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='会议室预约提醒工具')
    parser.add_argument('--config', '-c', help='配置文件路径')
    parser.add_argument('--today', '-t', action='store_true', help='查看今日提醒')
    parser.add_argument('--calendar', '-l', type=int, default=2, help='查看未来N周日历')
    parser.add_argument('--setup-cron', action='store_true', help='设置定时任务')
    
    args = parser.parse_args()
    
    reminder = MeetingRoomReminder(args.config)
    
    if args.today:
        reminder.run_daily_check()
    elif args.calendar:
        reminder.show_calendar_view(args.calendar)
    elif args.setup_cron:
        setup_crontab()
    else:
        # 默认显示日历视图
        reminder.show_calendar_view()


def setup_crontab():
    """设置cron定时任务"""
    cron_line = "0 0 * * * cd /workspace/meeting-room-reminder && python3 main.py --today >> /workspace/meeting-room-reminder/cron.log 2>&1"
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║              设置定时任务 (Crontab)                         ║
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║  请手动执行以下命令添加定时任务：                            ║
║                                                           ║
║  crontab -e                                               ║
║                                                           ║
║  然后添加以下行：                                          ║
║                                                           ║
""" + f"""║  {cron_line}
║                                                           ║
║  这将在每天凌晨 00:00 自动运行提醒检查                      ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")


if __name__ == '__main__':
    main()
