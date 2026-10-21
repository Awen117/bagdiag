# -*- coding: utf-8 -*-
"""变道 / 取消变道分析。

⚠️ 横移量必须用【地图绝对坐标】：
   ❌ 初始 yaw 投影 —— 弯道长距离会放大成假值
   ❌ 分段航向积分 —— 车自身转向会把横移吸收掉，算出 ≈0
   ✅ 地图绝对坐标垂直分量变化（先确认路段走向）
"""
from .. import ego as ego_mod
from .. import path as path_mod


def analyze(reader, ref_t_ns=None, span_s=20.0):
    ego = ego_mod.series(reader)
    if not ego:
        return {"error": "no ego data"}
    intents = path_mod.lane_change_intents(reader)

    t_ref = ref_t_ns or (intents[0][0] if intents else ego[0][0])
    in_span = [r for r in ego if abs(r[0] - t_ref) <= span_s * 1e9]
    if len(in_span) < 2:
        return {"error": "时间窗内 ego 样本不足", "t_ref_ns": t_ref}

    a, b = in_span[0], in_span[-1]
    dx, dy = b[1] - a[1], b[2] - a[2]
    dist = (dx * dx + dy * dy) ** 0.5
    # 主行进轴与垂直轴位移
    if abs(dx) >= abs(dy):
        lateral, travel = dy, abs(dx)
        axis = "y (垂直 x 向行驶)"
    else:
        lateral, travel = dx, abs(dy)
        axis = "x (垂直 y 向行驶)"

    # 路段是否大致沿某一主轴：主轴/次轴比值不够大时，横移量会被弯道污染
    major, minor = max(abs(dx), abs(dy)), min(abs(dx), abs(dy))
    axis_ratio = major / minor if minor > 1e-6 else 999.0
    reliable = axis_ratio >= 2.5 or major < 5.0

    return {
        "t_ref_ns": t_ref,
        "axis_ratio": round(axis_ratio, 2),
        "lateral_reliable": reliable,
        "warning": None if reliable else
        "路段不沿主轴（主轴/次轴=%.1f），横移量可能被弯道污染，需人工确认" % axis_ratio,
        "span_s": round((b[0] - a[0]) / 1e9, 1),
        "travel_m": round(dist, 1),
        "travel_axis_m": round(travel, 1),
        "lateral_delta_m": round(lateral, 2),
        "lateral_axis": axis,
        "lane_change_likely": abs(lateral) >= 1.5,
        "intent_windows": [{"start_ns": s, "end_ns": e,
                            "duration_s": round((e - s) / 1e9, 1)}
                           for s, e in intents],
        "note": "±1.5m 以上视为发生变道；lane ID 变化不等于变道",
    }
