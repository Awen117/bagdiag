#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量体检.py —— 把一个文件夹里所有 bag 都跑一遍 diag health，列成表

用法：
    python3 批量体检.py ~/Desktop/bags/20261027
    python3 批量体检.py ~/Desktop/bags                  # 全部（几百片，约 2-3 分钟）

⚠️ 口径说明（2026-10-30 实测校正，务必记住）：
    category_health 里的 health_score 是【话题出现率】= topics_present 的比例，
    例如 mrm 83.3 = "6 个话题出现了 5 个"，**不代表模块有故障**。
    MRM / AEB 没被触发时本来就不发某些话题 → 分数低是常态，不能当异常排序。

    真正有意义的异常只有两个字段：
      · missing_topics      —— 整片 bag 里根本不存在的话题
      · frequency_anomalies —— 话题实际频率偏离期望（真·异常）

    本脚本按【频率异常数 + 缺失话题数】排序，最可疑的排最前面。
"""

import os
import sys
import json
import subprocess

本目录 = os.path.dirname(os.path.abspath(__file__))
DIAG = os.path.join(本目录, 'diag')


def 找bag(目录):
    """递归找出目录下所有 .mcap，返回路径列表"""
    结果 = []
    for 根, _, 文件们 in os.walk(目录):
        for 名 in 文件们:
            if 名.endswith('.mcap'):
                结果.append(os.path.join(根, 名))
    return sorted(结果)


def 体检一片(路径):
    """跑 diag health，返回一个字典；失败返回 None"""
    try:
        输出 = subprocess.run(
            [DIAG, 'health', 路径],
            capture_output=True, text=True, timeout=300,
        )
        if 输出.returncode != 0:
            return None
        数据 = json.loads(输出.stdout)
    except Exception:
        return None

    异常 = 数据.get('anomalies_summary', {})
    缺失 = 异常.get('missing_topics', [])
    频率 = 异常.get('frequency_anomalies', [])

    return {
        '时长': 数据['basic_info']['time_range']['duration_seconds'],
        '消息数': 数据['basic_info']['total_messages'],
        '覆盖': 数据['health_summary']['topic_coverage_score'],
        '缺失话题': 缺失,
        '频率异常': 频率,
        '异常数': len(缺失) + len(频率),
    }


def main():
    目录 = sys.argv[1] if len(sys.argv) > 1 else '.'
    bags = 找bag(目录)
    print('找到 %d 片，开始跑...\n' % len(bags))

    结果 = []
    for i, 路径 in enumerate(bags, 1):
        名 = os.path.basename(路径)
        print('[%d/%d] %s' % (i, len(bags), 名), end=' ... ', flush=True)
        r = 体检一片(路径)
        if r is None:
            print('读取失败')
            continue
        print('异常 %d 个（缺失 %d / 频率 %d）' % (
            r['异常数'], len(r['缺失话题']), len(r['频率异常'])))
        结果.append((名, 路径, r))

    if not 结果:
        print('\n没有成功读取的 bag')
        return

    # 按异常数从多到少排序：最可疑的排最前面
    结果.sort(key=lambda x: x[2]['异常数'], reverse=True)

    print('\n' + '=' * 96)
    print('%-38s %6s %6s %6s  %s' % ('分片', '异常', '缺失', '频率', '缺失话题'))
    print('-' * 96)
    for 名, 路径, r in 结果:
        缺 = ','.join(t.split('/')[-1] for t in r['缺失话题']) or '-'
        print('%-38s %6d %6d %6d  %s' % (
            名[:38], r['异常数'], len(r['缺失话题']), len(r['频率异常']), 缺[:44]))

    print('=' * 96)

    # 统计：哪些话题最常缺失
    from collections import Counter
    缺统计 = Counter()
    频统计 = Counter()
    for _, _, r in 结果:
        缺统计.update(r['缺失话题'])
        频统计.update(f['topic'] for f in r['频率异常'])

    print('\n最常缺失的话题（%d 片中出现次数）：' % len(结果))
    for 话, 次 in 缺统计.most_common(10):
        print('  %-50s %3d 片' % (话, 次))

    print('\n最常频率异常的话题：')
    for 话, 次 in 频统计.most_common(10):
        print('  %-50s %3d 片' % (话, 次))

    # 落盘成 JSON —— 后续分析请读这个文件，不要回头解析上面那张【被截断】的表
    落盘 = os.path.join(os.path.dirname(本目录), '批量体检结果.json')
    with open(落盘, 'w', encoding='utf-8') as f:
        json.dump(
            [{'片': 名, '路径': 路径, **r} for 名, 路径, r in 结果],
            f, ensure_ascii=False, indent=1,
        )
    print('\n完整结果已存：%s' % 落盘)


if __name__ == '__main__':
    main()
