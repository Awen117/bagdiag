# -*- coding: utf-8 -*-
"""停障场景分析：减速起点 / 停车距离 / 峰值减速度 / 与目标距离 / AEB·MRM。

适用场景：本车道静止车、远距离静止车、低矮障碍、弯道内静止障碍、车道边缘障碍。
"""
import math

from .. import ego as ego_mod
from ..io import iter_msgs

CTRL_CMD = "/control/command/control_cmd"
EMERGENCY = "/control/command/emergency_cmd"
MRM = "/system/fail_safe/mrm_state"
OBJECTS = "/perception/object_recognition/tracking/objects"

MRM_NAMES = {1: "NORMAL", 2: "MRM_OPERATING", 3: "MRM_SUCCEEDED", 4: "MRM_FAILED"}


def _obj_pos(k):
    for a in ("initial_pose_with_covariance", "pose_with_covariance"):
        v = getattr(k, a, None)
        if v is not None and getattr(v, "pose", None) is not None:
            return v.pose.position
    return None


def analyze(reader, max_obj_dist=60.0):
    ego = ego_mod.series(reader)
    if not ego:
        return {"error": "no ego data"}

    speed = [(r[0], r[4]) for r in ego]
    accel, emergency, mrm = [], set(), set()
    for _, t, m in iter_msgs(reader, CTRL_CMD):
        try:
            accel.append((t, float(m.longitudinal.acceleration)))
        except Exception:
            pass
    for _, _, m in iter_msgs(reader, EMERGENCY):
        emergency.add(bool(getattr(m, "emergency", False)))
    for _, _, m in iter_msgs(reader, MRM):
        mrm.add(int(getattr(getattr(m, "state", None), "value", 1)))

    accel.sort()
    fwd = [(t, v) for t, v in speed if v > 0.5]
    res = {
        "has_forward_motion": bool(fwd),
        "mrm": [MRM_NAMES.get(s, s) for s in sorted(mrm)] or ["NORMAL"],
        "aeb_engaged": True in emergency,
    }
    if not fwd:
        res["note"] = "全程速度 <0.5 km/h，这段没有测试动作"
        return res

    vmax = max(v for _, v in fwd)
    t_vmax = next(t for t, v in fwd if v >= vmax - 0.5)
    tail = [(t, v) for t, v in speed if t >= t_vmax]
    t_dec = next((t for t, v in tail if v < vmax - 2.0), None)
    t_stop = next((t for t, v in tail if v < 0.3), None)

    res.update({
        "vmax_kmh": round(vmax, 1),
        "t_vmax_ns": t_vmax,
        "t_dec_ns": t_dec,
        "t_stop_ns": t_stop,
        "stopped": t_stop is not None,
    })
    if t_stop:
        res["decel_distance_m"] = round(ego_mod.travelled(ego, t_vmax, t_stop), 1)
        res["decel_duration_s"] = round((t_stop - t_vmax) / 1e9, 2)
        aa = [a for t, a in accel if t_vmax <= t <= t_stop]
        if aa:
            res["decel_peak_mps2"] = round(min(aa), 2)
            res["decel_avg_mps2"] = round(sum(aa) / len(aa), 2)
    else:
        res["note"] = "窗口内未停稳（末速 %.1f km/h）" % tail[-1][1]

    # 与最近跟踪目标的距离
    ref_t = t_stop or speed[-1][0]
    e = ego_mod.at(ego, ref_t)
    near = None
    for _, t, m in iter_msgs(reader, OBJECTS):
        if abs(t - ref_t) > 3e8:
            continue
        for o in (m.objects or []):
            q = _obj_pos(o.kinematics)
            if q is None:
                continue
            d = math.hypot(q.x - e[1], q.y - e[2])
            if d <= max_obj_dist:
                near = d if near is None else min(near, d)
    if near is not None:
        res["nearest_obj_m"] = round(near, 1)

    # 判定（阈值可改）
    ok = (res.get("stopped") and
          res.get("nearest_obj_m", 99) >= MIN_STOP_GAP_M and
          res.get("decel_peak_mps2", 0) >= -MAX_DECEL_MPS2 and
          not res["aeb_engaged"] and res["mrm"] == ["NORMAL"])
    res["verdict"] = "PASS" if ok else "CHECK"
    return res
