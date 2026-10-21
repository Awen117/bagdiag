# -*- coding: utf-8 -*-
"""bagdiag 命令行入口。"""
import argparse
import glob
import json
import os
import sys


def _fmt_ns(ns):
    import datetime as dt
    if not ns:
        return "-"
    return dt.datetime.fromtimestamp(ns / 1e9).strftime("%H:%M:%S.%f")[:-3]


def _bags(path):
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "*.mcap")) +
                      glob.glob(os.path.join(path, "*.mcap.zst")))
    return [path]


def _emit(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    return obj


def cmd_info(args):
    from . import io
    for p in _bags(args.path):
        d = io.info(p)
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s  %.2fs  %d 条消息  %d 话题  %d schema"
              % (d["path"], d["duration_s"], d["messages"], d["topics"], d["schema_count"]))
        print(" 时间 %s ~ %s" % (_fmt_ns(d["start_ns"]), _fmt_ns(d["end_ns"])))
        if d["zero_msg_topics"]:
            print(" 零消息话题: %s" % ", ".join(d["zero_msg_topics"][:8]))
        print(" Top 话题:")
        for t in d["topic_detail"][:12]:
            print("   %-62s %d" % (t["topic"], t["messages"]))


def cmd_stop(args):
    from . import io
    from .modules import stop
    for p in _bags(args.path):
        r = stop.analyze(io.open_bag(p))
        r["bag"] = os.path.basename(p)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s" % r.get("bag"))
        if r.get("note"):
            print(" 注意: %s" % r["note"])
        print(" 最高车速 %s km/h   停稳: %s"
              % (r.get("vmax_kmh", "-"), "是" if r.get("stopped") else "否"))
        print(" 减速 %s m / %s s   峰值 %s / 平均 %s m/s²"
              % (r.get("decel_distance_m", "-"), r.get("decel_duration_s", "-"),
                 r.get("decel_peak_mps2", "-"), r.get("decel_avg_mps2", "-")))
        print(" 停稳时最近目标 %s m   MRM %s   AEB %s"
              % (r.get("nearest_obj_m", "-"), ",".join(r.get("mrm", [])),
                 r.get("aeb_engaged")))
        print(" 判定: %s" % r.get("verdict", "-"))


def cmd_traj(args):
    from . import io
    from .modules import trajectory
    for p in _bags(args.path):
        r = trajectory.analyze(io.open_bag(p), min_points=args.min_points)
        r["guard_holds"] = trajectory.guard_holds(io.open_bag(p))
        r["bag"] = os.path.basename(p)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s" % r["bag"])
        print(" 轨迹 %d 帧  点数 %d~%d  长度 %.2f~%.2f m  最大间隔 %.3fs"
              % (r["frames"], r["points_min"], r["points_max"],
                 r["length_min_m"], r["length_max_m"], r["max_gap_s"]))
        print(" 点数<%d 的帧: %d (%.1f%%)  判定: %s"
              % (r["min_points_required"], r["short_frames"],
                 r["short_ratio_pct"], r["verdict"]))
        for h in r["guard_holds"]:
            print(" guard hold %.2fs  near_jump=%s  起 %s"
                  % (h["duration_s"], h["near_jump"], _fmt_ns(h["start_ns"])))


def cmd_mrm(args):
    from . import io
    from .modules import mrm
    for p in _bags(args.path):
        r = mrm.analyze(io.open_bag(p))
        r["bag"] = os.path.basename(p)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s   MRM 触发 %d 次" % (r["bag"], r["mrm_trigger_count"]))
        for t in r["mrm_transitions"]:
            print("   %s  %s -> %s" % (_fmt_ns(t["t_ns"]), t["from"], t["to"]))


def cmd_track(args):
    from . import io
    from .modules import tracking
    for p in _bags(args.path):
        r = tracking.analyze(io.open_bag(p))
        r["continuity"] = tracking.uuid_continuity(io.open_bag(p))
        r["bag"] = os.path.basename(p)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s   检测源 %s" % (r["bag"], r["det_topic"]))
        print(" %-20s %8s %10s %8s %10s" % ("类别", "检测帧", "跟踪丢失", "占比", "类别混淆"))
        for row in r["rows"]:
            print(" %-20s %8d %10d %7.1f%% %10d"
                  % (row["class"], row["det_frames"], row["tracking_lost"],
                     row["lost_pct"], row["class_confused"]))
        if r["top_confusions"]:
            print(" 主要混淆: " + ", ".join("%s→%s %d" % (c["from"], c["to"], c["count"])
                                          for c in r["top_confusions"]))
        print(" 跟踪轨迹 %d 条（≥%d 帧）" % (len(r["continuity"]), 20))


