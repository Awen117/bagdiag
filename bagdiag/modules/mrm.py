# -*- coding: utf-8 -*-
"""MRM / 急停事件时间线。"""
from ..io import iter_msgs

MRM = "/system/fail_safe/mrm_state"
EMERGENCY = "/control/command/emergency_cmd"

NAMES = {0: "UNKNOWN", 1: "NORMAL", 2: "MRM_OPERATING", 3: "MRM_SUCCEEDED", 4: "MRM_FAILED"}

# 短于这个时长的 MRM 视为状态机毛刺，不计入触发次数
BLIP_S = 0.5


def analyze(reader):
    states, emerg = [], []
    for _, t, m in iter_msgs(reader, MRM):
        v = getattr(m.state, "value", m.state)
        states.append((t, int(v)))
    for _, t, m in iter_msgs(reader, EMERGENCY):
        emerg.append((t, bool(getattr(m, "emergency", False))))
    states.sort()
    emerg.sort()

    transitions = []
    prev = None
    for t, v in states:
        if v != prev:
            transitions.append({"t_ns": t, "from": NAMES.get(prev, prev),
                                "to": NAMES.get(v, v)})
            prev = v
    em_events, prev = [], None
    for t, v in emerg:
        if v != prev:
            em_events.append({"t_ns": t, "value": v})
            prev = v
    # 把 MRM_OPERATING 的进入/退出配成事件区间，剔除瞬时毛刺
    episodes, opened = [], None
    for tr in transitions:
        if tr["to"] == "MRM_OPERATING":
            opened = tr["t_ns"]
        elif tr["from"] == "MRM_OPERATING" and opened is not None:
            episodes.append((opened, tr["t_ns"]))
            opened = None
    if opened is not None and states:
        episodes.append((opened, states[-1][0]))

    real = [e for e in episodes if (e[1] - e[0]) / 1e9 >= BLIP_S]
    blips = [e for e in episodes if (e[1] - e[0]) / 1e9 < BLIP_S]

    return {
        "mrm_transitions": transitions,
        "emergency_events": em_events,
        "mrm_episodes": [{"start_ns": a, "end_ns": b,
                          "duration_s": round((b - a) / 1e9, 2)} for a, b in episodes],
        "mrm_trigger_count": len(real),
        "mrm_blip_count": len(blips),
        "engaged": bool(real),
    }
