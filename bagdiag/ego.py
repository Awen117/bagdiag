# -*- coding: utf-8 -*-
"""自车状态：位置、航向、车速（km/h）。"""
import math

from .io import iter_msgs

TOPIC = "/localization/kinematic_state"


def _yaw(o):
    return math.atan2(2 * (o.w * o.z + o.x * o.y),
                      1 - 2 * (o.y * o.y + o.z * o.z))


def series(reader):
    """[(t_ns, x, y, yaw, kmh)] 按时间升序。"""
    out = []
    for _, t, m in iter_msgs(reader, TOPIC):
        q = m.pose.pose.position
        out.append((t, q.x, q.y, _yaw(m.pose.pose.orientation),
                    float(m.twist.twist.linear.x) * 3.6))
    out.sort(key=lambda r: r[0])
    return out


def at(s, t):
    """最近时刻的 ego 样本。"""
    if not s:
        return None
    return min(s, key=lambda r: abs(r[0] - t))


def body_frame(ego, x, y):
    """把地图坐标转成车体坐标 (lon, lat)。lat>0 = 车左。"""
    dx, dy = x - ego[1], y - ego[2]
    c, s = math.cos(ego[3]), math.sin(ego[3])
    return dx * c + dy * s, -dx * s + dy * c


def travelled(ego, t0, t1):
    """t0→t1 行驶距离（米）。"""
    seg = [r for r in ego if t0 <= r[0] <= t1]
    return sum(math.hypot(seg[i + 1][1] - seg[i][1],
                          seg[i + 1][2] - seg[i][2])
               for i in range(len(seg) - 1))
