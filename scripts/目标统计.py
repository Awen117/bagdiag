#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标统计.py —— 看"感知看到了哪些东西"（第二层：内容对不对）

【作用】话题体检.py 只回答"有没有数据"；这个脚本回答"数据里有什么"：
        每一帧有多少个目标？分别是什么类别？出现得稳不稳？

【用法】
    python3 目标统计.py <bag文件> [话题名]
    默认看 /perception/object_recognition/objects（最终目标列表）
    例：python3 目标统计.py xxx.mcap
    例：python3 目标统计.py xxx.mcap /perception/object_recognition/detection/objects

【怎么读结果】
    帧数        = 有多少帧有目标数据
    平均目标数  = 每帧平均看到几个东西
    类别分布    = 各类别一共出现了多少"目标次"（一个目标在一帧里算1次）
    每帧目标数  = 时间线，看某个时刻突然变成 0（= 目标全丢了）
"""

import sys
import os
import datetime
from collections import Counter

# 把工作区根目录加进来，好 import 已有的 bag 读取库
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analyzers.bag import _open, _iter_decode      # 现成的读 bag 工具

CST = datetime.timezone(datetime.timedelta(hours=8))

# 类别编号 → 名字（这是 autoware 定死的对照表）
类别表 = {
    0: 'UNKNOWN(未知)', 1: 'CAR(轿车)', 2: 'TRUCK(卡车)', 3: 'BUS(公交)',
    4: 'TRAILER(挂车)', 5: 'MOTORCYCLE(摩托)', 6: 'BICYCLE(自行车)',
    7: 'PEDESTRIAN(行人)', 8: 'CONSTRUCTION_VEHICLE(工程车)',
    9: 'BARRIER(护栏)', 10: 'TRAFFIC_CONE(锥桶)', 11: 'ANIMAL(动物)',
    12: 'HAZARD(危险物)',
}


def 取时间(消息, 默认时间):
    """从消息头里取时间戳（纳秒），没有就用 bag 记录时间"""
    时间头 = getattr(getattr(消息, 'header', None), 'stamp', None)
    if 时间头 is None:
        return 默认时间
    return 时间头.sec * 10 ** 9 + 时间头.nanosec


def 时刻(纳秒):
    return datetime.datetime.fromtimestamp(纳秒 / 1e9, CST).strftime('%H:%M:%S.%f')[:-3]


def 统计(bag路径, 话题='/perception/object_recognition/objects'):
    print('=' * 74)
    print('  目标统计：%s' % bag路径.split('/')[-1])
    print('  话题：%s' % 话题)
    print('=' * 74)

    读取器, 解码器, 文件句柄 = _open(bag路径)

    帧数 = 0
    目标总数 = 0
    类别计数 = Counter()
    每帧数量 = []          # [(时间, 目标数), ...]
    空帧 = []              # 一个目标都没有的帧

    for 通道名, 记录时间, 消息 in _iter_decode(读取器, [话题]):
        目标列表 = getattr(消息, 'objects', None) or []
        时间 = 取时间(消息, 记录时间)

        帧数 += 1
        目标总数 += len(目标列表)
        每帧数量.append((时间, len(目标列表)))

        if len(目标列表) == 0:
            空帧.append(时间)

        for 目标 in 目标列表:
            分类列表 = getattr(目标, 'classification', None) or []
            if 分类列表:
                # 一个目标可能有多个候选类别，取概率最高的那个（列表第一个）
                标签 = 分类列表[0].label
                标签号 = getattr(标签, 'value', 标签)      # ROS 里枚举要取 .value
                类别计数[标签号] += 1

    文件句柄.close()

    if 帧数 == 0:
        print('  ❌ 这个话题在这份 bag 里一条消息都没有')
        return

    print('  帧数: %d 帧' % 帧数)
    print('  平均每帧目标数: %.1f 个' % (目标总数 / 帧数))
    print('  目标总出现次数: %d 次' % 目标总数)
    print()

    print('  类别分布（各类别共出现多少次）：')
    for 标签号, 次数 in 类别计数.most_common():
        名字 = 类别表.get(标签号, '未知类别%s' % 标签号)
        占比 = 100.0 * 次数 / 目标总数 if 目标总数 else 0
        print('     %-32s %6d 次  (%4.1f%%)' % (名字, 次数, 占比))
    print()

    # 找"目标数突然变成 0"的时刻（可能是目标全丢）
    最大值 = max(数量 for _, 数量 in 每帧数量)
    print('  每帧目标数范围: 0 ~ %d 个' % 最大值)
    if 空帧:
        print('  ⚠️ 有 %d 帧一个目标都没有（第一帧 %s）' % (len(空帧), 时刻(空帧[0])))
    else:
        print('  ✅ 每一帧都有目标')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    bag文件 = sys.argv[1]
    指定话题 = sys.argv[2] if len(sys.argv) > 2 else '/perception/object_recognition/objects'
    统计(bag文件, 指定话题)
