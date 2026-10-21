# -*- coding: utf-8 -*-
"""路径 / 轨迹几何工具。"""
import math

from .io import iter_msgs

PATH = "/planning/scenario_planning/lane_driving/behavior_planning/path"
TRAJECTORY = "/planning/scenario_planning/trajectory"
LC_LEFT = "/planning/path_candidate/lane_change_left"
LC_RIGHT = "/planning/path_candidate/lane_change_right"


def points(msg):
    """取 points[].pose.position → [(x, y)]。"""
    return [(p.pose.position.x, p.pose.position.y)
            for p in (getattr(msg, "points", None) or [])]


def length(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0],
                          pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def series(reader, topic):
    """[(t_ns, n_points, length_m)]"""
    out = []
    for _, t, m in iter_msgs(reader, topic):
        p = points(m)
        if len(p) >= 2:
            out.append((t, len(p), length(p)))
    out.sort(key=lambda r: r[0])
    return out


def lateral_offsets(reader, ego, topic=PATH, lookahead_idx=9):
    """每帧路径第 lookahead 点相对车体中心的横向偏移（米）。"""
    from .ego import at, body_frame
    out = []
    for _, t, m in iter_msgs(reader, topic):
        p = points(m)
        if len(p) < 5:
            continue
        e = at(ego, t)
        if e is None:
            continue
        px, py = p[min(lookahead_idx, len(p) - 1)]
        _, lat = body_frame(e, px, py)
        out.append((t, lat))
    out.sort(key=lambda r: r[0])
    return out


def lane_change_intents(reader, gap_s=0.2):
    """变道意图时段 [(t_start, t_end)]（左右 path_candidate 非空且长度>1m）。"""
    ts = []
    for topic in (LC_LEFT, LC_RIGHT):
        for _, t, m in iter_msgs(reader, topic):
            p = points(m)
            if len(p) > 2 and length(p) > 1.0:
                ts.append(t)
    ts.sort()
    if not ts:
        return []
    runs, a, b = [], ts[0], ts[0]
    for t in ts[1:]:
        if (t - b) / 1e9 <= gap_s:
            b = t
        else:
            runs.append((a, b))
            a = b = t
    runs.append((a, b))
    return runs
