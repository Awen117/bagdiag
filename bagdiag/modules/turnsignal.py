# -*- coding: utf-8 -*-
"""转向灯 / 控制模式一致性检查。

为什么需要它：
  "全自动驾驶状态下，车打了转向灯往一边变道，但规划层没有变道意图、
   系统下发的转向指令还是关灯" —— 这类问题靠单看转向灯看不出来，
  必须把三样东西放一起比：
     ① 实际灯状态  /vehicle/status/turn_indicators_status
     ② 系统下发     /control/command/turn_indicators_cmd
     ③ 谁在控制     operation_mode / control_mode / autoware_state

枚举（autoware_vehicle_msgs）：
  TurnIndicatorsReport / TurnIndicatorsCommand: 1=DISABLE 2=ENABLE_LEFT 3=ENABLE_RIGHT
  （Command 里 0 = NO_COMMAND，不属标准枚举，但车端会发）
  OperationModeState: 1=STOP 2=AUTONOMOUS 3=LOCAL 4=REMOTE
  ControlModeReport : 1=AUTONOMOUS 2=AUTONOMOUS_STEER_ONLY 3=AUTONOMOUS_VELOCITY_ONLY 4=MANUAL
"""
from ..io import iter_msgs

STATUS = "/vehicle/status/turn_indicators_status"
CMD = "/control/command/turn_indicators_cmd"
EXT_CMD = "/external/selected/turn_indicators_cmd"
OP_MODE = "/api/operation_mode/state"
CTRL_MODE = "/vehicle/status/control_mode"
STATE = "/autoware/state"

TI = {0: "NO_COMMAND", 1: "DISABLE", 2: "ENABLE_LEFT", 3: "ENABLE_RIGHT"}
MODE = {0: "UNKNOWN", 1: "STOP", 2: "AUTONOMOUS", 3: "LOCAL", 4: "REMOTE"}
CTRL = {0: "NO_COMMAND", 1: "AUTONOMOUS", 2: "AUTONOMOUS_STEER_ONLY",
        3: "AUTONOMOUS_VELOCITY_ONLY", 4: "MANUAL", 5: "DISENGAGED", 6: "NOT_READY"}
AW = {0: "UNKNOWN", 1: "INITIALIZING", 2: "WAITING_FOR_ROUTE", 3: "PLANNING",
      4: "WAITING_FOR_ENGAGE", 5: "DRIVING", 6: "ARRIVED_GOAL", 7: "FINALIZING"}


def _transitions(reader, topic, field, names):
    seq = []
    for _, t, m in iter_msgs(reader, topic):
        v = getattr(m, field, None)
        if v is None:
            continue
        v = getattr(v, "value", v)
        seq.append((t, int(v)))
    seq.sort()
    out, prev = [], None
    for t, v in seq:
        if v != prev:
            out.append({"t_ns": t, "value": v, "name": names.get(v, str(v))})
            prev = v
    return seq, out


def analyze(reader):
    st, st_tr = _transitions(reader, STATUS, "report", TI)
    cm, cm_tr = _transitions(reader, CMD, "command", TI)
    _, op_tr = _transitions(reader, OP_MODE, "mode", MODE)
    _, ct_tr = _transitions(reader, CTRL_MODE, "mode", CTRL)
    _, aw_tr = _transitions(reader, STATE, "state", AW)

    # 灯亮但系统指令不是同一个方向 → 记一次不一致
    mismatches = []
    for t, v in st:
        if v not in (2, 3):
            continue
        near = [c for c in cm if c[0] <= t]
        cmd_v = near[-1][1] if near else None
        if cmd_v != v:
            if not mismatches or t - mismatches[-1]["t_ns"] > 3 * 10**8:
                mismatches.append({
                    "t_ns": t,
                    "status": TI.get(v, v),
                    "cmd": TI.get(cmd_v, cmd_v),
                })

    left = sum(1 for _, v in st if v == 2)
    right = sum(1 for _, v in st if v == 3)
    return {
        "status_transitions": st_tr,
        "cmd_transitions": cm_tr,
        "operation_mode": op_tr,
        "control_mode": ct_tr,
        "autoware_state": aw_tr,
        "left_on_frames": left,
        "right_on_frames": right,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:12],
        "note": ("mismatch 表示灯亮着但系统指令不是同一方向；"
                 "若此时 operation_mode=AUTONOMOUS 且规划无 lane_change 候选，"
                 "说明灯不是标准链路点亮的，需要研发从节点层排查"),
    }
