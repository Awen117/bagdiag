#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
话题体检.py —— 用 bag 文件判断"哪些话题没数据了"

【作用】等于把车机上的 ros2 topic hz 搬到桌面上做：
        输入一个 bag 文件，输出每个话题的条数、首末时间、最大间隔
        条数=0 或间隔很大 → 这个话题"断了"

【用法】
    python3 话题体检.py <bag文件路径> [只看某个关键词]
    例：python3 话题体检.py ~/Desktop/bags/20261014/特定道路_153614/xxx.mcap
    例：python3 话题体检.py xxx.mcap perception        # 只看含 perception 的话题

【怎么读结果】
    条数 = 这段时间里这个topic发了几条消息（0 = 一条都没有 = 完全断了）
    最大间隔 = 相邻两条之间最长隔了多久（超过 1 秒就要注意）
"""

import sys
import datetime
from mcap.reader import make_reader          # 读 mcap 格式 bag 的库

CST = datetime.timezone(datetime.timedelta(hours=8))   # 中国时区(+8)


def 时间(纳秒):
    """把纳秒时间戳变成 时:分:秒.毫秒 这样的可读格式"""
    return datetime.datetime.fromtimestamp(纳秒 / 1e9, CST).strftime('%H:%M:%S.%f')[:-3]


def 体检(bag路径, 关键词=None):
    print('=' * 78)
    print('  话题体检：%s' % bag路径.split('/')[-1])
    print('=' * 78)

    with open(bag路径, 'rb') as 文件:
        读取器 = make_reader(文件)              # 打开 bag
        摘要 = 读取器.get_summary()             # 摘要里有话题清单和条数

        # 第1步：从摘要里拿到"每个话题有多少条消息"
        条数表 = {}
        for 通道 in 摘要.channels.values():
            条数表[通道.topic] = 摘要.statistics.channel_message_counts.get(通道.id, 0)

        # 第2步：遍历消息，记录每个话题的第一条/最后一条时间、最大间隔
        首条 = {}
        末条 = {}
        上一条 = {}
        最大间隔 = {}

        for 结构, 通道, 消息 in 读取器.iter_messages():     # 一条条读（不解码，很快）
            话题 = 通道.topic
            时刻 = 消息.log_time                            # 这条消息的时间戳（纳秒）

            if 话题 not in 首条:
                首条[话题] = 时刻
            if 话题 in 上一条:
                间隔 = (时刻 - 上一条[话题]) / 1e9          # 换算成秒
                if 间隔 > 最大间隔.get(话题, 0):
                    最大间隔[话题] = 间隔
            上一条[话题] = 时刻
            末条[话题] = 时刻

        # 第3步：打印表格
        话题列表 = sorted(条数表.keys())
        if 关键词:
            话题列表 = [t for t in 话题列表 if 关键词 in t]

        总条数 = sum(条数表.values())
        时长 = (摘要.statistics.message_end_time - 摘要.statistics.message_start_time) / 1e9
        print('  话题数: %d 个   时长: %.2f 秒   消息总数: %d 条' % (len(摘要.channels), 时长, 总条数))
        print()
        print('  %-62s %6s %14s %8s' % ('话题', '条数', '首条时间', '最大间隔'))
        print('  ' + '-' * 74)

        断了 = []          # 收集"可疑"的话题
        for 话题 in 话题列表:
            条数 = 条数表[话题]
            首 = 时间(首条[话题]) if 话题 in 首条 else '-'
            间隔 = 最大间隔.get(话题, 0)
            标记 = ''
            if 条数 == 0:
                标记 = '  ← 完全没有数据'
                断了.append(话题)
            elif 间隔 > 1.0:
                标记 = '  ← 中断过 %.1f 秒' % 间隔
                断了.append(话题)
            # 有筛选关键词时不截断名字（结果少），这样可以直接用 grep 搜完整话题名
            if 关键词:
                显示名 = 话题
            else:
                显示名 = 话题 if len(话题) <= 62 else '...' + 话题[-59:]
            print('  %-62s %6d %14s %7.2fs%s' % (显示名, 条数, 首, 间隔, 标记))

        # 第4步：总结（先报总数，方便一眼看到"一共几个话题"）
        print()
        print('  ── 本次共列出 %d 个话题：完全无数据 %d 个、有中断(>1秒) %d 个' % (
            len(话题列表),
            sum(1 for t in 话题列表 if 条数表[t] == 0),
            sum(1 for t in 话题列表 if 条数表[t] > 0 and 最大间隔.get(t, 0) > 1.0)))
        print()
        if 断了:
            print('  ⚠️ 有 %d 个话题可疑（没数据 或 中断超过 1 秒）：' % len(断了))
            for 话题 in 断了[:15]:
                print('       %s' % 话题)
        else:
            print('  ✅ 所有话题都有数据，且没有超过 1 秒的中断')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    bag文件 = sys.argv[1]
    关键词 = sys.argv[2] if len(sys.argv) > 2 else None
    体检(bag文件, 关键词)
