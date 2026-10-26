# -*- coding: utf-8 -*-
"""分片连续性检查（检测录制中断）。

为什么需要它：
  分片号是连续的，但时间戳可能断层 —— 中断期间的分片直接不存在，
  片号照样连号（101 → 102），肉眼完全看不出。
  实测一段录制中途断了 155 秒，那段时间的测试场景完全没有数据。

用法：给一个目录（含 <session>_<序号>.mcap）或一个 .info 文件。
一个 .info 里可能含多个会话，会按会话分别统计。
"""
import datetime as dt
import glob
import json
import os
import re

_SEG = re.compile(r"_(\d{14})_(\d+)\.mcap$")
_FMT = "%Y%m%d%H%M%S"


def _from_info(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _load(path):
    """返回 [(session, idx, start, end)]。"""
    segs = []
    if os.path.isfile(path) and path.endswith(".info"):
        for r in _from_info(path):
            b = os.path.basename(r.get("bag_path", ""))
            m = _SEG.search(b)
            if not m:
                continue
            segs.append((m.group(1), int(m.group(2)),
                         r.get("start_time_cst", ""), r.get("end_time_cst", "")))
    else:
        for f in sorted(glob.glob(os.path.join(path, "*.mcap"))):
            m = _SEG.search(os.path.basename(f))
            if m:
                segs.append((m.group(1), int(m.group(2)), "", ""))
    return segs


def _analyze_one(segs, expect_s, tolerance_s):
    segs = sorted(segs, key=lambda r: r[1])
    gaps, short = [], []
    if segs and segs[0][2]:
        for i in range(1, len(segs)):
            a, b = segs[i - 1], segs[i]
            try:
                ta = dt.datetime.strptime(a[3], _FMT)
                tb = dt.datetime.strptime(b[2], _FMT)
            except Exception:
                continue
            d = (tb - ta).total_seconds()
            if d > tolerance_s:
                gaps.append({"after_seg": a[1], "before_seg": b[1],
                             "gap_s": round(d, 1),
                             "between": "%s → %s" % (a[3][8:], b[2][8:])})
        for s in segs:
            try:
                dur = (dt.datetime.strptime(s[3], _FMT) -
                       dt.datetime.strptime(s[2], _FMT)).total_seconds()
            except Exception:
                continue
            if dur < expect_s - tolerance_s:
                short.append({"seg": s[1], "duration_s": round(dur, 1)})

    idx_gaps = []
    for i in range(1, len(segs)):
        if segs[i][1] - segs[i - 1][1] > 1:
            idx_gaps.append({"from": segs[i - 1][1], "to": segs[i][1]})

    return {
        "segments": len(segs),
        "first_seg": segs[0][1] if segs else None,
        "last_seg": segs[-1][1] if segs else None,
        "time_gaps": gaps,
        "short_segments": short,
        "index_gaps": idx_gaps,
        "ok": not gaps and not idx_gaps,
    }


def analyze(path, expect_s=15.0, tolerance_s=2.0):
    segs = _load(path)
    if not segs:
        return {"error": "没有找到分片 mcap / .info", "path": path}

    groups = {}
    for s in segs:
        groups.setdefault(s[0], []).append(s)

    if len(groups) == 1:
        res = _analyze_one(list(groups.values())[0], expect_s, tolerance_s)
        res["session"] = list(groups)[0]
    else:
        res = {"multi_session": True,
               "sessions": {k: _analyze_one(v, expect_s, tolerance_s)
                            for k, v in sorted(groups.items())}}
        res["ok"] = all(x["ok"] for x in res["sessions"].values())

    res["note"] = ("片号连续不代表时间连续；time_gaps 非空说明该时段没有录制，"
                   "对应时间点无法分析")
    return res
