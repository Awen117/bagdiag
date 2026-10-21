# -*- coding: utf-8 -*-
"""日志检索：按关键字过滤 /rosout（也能直接读车机 1_stdout.log）。"""
import re

from ..io import iter_msgs

LEVELS = {10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR", 50: "FATAL"}


def grep_bag(reader, keywords, level_min=30, limit=200):
    kws = [k.lower() for k in keywords]
    out = []
    for _, t, m in iter_msgs(reader, "/rosout"):
        msg = getattr(m, "msg", "") or ""
        lv = int(getattr(m, "level", 0))
        if lv < level_min:
            continue
        low = msg.lower()
        if not any(k in low for k in kws):
            continue
        out.append({"t_ns": t, "level": LEVELS.get(lv, lv),
                    "node": getattr(m, "name", ""), "msg": msg})
        if len(out) >= limit:
            break
    return out


def grep_logfile(path, keywords, limit=200):
    """检索纯文本日志（车机 1_stdout.log），自动去掉 ANSI 颜色。"""
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    kws = [k.lower() for k in keywords]
    out = []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            s = ansi.sub("", line).rstrip()
            low = s.lower()
            if any(k in low for k in kws):
                out.append(s)
                if len(out) >= limit:
                    break
    return out


def counts_by_minute(entries):
    """按分钟统计条数（entries 需含 t_ns）。"""
    from collections import Counter
    import datetime as dt
    c = Counter()
    for e in entries:
        t = dt.datetime.fromtimestamp(e["t_ns"] / 1e9)
        c[t.strftime("%H:%M")] += 1
    return dict(sorted(c.items()))
