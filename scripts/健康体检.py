#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康体检.py —— 读 diag health 的 JSON，把分数捞出来（完整可运行版）

【第 3 课：JSON 就是字典 + 列表】

用法：
    # 1) 先把 diag 输出存成文件
    cd ~/Desktop/workspace/tools
    ./diag health "<某个 bag>.mcap" > /tmp/h.json

    # 2) 跑本脚本
    python3 健康体检.py /tmp/h.json
"""

import sys
阈值 = 95
import json


def 读健康分(路径):

    # ---------- 第 1 步：把 JSON 文件读成字典 ----------
    with open(路径, encoding='utf-8') as f:
        数据 = json.load(f)
    # 到这里，「数据」就是一个大字典，和你第 2 天写的 计数 = {'WARN': 0} 是同一种东西

    # ---------- 第 2 步：一层层用方括号取数 ----------
    信息 = 数据['basic_info']
    print('时长: %.1f 秒   消息总数: %d 条' % (
        信息['time_range']['duration_seconds'],
        信息['total_messages'],
    ))

    总分 = 数据['health_summary']['overall_health_score']
    print('overall 健康分: %.1f' % 总分)

    模块表 = 数据['category_health']
    # 模块表长这样：{'perception': {'health_score': 100.0}, 'mrm': {'health_score': 83.3}, ...}

    # ---------- 第 3 步：遍历 + 挑出差的 ----------
    差模块 = []
    最低模块 = None
    最低分 = 999

    for 模块, 详情 in 模块表.items():
        分 = 详情['health_score']
        print('  %-16s %5.1f' % (模块, 分))

        if 分 < 最低分:
            最低分 = 分
            最低模块 = 模块

        if 分 < 阈值:                 # ← 想换阈值就改这个 90
            差模块.append(模块)

    print('最低分模块: %s %.1f' % (最低模块, 最低分))
    print('低于 %.0f 分的模块: %s' % (阈值, 差模块))


if __name__ == '__main__':
    读健康分(sys.argv[1])
