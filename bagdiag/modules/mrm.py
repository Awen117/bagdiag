# -*- coding: utf-8 -*-
"""MRM / 急停事件时间线。"""
from ..io import iter_msgs

MRM = "/system/fail_safe/mrm_state"
EMERGENCY = "/control/command/emergency_cmd"

NAMES = {0: "UNKNOWN", 1: "NORMAL", 2: "MRM_OPERATING", 3: "MRM_SUCCEEDED", 4: "MRM_FAILED"}


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
    operating = sum(1 for x in transitions if x["to"] == "MRM_OPERATING")
    return {
        "mrm_transitions": transitions,
        "emergency_events": em_events,
        "mrm_trigger_count": operating,
        "engaged": operating > 0,
    }
