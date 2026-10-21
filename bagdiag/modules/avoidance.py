# -*- coding: utf-8 -*-
"""绕行意图：路径相对车体中心线的横向偏移。

<0.5m 视为直线（不绕）；>0.5m 视为有绕行意图。
"""
from .. import ego as ego_mod
from .. import path as path_mod


def analyze(reader, threshold_m=0.5):
    ego = ego_mod.series(reader)
    if not ego:
        return {"error": "no ego data"}
    offs = path_mod.lateral_offsets(reader, ego)
    if not offs:
        return {"error": "no path data"}
    mags = [abs(l) for _, l in offs]
    peak = max(mags)
    peak_t = offs[mags.index(peak)][0]
    return {
        "frames": len(offs),
        "max_abs_offset_m": round(peak, 2),
        "max_offset_t_ns": peak_t,
        "threshold_m": threshold_m,
        "intent": "AVOIDING" if peak > threshold_m else "STRAIGHT",
        "note": "偏移大于阈值说明规划在横向避让；否则为直线停障",
    }
