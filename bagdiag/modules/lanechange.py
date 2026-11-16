# -*- coding: utf-8 -*-
"""变道 / 取消变道分析。

⚠️ 横移量必须用【地图绝对坐标】：
   ❌ 初始 yaw 投影 —— 弯道长距离会放大成假值
   ❌ 分段航向积分 —— 车自身转向会把横移吸收掉，算出 ≈0
   ✅ 地图绝对坐标垂直分量变化（先确认路段走向）
"""
import math

from .. import ego as ego_mod
from .. import path as path_mod

# 窗口内航向变化超过这个角度，说明车在转弯，横移量按轴向投影必然失真
YAW_TURN_DEG = 8.0


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

    # 用【车头平均航向】做投影，而不是地图 x/y 轴：
    #   车不在 x/y 轴向上行驶时（比如航向 45°），按轴取较小分量会算出几十米的假横移。
    yaw_sin = sum(math.sin(r[3]) for r in in_span)
    yaw_cos = sum(math.cos(r[3]) for r in in_span)
    heading = math.atan2(yaw_sin, yaw_cos)
    travel = dx * math.cos(heading) + dy * math.sin(heading)   # 沿车头方向
    lateral = -dx * math.sin(heading) + dy * math.cos(heading)  # 车左侧为正
    axis = "车头平均航向 %.0f°" % math.degrees(heading)

    warnings = []
    reliable = True

    # 航向变化检查：一次转弯会让"单一平均航向"的投影失真
    yaw_span = abs(b[3] - a[3])
    if yaw_span > math.pi:
        yaw_span = 2 * math.pi - yaw_span
    yaw_deg = math.degrees(yaw_span)
    turning = yaw_deg > YAW_TURN_DEG
    if turning:
        reliable = False
        warnings.append("窗口内航向变化 %.0f°，疑似转弯而非变道，横移量不可判定" % yaw_deg)

    # 横移不可能超过行进距离本身：明显超出说明坐标系选错了
    if dist > 5.0 and abs(lateral) > dist * 0.5:
        reliable = False
        warnings.append("横移 %.1fm 相对行进 %.1fm 过大，坐标系可能不适用" % (abs(lateral), dist))

    return {
        "t_ref_ns": t_ref,
        "lateral_reliable": reliable,
        "yaw_change_deg": round(yaw_deg, 1),
        "turning": turning,
        "warning": "；".join(warnings) if warnings else None,
        "span_s": round((b[0] - a[0]) / 1e9, 1),
        "travel_m": round(dist, 1),
        "travel_axis_m": round(abs(travel), 1),
        "lateral_delta_m": round(lateral, 2),
        "lateral_axis": axis,
        "lane_change_likely": reliable and abs(lateral) >= 1.5,
        "intent_windows": [{"start_ns": s, "end_ns": e,
                            "duration_s": round((e - s) / 1e9, 1)}
                           for s, e in intents],
        "note": "±1.5m 以上视为发生变道；lane ID 变化不等于变道",
    }
