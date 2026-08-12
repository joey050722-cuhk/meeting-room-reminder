#!/usr/bin/env python3
"""
会议室状态检查工具（Windows + Outlook）
=========================================
通过 Outlook 的 FreeBusy 接口，一键查询所有会议室在目标时间段的忙闲状态，
避免和同事（如Athena）抢冲突。抢之前跑一下就知道哪些会议室能用。

用法示例:
  # 1. 查单个时间段（你的会议时间）
  python check_rooms.py --date 2026-08-19 --start 11:00 --end 12:00

  # 2. 查时间段矩阵（多个备选时间段 x 所有会议室）
  python check_rooms.py --date 2026-08-19 --start 10:00 --end 13:00 --step 30

  # 3. 只看大会议室
  python check_rooms.py --date 2026-08-19 --start 11:00 --end 12:00 --type large
"""

import argparse
import datetime
import os
import sys
import yaml


def load_config():
    """读取配置文件"""
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_room_emails(cfg, room_type=None):
    """从配置读取会议室资源邮箱映射，可按类型过滤"""
    emails = cfg.get('room_emails', {})
    if not emails:
        print("❌ config.yaml 里没有 room_emails 配置")
        return {}

    # 过滤未填写的占位
    filtered = {}
    for room, email in emails.items():
        if not email or '请填入' in str(email):
            continue
        if room_type and room_type == 'large' and '大' not in room:
            continue
        if room_type and room_type == 'small' and '小' not in room:
            continue
        filtered[room] = email
    return filtered


def get_outlook():
    """连接本机Outlook"""
    try:
        import win32com.client
    except ImportError:
        print("❌ 需要安装 pywin32，请运行: pip install pywin32")
        sys.exit(1)

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        return outlook
    except Exception as e:
        print(f"❌ 无法连接Outlook: {e}")
        print("  请确认: 1) 电脑已安装Outlook 2) 已登录邮箱 3) Outlook正在运行")
        sys.exit(1)


