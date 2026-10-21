# -*- coding: utf-8 -*-
"""轨迹健康度：点数/长度塌缩、发布间隔、output guard hold。"""
from .. import path as path_mod
from ..io import iter_msgs

GUARD_KEY = "Output guard"


def analyze(reader, min_points=100):
    traj = path_mod.series(reader, path_mod.TRAJECTORY)
    if not traj:
        return {"error": "no trajectory"}
    ns = [r[1] for r in traj]
    ls = [r[2] for r in traj]
    gaps = [(traj[i][0] - traj[i - 1][0]) / 1e9 for i in range(1, len(traj))]
    short = [r for r in traj if r[1] < min_points]
    res = {
        "frames": len(traj),
        "points_min": min(ns), "points_max": max(ns),
        "length_min_m": round(min(ls), 2), "length_max_m": round(max(ls), 2),
        "max_gap_s": round(max(gaps), 3) if gaps else 0,
        "short_frames": len(short),
        "short_ratio_pct": round(100.0 * len(short) / len(traj), 1),
        "min_points_required": min_points,
    }
    # 用中位数判定，避免"静止那几帧"把整段误判为塌缩
    med = sorted(ls)[len(ls) // 2]
    res["length_median_m"] = round(med, 2)
    if short:
        res["first_short_ns"] = short[0][0]
    if med < 2.0:
        res["verdict"] = "COLLAPSED"
    elif med < 10.0:
        res["verdict"] = "SHORT"
    else:
        res["verdict"] = "OK"
    return res


def guard_holds(reader):
    """从 /rosout 提取 output guard 的 hold 与恢复事件。"""
    holds = []
    for _, t, m in iter_msgs(reader, "/rosout"):
        msg = getattr(m, "msg", "") or ""
        if GUARD_KEY not in msg:
            continue
        if "holding" in msg.lower():
            jump = None
            if "near_jump=" in msg:
                try:
                    jump = float(msg.split("near_jump=")[1].split(")")[0])
                except Exception:
                    pass
            holds.append({"t_ns": t, "event": "hold", "near_jump": jump, "raw": msg})
        elif "recovered" in msg.lower():
            holds.append({"t_ns": t, "event": "recovered", "near_jump": None, "raw": msg})
    holds.sort(key=lambda h: h["t_ns"])
    # 配对计算持续时长
    out, start = [], None
    for h in holds:
        if h["event"] == "hold":
            start = h
        elif start is not None:
            out.append({"start_ns": start["t_ns"], "end_ns": h["t_ns"],
                        "duration_s": round((h["t_ns"] - start["t_ns"]) / 1e9, 2),
                        "near_jump": start["near_jump"]})
            start = None
    return out