def cmd_lane(args):
    from . import io
    from .modules import lanechange
    for p in _bags(args.path):
        r = lanechange.analyze(io.open_bag(p), span_s=args.span)
        r["bag"] = os.path.basename(p)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s" % r["bag"])
        if r.get("error"):
            print(" %s" % r["error"]); continue
        print(" 窗口 %.1fs  行进 %.1fm (主轴向 %.1fm)"
              % (r["span_s"], r["travel_m"], r["travel_axis_m"]))
        print(" 横移 %+.2fm  (%s)   变道: %s"
              % (r["lateral_delta_m"], r["lateral_axis"],
                 "是" if r["lane_change_likely"] else "否"))
        for w in r["intent_windows"][:6]:
            print("   意图 %s ~ %s (%.1fs)"
                  % (_fmt_ns(w["start_ns"]), _fmt_ns(w["end_ns"]), w["duration_s"]))


def cmd_avoid(args):
    from . import io
    from .modules import avoidance
    for p in _bags(args.path):
        r = avoidance.analyze(io.open_bag(p), threshold_m=args.threshold)
        r["bag"] = os.path.basename(p)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s" % r["bag"])
        if r.get("error"):
            print(" %s" % r["error"]); continue
        print(" 路径横向最大偏移 %.2fm（%d 帧） → %s"
              % (r["max_abs_offset_m"], r["frames"],
                 "有绕行意图" if r["intent"] == "AVOIDING" else "直线（不绕）"))


def cmd_rosout(args):
    from . import io
    from .modules import rosout
    kws = args.keyword
    if args.logfile:
        for line in rosout.grep_logfile(args.logfile, kws, limit=args.limit):
            print(line)
        return
    for p in _bags(args.path):
        hits = rosout.grep_bag(io.open_bag(p), kws, level_min=args.level, limit=args.limit)
        if args.json:
            print(json.dumps({"bag": os.path.basename(p), "hits": hits},
                             ensure_ascii=False, indent=2))
            continue
        print("=" * 70)
        print(" %s  命中 %d 条" % (os.path.basename(p), len(hits)))
        for h in hits[:40]:
            print("  %s [%s] %s: %s"
                  % (_fmt_ns(h["t_ns"]), h["level"], h["node"][-28:], h["msg"][:110]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="bagdiag",
        description=" / Autoware MCAP 诊断工具（不依赖运行中的 ROS）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="包概览与完整性"); p.add_argument("path")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("stop", help="停障场景：减速起点/停车距离/减速度")
    p.add_argument("path"); p.set_defaults(func=cmd_stop)

    p = sub.add_parser("traj", help="轨迹健康度 + output guard hold")
    p.add_argument("path"); p.add_argument("--min-points", type=int, default=100)
    p.set_defaults(func=cmd_traj)

    p = sub.add_parser("mrm", help="MRM / 急停事件")
    p.add_argument("path"); p.set_defaults(func=cmd_mrm)

    p = sub.add_parser("track", help="跟踪丢失 / 类别混淆")
    p.add_argument("path"); p.set_defaults(func=cmd_track)

    p = sub.add_parser("lane", help="变道 / 取消变道（绝对坐标）")
    p.add_argument("path"); p.add_argument("--span", type=float, default=20.0)
    p.set_defaults(func=cmd_lane)

    p = sub.add_parser("avoid", help="绕行意图（路径横向偏移）")
    p.add_argument("path"); p.add_argument("--threshold", type=float, default=0.5)
    p.set_defaults(func=cmd_avoid)

    p = sub.add_parser("rosout", help="日志检索")
    p.add_argument("path", nargs="?")
    p.add_argument("-k", "--keyword", action="append", required=True)
    p.add_argument("--level", type=int, default=30, help="最低级别 10/20/30/40/50")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--logfile", help="改为检索纯文本日志文件")
    p.set_defaults(func=cmd_rosout)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