def query_freebusy(outlook, room_email, target_date, slot_start, slot_end):
    """
    查询单个会议室在 [slot_start, slot_end] 的忙闲
    返回: (status, detail)
    status: 'free'空闲 / 'busy'忙 / 'tentative'暂定 / 'unknown'未知
    """
    try:
        ns = outlook.GetNamespace("MAPI")
        recipient = ns.CreateRecipient(room_email)
        if not recipient.Resolve():
            return ('unknown', '邮箱无法解析')

        # FreeBusy(start, minPerChar, completeFormat)：从当天0点起，每30分钟一个字符
        day_start = datetime.datetime.combine(target_date, datetime.time(0, 0))
        fb = recipient.FreeBusy(day_start, 30, False)

        # 解析目标时间段对应的字符范围
        start_min = slot_start.hour * 60 + slot_start.minute
        end_min = slot_end.hour * 60 + slot_end.minute
        idx_a = start_min // 30
        idx_b = min((end_min - 1) // 30, len(fb) - 1)

        segment = fb[idx_a:idx_b + 1] if fb else ''
        if 'B' in segment:
            return ('busy', '被占用')
        if 'O' in segment:
            return ('busy', '外出/占用')
        if 'T' in segment:
            return ('tentative', '暂定占用')
        return ('free', '空闲')
    except Exception as e:
        return ('unknown', f'查询失败: {e}')


def build_slots(start_str, end_str, step_min):
    """生成时间段列表"""
    def to_time(s):
        h, m = map(int, s.split(':'))
        return datetime.time(h, m)

    start = to_time(start_str)
    end = to_time(end_str)
    slots = []
    cur = datetime.datetime.combine(datetime.date.today(), start)
    end_dt = datetime.datetime.combine(datetime.date.today(), end)
    while cur < end_dt:
        slot_end = cur + datetime.timedelta(minutes=step_min)
        if slot_end > end_dt:
            break
        slots.append((cur.time(), slot_end.time()))
        cur = slot_end
    return slots


def parse_date(date_str):
    """解析日期，支持 2026-08-19 或 8/19 或 0819"""
    try:
        if '-' in date_str:
            parts = date_str.split('-')
            return datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif '/' in date_str:
            parts = date_str.split('/')
            y = int(parts[0]) if len(parts[0]) == 4 else datetime.date.today().year
            return datetime.date(y, int(parts[1]), int(parts[2]))
        else:
            return datetime.datetime.strptime(date_str, '%m%d').date().replace(year=datetime.date.today().year)
    except Exception:
        print(f"❌ 日期格式不对: {date_str}，请用 2026-08-19 或 8/19")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='会议室状态检查（Outlook FreeBusy）')
    parser.add_argument('--date', '-d', required=True, help='目标日期，如 2026-08-19')
    parser.add_argument('--start', '-s', required=True, help='开始时间，如 11:00')
    parser.add_argument('--end', '-e', required=True, help='结束时间，如 12:00')
    parser.add_argument('--step', '-t', type=int, default=30, help='矩阵模式步长(分钟)，默认30')
    parser.add_argument('--type', '-ty', choices=['large', 'small', 'all'], default='all',
                        help='只看大会议室(large)或小会议室(small)，默认全部')
    args = parser.parse_args()

    cfg = load_config()
    target_date = parse_date(args.date)
    rooms = get_room_emails(cfg, args.type if args.type != 'all' else None)

    if not rooms:
        print("❌ 没有可用的会议室邮箱配置！")
        print("   请先在 config.yaml 的 room_emails 段填入实际会议室资源邮箱")
        print("   （Outlook里添加会议室时能看到，形如 xxx@hh.global）")
        sys.exit(1)

    # 生成时间段
    slots = build_slots(args.start, args.end, args.step)

    outlook = get_outlook()

    print()
    print(f"📅 目标日期: {target_date} ({'一二三四五六日'[target_date.weekday()]}周)")
    print(f"🕐 时间段: {args.start} - {args.end} (步长{args.step}分钟, {len(slots)}个时段)")
    print(f"🏢 会议室数: {len(rooms)} 个")
    print("=" * 70)

    if len(slots) == 1:
        # 单时间段模式：详细列出
        slot = slots[0]
        print(f"\n📌 {slot[0]} - {slot[1]}  会议室状态：")
        print("-" * 70)
        free_list, busy_list = [], []
        for room, email in rooms.items():
            status, detail = query_freebusy(outlook, email, target_date, slot[0], slot[1])
            if status == 'free':
                free_list.append(room)
                mark = "✅ 空闲"
            elif status == 'tentative':
                mark = "🟡 暂定"
            else:
                busy_list.append(room)
                mark = "❌ 占用"
            print(f"  {mark}  {room:<6} ({email})")

        print("-" * 70)
        print(f"✅ 空闲可用: {'、'.join(free_list) if free_list else '无'}")
        print(f"❌ 已占用: {'、'.join(busy_list) if busy_list else '无'}")
        if free_list:
            print("\n🎯 建议优先抢: " + '、'.join(
                [r for r in free_list if '大' in r] + [r for r in free_list if '大' not in r]))
    else:
        # 矩阵模式：时间段 x 会议室
        print()
        header = f"{'时间段':<14}"
        for room in rooms:
            header += f"  {room}"
        print(header)
        print("-" * len(header))

        for slot in slots:
            row = f"{str(slot[0])}-{str(slot[1]):<7}"
            for room, email in rooms.items():
                status, _ = query_freebusy(outlook, email, target_date, slot[0], slot[1])
                if status == 'free':
                    row += "  ✅"
                elif status == 'tentative':
                    row += "  🟡"
                else:
                    row += "  ❌"
            print(row)

        print("-" * len(header))
        print("✅=空闲  🟡=暂定  ❌=占用")
        print("💡 找一行 ✅ 最多的时段，就是最优选择！")

    print()
    print("=" * 70)
    print("💡 提示: 抢之前先跑这个，选✅多的时段，避免和同事冲突")
    print("   支持备选: --type large 只看大会议室")


if __name__ == '__main__':
    main()
