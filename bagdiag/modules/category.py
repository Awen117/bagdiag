# -*- coding: utf-8 -*-
"""检测层 ↔ 跟踪层 类别一致性配对。

为什么需要它：
  "检测有目标、跟踪也有目标，但类别对不上" —— 这类问题既不是漏检，也不是
  类别混淆，用普通统计看不出来。必须逐帧把检测框换算到 map 坐标，再和跟踪框
  配对，才能确认"是不是同一个目标被标成了别的类别"。

口径（很重要）：
  · /perception/object_recognition/detection/objects      是 base_link 坐标
  · /perception/object_recognition/detection/bevfusion/objects  也是 base_link
  · /perception/object_recognition/tracking/objects       是 map 坐标
  → 必须先按 ego 位姿把检测换算到 map，否则会得到一堆假的"不匹配"
"""
import math

from .. import ego as ego_mod
from ..io import iter_msgs

LABELS = {
    0: "UNKNOWN", 1: "CAR", 2: "TRUCK", 3: "BUS", 4: "TRAILER",
    5: "MOTORCYCLE", 6: "BICYCLE", 7: "PEDESTRIAN",
    8: "CONSTRUCTION_VEHICLE", 9: "BARRIER", 10: "TRAFFIC_CONE",
}

DET = "/perception/object_recognition/detection/objects"
BEV = "/perception/object_recognition/detection/bevfusion/objects"
TRK = "/perception/object_recognition/tracking/objects"


def _label(obj):
    cls = getattr(obj, "classification", None) or []
    if not cls:
        return "UNKNOWN", 0.0
    c = cls[0]
    v = getattr(c.label, "value", c.label)
    return LABELS.get(v, str(v)), float(getattr(c, "probability", 0.0))


def _pos(twist_obj):
    for attr in ("initial_pose_with_covariance", "pose_with_covariance"):
        v = getattr(twist_obj, attr, None)
        if v is not None and getattr(v, "pose", None) is not None:
            return v.pose.position
    return None


def _collect(reader, topic):
    out = []
    for _, t, m in iter_msgs(reader, topic):
        for o in (getattr(m, "objects", None) or []):
            p = _pos(o.kinematics)
            if p is None:
                continue
            lab, prob = _label(o)
            d = o.shape.dimensions
            out.append((t, p.x, p.y, lab, prob, float(d.x), float(d.y)))
    out.sort(key=lambda r: r[0])
    return out


def analyze(reader, window_s=0.06, radius_m=2.0):
    """把检测目标换算到 map 后与跟踪目标就近配对，统计类别是否一致。"""
    ego = ego_mod.series(reader)
    det = _collect(reader, DET)
    trk = _collect(reader, TRK)

    # 跟踪目标按时间分桶，避免 O(n*m) 全表扫描
    buckets = {}
    for row in trk:
        buckets.setdefault(int(row[0] // 10**8), []).append(row)

    pairs = {}          # (检测类别, 跟踪类别) -> 次数
    unmatched = 0       # 附近完全没有跟踪目标
    total = 0
    worst = []          # 记录几个典型配对样本

    for (t, x, y, lab, prob, w, ln) in det:
        e = ego_mod.at(ego, t)
        if e is None:
            continue
        c, s = math.cos(e[3]), math.sin(e[3])
        mx, my = e[1] + x * c - y * s, e[2] + x * s + y * c

        best = None
        key = int(t // 10**8)
        for k in (key - 1, key, key + 1):
            for row in buckets.get(k, ()):
                if abs(row[0] - t) > window_s * 10**9:
                    continue
                d = math.hypot(row[1] - mx, row[2] - my)
                if d <= radius_m and (best is None or d < best[0]):
                    best = (d, row)
        total += 1
        if best is None:
            unmatched += 1
            continue
        dist, row = best
        key2 = (lab, row[3])
        pairs[key2] = pairs.get(key2, 0) + 1
        if lab != row[3] and len(worst) < 12:
            worst.append({
                "t_ns": t, "dist_m": round(dist, 2),
                "det": lab, "track": row[3],
                "det_size": "%dx%d" % (round(w), round(ln)),
                "trk_size": "%dx%d" % (round(row[5]), round(row[6])),
                "prob": round(prob, 2),
            })

    mismatch = sum(v for (a, b), v in pairs.items() if a != b)
    matched = sum(pairs.values())
    report = {
        "det_frames": total,
        "matched": matched,
        "unmatched_in_radius": unmatched,
        "mismatch": mismatch,
        "mismatch_ratio": round(mismatch / matched, 3) if matched else 0.0,
        "pair_matrix": [
            {"det": a, "track": b, "count": v}
            for (a, b), v in sorted(pairs.items(), key=lambda kv: -kv[1])
        ],
        "mismatch_samples": worst,
        "note": ("unmatched 很大且检测总数正常 → 可能是跟踪丢失；"
                 "matched 但 mismatch 大 → 同一目标被标成别的类别，"
                 "属类别问题，不是丢失"),
    }
    return report
