# -*- coding: utf-8 -*-
"""跟踪质量：跟踪丢失 / 类别混淆 / UUID 续存统计。

口径（重要）:
  跟踪丢失 = 检测层有目标，但跟踪层同位置 2m 内完全没有任何目标
  类别混淆 = 跟踪层有目标、位置对得上，但类别不同
不要用"位置+尺寸"双匹配，会把类别判错误算成漏检。
"""
import math
from collections import Counter, defaultdict

from .. import ego as ego_mod
from ..io import iter_msgs

DET_TOPICS = ["/perception/object_recognition/detection/objects",
              "/perception/object_recognition/detection/bevfusion/objects"]
TRK = "/perception/object_recognition/tracking/objects"

LABELS = {0: "UNKNOWN", 1: "CAR", 2: "TRUCK", 3: "BUS", 4: "TRAILER",
          5: "MOTORCYCLE", 6: "BICYCLE", 7: "PEDESTRIAN",
          8: "CONSTRUCTION_VEHICLE", 9: "BARRIER", 10: "CONE"}


def _label(o):
    cl = getattr(o, "classification", None) or []
    if not cl:
        return "UNKNOWN"
    lv = getattr(cl[0].label, "value", cl[0].label)
    return LABELS.get(int(lv), str(lv))


def _pos(k):
    for a in ("initial_pose_with_covariance", "pose_with_covariance"):
        v = getattr(k, a, None)
        if v is not None and getattr(v, "pose", None) is not None:
            return v.pose.position
    return None


def analyze(reader, det_topic=None, gate_m=2.0, window_m=40.0):
    det_topic = det_topic or DET_TOPICS[0]
    ego = ego_mod.series(reader)
    if not ego:
        return {"error": "no ego data"}

    trk = []
    for _, t, m in iter_msgs(reader, TRK):
        for o in (m.objects or []):
            q = _pos(o.kinematics)
            if q is not None:
                trk.append((t, q.x, q.y, _label(o)))
    trk.sort(key=lambda r: r[0])

    total, lost, conf = Counter(), Counter(), Counter()
    pairs = Counter()
    for _, t, m in iter_msgs(reader, det_topic):
        e = ego_mod.at(ego, t)
        if e is None:
            continue
        pool = [x for x in trk if abs(x[0] - t) < 2.5e8]
        for o in (m.objects or []):
            q = _pos(o.kinematics)
            if q is None:
                continue
            # 检测是 base_link 帧 → 转到 map
            mx = e[1] + q.x * math.cos(e[3]) - q.y * math.sin(e[3])
            my = e[2] + q.x * math.sin(e[3]) + q.y * math.cos(e[3])
            lon, lat = ego_mod.body_frame(e, mx, my)
            if not (0 < lon < window_m and abs(lat) < 10):
                continue
            lbl = _label(o)
            total[lbl] += 1
            same = [x for x in pool if x[3] == lbl and
                    math.hypot(x[1] - mx, x[2] - my) < gate_m]
            if same:
                continue
            other = [x for x in pool if math.hypot(x[1] - mx, x[2] - my) < gate_m]
            if other:
                conf[lbl] += 1
                pairs[(lbl, other[0][3])] += 1
            else:
                lost[lbl] += 1

    rows = []
    for lbl, n in total.most_common():
        rows.append({
            "class": lbl, "det_frames": n,
            "tracking_lost": lost[lbl],
            "lost_pct": round(100.0 * lost[lbl] / n, 1),
            "class_confused": conf[lbl],
            "confused_pct": round(100.0 * conf[lbl] / n, 1),
        })
    top_pairs = [{"from": a, "to": b, "count": c} for (a, b), c in pairs.most_common(5)]
    return {"det_topic": det_topic, "rows": rows, "top_confusions": top_pairs}


def uuid_continuity(reader, min_frames=20):
    """每条跟踪轨迹的帧数与时间连续性。"""
    agg = defaultdict(lambda: {"n": 0, "label": Counter(), "t0": None, "t1": None})
    for _, t, m in iter_msgs(reader, TRK):
        for o in (m.objects or []):
            uid = str(getattr(o, "object_id", b""))[-8:]
            b = agg[uid]
            b["n"] += 1
            b["label"][_label(o)] += 1
            b["t0"] = t if b["t0"] is None else min(b["t0"], t)
            b["t1"] = t if b["t1"] is None else max(b["t1"], t)
    out = []
    for uid, b in sorted(agg.items(), key=lambda x: -x[1]["n"]):
        if b["n"] < min_frames:
            continue
        out.append({"track_id": uid, "frames": b["n"],
                    "label": b["label"].most_common(1)[0][0],
                    "label_stable": len(b["label"]) == 1,
                    "t0_ns": b["t0"], "t1_ns": b["t1"],
                    "duration_s": round((b["t1"] - b["t0"]) / 1e9, 2)})
    return out
