# -*- coding: utf-8 -*-
"""MCAP bag 分析: 概要/频道/车速/急刹/规划/状态/急停/目标/诊断/AEB."""

import os
import re
import glob
import time as _time
import hashlib
import tempfile
import threading
from collections import Counter, defaultdict
from datetime import datetime

from mcap.reader import make_reader
from mcap_ros2.decoder import Decoder

try:
    from zstandard import ZstdDecompressor
    HAVE_ZSTD = True
except ImportError:
    HAVE_ZSTD = False

DESKTOP = os.path.expanduser("~") + "/Desktop"
BAG_DIR = os.environ.get("BAG_DIR") or os.path.join(DESKTOP, "bags")
CACHE_DIR = os.path.join(tempfile.gettempdir(), "mcap_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DECODERS = {}  # lock-guarded single decoder reuse (threaded safety not needed, stdio single thread)
_cache_lock = threading.Lock()


def _g(obj, *path, default=None):
    for p in path:
        if obj is None:
            return default
        obj = getattr(obj, p, None)
    return obj if obj is not None else default


def _fmt_t(ns, start_ns, wall=True):
    rel = (ns - start_ns) / 1e9
    if wall:
        try:
            w = datetime.fromtimestamp(ns / 1e9).strftime("%H:%M:%S.%f")[:-3]
        except Exception:
            w = ""
        return f"{w} (+{rel:.1f}s)"
    return f"{rel:.1f}s"


def _resolve_path(path):
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    if path.endswith(".zst"):
        st = os.stat(path)
        key = hashlib.md5(f"{path}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:12]
        target = os.path.join(CACHE_DIR, os.path.basename(path)[:-4] + "_" + key + ".mcap")
        valid = False
        if os.path.isfile(target):
            try:
                with open(target, "rb") as fh:
                    valid = fh.read(8) == b"\x89MCAP0\r\n"
            except OSError:
                valid = False
        if not valid:
            if not HAVE_ZSTD:
                raise RuntimeError("缺少 zstandard 库, 无法解压 .zst")
            with open(path, "rb") as fh, open(target, "wb") as out:
                ZstdDecompressor().copy_stream(fh, out)
        return target
    return path


def _open(path):
    p = _resolve_path(path)
    dec = DECODERS.get(p)
    if dec is None:
        fh = open(p, "rb")
        reader = make_reader(fh)
        dec = (reader, Decoder(), fh)
        DECODERS[p] = dec
    return dec


def _scan_bag(path, topics=None):
    reader, _, _ = _open(path)
    summary = reader.get_summary()
    channels = list(summary.channels.values()) if summary else []
    if topics:
        channels = [c for c in channels if c.topic in set(topics)]
    first = None
    last = None
    for c in channels:
        st = _g(c, "metadata", default={})
    stats = summary.statistics if summary else None
    if stats:
        try:
            first = stats.message_start_time
            last = stats.message_end_time
        except Exception:
            first = last = None
    return reader, channels, first, last, stats


def _iter_decode(reader, topics):
    dec = DECODERS.get("_global_dec")
    if dec is None:
        dec = Decoder()
        DECODERS["_global_dec"] = dec
    for schema, channel, msg in reader.iter_messages(topics=topics):
        try:
            mo = dec.decode(schema, msg)
        except Exception:
            mo = None
        yield channel, msg.log_time, mo


def scan_sessions():
    print("🔍 扫描桌面日志目录...")
    print("=" * 76)
    print("  📹 远驾日志 (远程驾驶相机推流)")
    if os.path.isdir(os.path.join(DESKTOP, "远驾日志")):
        for f in sorted(glob.glob(os.path.join(DESKTOP, "远驾日志", "*"))):
            sz = os.path.getsize(f) / 1024.0
            print(f"    {os.path.basename(f)} ({sz:.0f} KB)")
    else:
        print("    (无)")
    print("=" * 76)
    print("  🚗 自驾日志 (autoware 节点日志)")
    if os.path.isdir(os.path.join(DESKTOP, "自驾日志")):
        for d in sorted(glob.glob(os.path.join(DESKTOP, "自驾日志", "*"))):
            if not os.path.isdir(d):
                continue
            n = len(glob.glob(os.path.join(d, "**", "*.log"), recursive=True))
            print(f"    {os.path.basename(d)}  ({n} 个日志文件)")
    else:
        print("    (无)")
    print("=" * 76)
    print("  📦 bag 包 (mcap)")
    if not os.path.isdir(BAG_DIR):
        print("    (无)")
        return ""
    total = 0
    for d in sorted(glob.glob(os.path.join(BAG_DIR, "*"))):
        if not os.path.isdir(d) or os.path.basename(d).startswith("."):
            continue
        day = os.path.basename(d)
        scenes = [s for s in sorted(glob.glob(os.path.join(d, "*"))) if os.path.isdir(s)]
        bags = sorted(glob.glob(os.path.join(d, "*.mcap*")))
        if not scenes:
            scenes = [d]
        size_gb = 0
        for f in glob.glob(os.path.join(d, "**", "*.mcap*"), recursive=True):
            size_gb += os.path.getsize(f)
        total += size_gb
        print(f"  📅 {day}  ({size_gb/1e9:.1f} GB, {len(bags)} 个直接 mcap)")
        for s in scenes:
            if s == d:
                continue
            sbags = sorted(glob.glob(os.path.join(s, "*.mcap*")))
            if not sbags:
                continue
            print(f"     🎬 {os.path.basename(s)}: {len(sbags)} 个")
            for b in sbags:
                print(f"        - {os.path.basename(b)} ({os.path.getsize(b)/1e6:.0f} MB)")
    print(f"  合计 {total/1e9:.1f} GB")
    return ""


def find_bags(keyword=None, date=None):
    prints = []
    for d in sorted(glob.glob(os.path.join(BAG_DIR, "*"))):
        if not os.path.isdir(d):
            continue
        day = os.path.basename(d)
        if date and day != date:
            continue
        for f in sorted(glob.glob(os.path.join(d, "**", "*.mcap*"), recursive=True)):
            base = os.path.realpath(f)
            scene_rel = os.path.relpath(os.path.dirname(base), d)
            hit = True
            if keyword:
                hit = keyword.lower() in scene_rel.lower() or keyword.lower() in os.path.basename(f).lower()
            if hit and keyword is None:
                hit = True
            if hit:
                prints.append(f"{day}/{scene_rel}/{os.path.basename(f)} ({os.path.getsize(f)/1e6:.0f} MB)")
    print(f"🔎 搜索到 {len(prints)} 个 bag:")
    for p in prints:
        print(f"  {p}")
    if not prints:
        print("  (无匹配结果)")
    return ""


def bag_topics(path):
    reader, channels, first, last, stats = _scan_bag(path)
    print(f"📦 {os.path.basename(path)} 共 {len(channels)} 个通道")
    print(f"{'topic':60s}  type                        count")
    seq = sorted(channels, key=lambda c: c.topic)
    for c in seq:
        count = ""
        if stats and stats.channel_message_counts:
            count = str(stats.channel_message_counts.get(c.id, ""))
        print(f"{c.topic:60s}  {c.message_encoding if hasattr(c,'message_encoding') else ''}  {count}")
    return ""


def bag_overview(path):
    reader, channels, first, last, stats = _scan_bag(path)
    print(f"📦 {os.path.basename(path)}")
    if first and last:
        dur = (last - first) / 1e9
        print(f"  ⏱ 时长: {dur/60:.1f} 分钟 ({dur:.1f} 秒)")
        print(f"  🕐 开始: {datetime.fromtimestamp(first/1e9).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  🕐 结束: {datetime.fromtimestamp(last/1e9).strftime('%Y-%m-%d %H:%M:%S')}")
    total = 0
    if stats:
        total = sum(stats.channel_message_counts.values())
    print(f"  📊 消息总数: {total}")
    print(f"  📡 topic 数: {len(channels)}")
    top = []
    if stats:
        id2ch = {c.id: c for c in channels}
        for cid, cnt in sorted(stats.channel_message_counts.items(), key=lambda kv: -kv[1]):
            c = id2ch.get(cid)
            if c:
                top.append((c.topic, cnt, c.message_encoding))
    if first and last:
        dur = (last - first) / 1e9
        print("  🏷 高频 topic (rate/s):")
        for t, cnt, typ in top[:15]:
            print(f"    {t:60s} {cnt:8d}  {cnt/dur:.1f}/s  {typ}")
    return ""


def _ego(reader, t0):
    pts = []
    for ch, logt, m in _iter_decode(reader, ["/localization/kinematic_state"]):
        if m is None:
            continue
        v = _g(m, "twist", "twist", "linear", "x")
        a = _g(m, "twist", "twist", "linear", "y")  # 有些x轴向侧向, 保守只用x
        pts.append((logt, v if v is not None else 0.0))
    if not pts:
        # 回退: vehicle/status/velocity_status
        for ch, logt, m in _iter_decode(reader, ["/vehicle/status/velocity_status"]):
            if m is None:
                continue
            v = _g(m, "velocity", "x") or _g(m, "velocity") or _g(m, "velocity_mps") or 0.0
            pts.append((logt, float(v)))
    if not pts:
        print("  ⚠️ 无 ego 速度话题(定位或车速话题缺失)")
        return None
    pts.sort()
    vmax = max(v for _, v in pts)
    vmin = min(v for _, v in pts)
    vmean = sum(v for _, v in pts) / len(pts)
    print(f"  🚗 ego 车速(样本 {len(pts)}): max={vmax:.2f} m/s ({vmax*3.6:.1f} km/h), mean={vmean:.2f}, min={vmin:.2f}")
    # 急刹事件: 逐样本减速度 < -2.5 m/s² (dt 下限 0.015s: 过滤同刻重复样本产生的假急刹)
    hard = []
    for i in range(1, len(pts)):
        dt = (pts[i][0] - pts[i - 1][0]) / 1e9
        if dt < 0.015 or dt > 0.5:
            continue
        a = (pts[i][1] - pts[i - 1][1]) / dt
        if a < -2.5:
            hard.append((pts[i][0], a, pts[i - 1][1]))
    if hard:
        merged = []
        for t, a, v0 in hard:
            if merged and (t - merged[-1][0]) / 1e9 < 1.5:
                merged[-1][2] = min(merged[-1][2], a)
            else:
                merged.append([t, a, v0])
        print(f"  🛑 急刹事件(减速度<-2.5m/s²): {len(merged)} 次")
        for t, a, v0 in merged:
            print(f"      {_fmt_t(t, t0)}  decel={a:.2f} m/s²  v_before={v0:.2f} m/s")
    else:
        print("  🛑 急刹事件: 无")
    # 刹停区间 v<0.1
    stops = []
    cur = None
    for t, v in pts:
        if v < 0.1:
            if cur is None:
                cur = [t, t, v]
            else:
                cur[1] = t
        else:
            if cur is not None and (cur[1] - cur[0]) / 1e9 > 1.0:
                stops.append(cur)
            cur = None
    if cur is not None and (cur[1] - cur[0]) / 1e9 > 1.0:
        stops.append(cur)
    if stops:
        print(f"  ⏹ 刹停区间(车速<0.1持续>1s): {len(stops)} 段")
        for s in stops[:12]:
            print(f"      {_fmt_t(s[0], t0)} -> {_fmt_t(s[1], t0)}  ({((s[1]-s[0])/1e9):.1f}s)")
        if len(stops) > 12:
            print(f"      ... 共 {len(stops)} 段")
    return pts


def _traj(reader, t0):
    cands = [
        "/planning/scenario_planning/motion_planning/motion_velocity_planner/trajectory",
        "/planning/scenario_planning/trajectory",
        "/planning/scenario_planning/velocity_smoother/trajectory",
        "/planning/trajectory",
        "/planning/scenario_planning/scenario_selector/trajectory",
        "/planning/scenario_planning/motion_planning/path_optimizer/trajectory",
    ]
    use = None
    for cn in cands:
        for ch, logt, m in _iter_decode(reader, [cn]):
            use = cn
            break
        if use:
            break
    if not use:
        print("  ⚠️ 规划轨迹话题未发布")
        return
    n = 0
    gaps = []
    prev = None
    for ch, logt, m in _iter_decode(reader, [use]):
        n += 1
        if prev is not None:
            d = (logt - prev) / 1e9
            if d > 0.5:
                gaps.append((logt, d))
        prev = logt
    print(f"  🛣 规划轨迹 {use.split('/')[-1]}: 发布 {n} 帧")
    if n and prev:
        print(f"      等效频率 {(n*1e9)/(prev-(t0 if True else prev)+1e-9):.1f} Hz")
    if gaps:
        print(f"  ⚠️ 轨迹丢失(间隔>0.5s): {len(gaps)} 次")
        for g, d in gaps[:8]:
            print(f"      {_fmt_t(g, t0)}  间隔 {d:.1f}s")
    else:
        print("  ✅ 轨迹连续无丢失")


def _planning_state(reader, t0):
    done = set()
    for cn in ["/autoware/state", "/autoware/engage", "/system/operation_mode/state", "/planning/teleop_active"]:
        if cn in done:
            continue
        seen = []
        for ch, logt, m in _iter_decode(reader, [cn]):
            if m is None:
                continue
            if hasattr(m, "data"):
                v = m.data
            else:
                keys = [k for k in dir(m) if not k.startswith("_") and not callable(getattr(m, k))]
                v = [k for k in keys if k in ("state", "mode", "emergency", "mrm", "safe_stop")][:1]
                v = m.data if hasattr(m, "data") else (getattr(m, "state", None) or getattr(m, "mode", None) or m)
            if not seen or seen[-1][1] != v:
                seen.append((logt, v))
        paid = len(seen)
        print(f"  🔀 {cn}: {paid} 次变化")
        for t, v in seen[:15]:
            print(f"      {_fmt_t(t, t0)}  -> {v}")
        done.add(cn)


def _emergency(reader, t0):
    for cn in ["/control/command/emergency_cmd", "/control/current_gate_mode", "/control/gate_mode_cmd"]:
        events = []
        for ch, logt, m in _iter_decode(reader, [cn]):
            if m is None:
                continue
            flags = []
            for f in ("emergency", "mrm", "safe_stop", "mode", "data"):
                v = getattr(m, f, None)
                if v is not None and f in ("emergency", "mrm", "safe_stop") and v != 0:
                    flags.append(f"{f}={v}")
            if flags:
                events.append((logt, " ".join(flags)))
        if events:
            print(f"  🚨 {cn}: {len(events)} 次触发")
            for t, e in events[:10]:
                print(f"      {_fmt_t(t, t0)}  {e}")
        else:
            print(f"  🚨 {cn}: 无触发")


def _objects(reader, t0):
    use = None
    for cn in ["/perception/object_recognition/tracking/objects", "/perception/object_recognition/objects"]:
        for ch, logt, m in _iter_decode(reader, [cn]):
            use = cn
            break
        if use:
            break
    if not use:
        print("  ⚠️ 目标物话题缺失")
        return
    buckets = defaultdict(int)
    labels = Counter()
    bkt = 2.0
    n = 0
    for ch, logt, m in _iter_decode(reader, [use]):
        n += 1
        objs = getattr(m, "objects", []) or []
        b = int((logt - t0) / 1e9 / bkt)
        buckets[b] = max(buckets[b], len(objs))
        for o in objs:
            cl = getattr(o, "classification", None) or []
            for c in cl[:1]:
                lab = getattr(c, "label", None)
                lab = getattr(lab, "value", lab)
                labels[lab] += 1
    if not n:
        print("  ⚠️ 无目标物消息")
        return
    # 过滤无标签的
    unique = labels.copy() if labels else Counter()
    print(f"  🎯 {use.split('/')[-1]}: {n} 帧消息")
    if buckets:
        mx = max(buckets.values())
        print(f"      max 同时目标数: {mx}")
        up = sorted(buckets.items())
        curve = [v for _, v in up]
        # 简化为: >80%情况下的典型数量
        typical = sorted(curve)[len(curve) // 2]
        print(f"      中位目标数: {typical}, 目标>0 时间占比: {(sum(1 for v in curve if v>0)/len(curve))*100:.0f}%")
    if labels:
        print(f"      🏷 目标类别分布 Top8 (label编码):")
        for lab, c in labels.most_common(8):
            name = {0: "未知", 1: "轿车", 2: "卡车", 3: "客车/BUS", 4: "挂车", 5: "摩托车", 6: "自行车", 7: "行人", 8: "低速车辆", 9: "静态物体"}.get(lab, str(lab))
            print(f"          {lab} ({name}): {c}")


def _diagnostics(reader, t0):
    n = 0
    levels = Counter()
    err_names = Counter()
    first_err = None
    for ch, logt, m in _iter_decode(reader, ["/diagnostics"]):
        if m is None:
            continue
        n += 1
        for st in (getattr(m, "status", None) or []):
            lv = getattr(st, "level", None)
            levels[lv] += 1
            if lv not in (0, None):
                nm = getattr(st, "name", "")
                err_names[(lv, nm)] += 1
                if lv == 2 and first_err is None:
                    first_err = (logt, nm, getattr(st, "message", "")[:120])
    print(f"  🩺 /diagnostics: {n} 帧")
    if levels:
        lvmap = {0: "OK", 1: "WARN", 2: "ERROR", 3: "STALE"}
        for lv, c in levels.most_common():
            print(f"      {lvmap.get(lv, lv)}: {c}")
    if first_err:
        t, nm, msg = first_err
        print(f"      🚩 首个 ERROR: {_fmt_t(t, t0)}  {nm[:60]}")
        print(f"         {msg}")
    na = [k for k, c in err_names.most_common(10) if k[0] == 2]
    if na:
        print("      ERROR 状态项 Top5:")
        for k, c in err_names.most_common(5):
            print(f"          L{getattr(k, 'level', 0)} {k[1][:70]}: {c}")


def _aeb(reader, t0):
    _cns = [c.strip() for c in os.environ.get("AEB_TOPICS", "").split(",") if c.strip()]
    for cn in (_cns or ["/control/aeb/ctrl", "/control/brake/ctrl"]):
        n = 0
        dirty = 0
        for ch, logt, m in _iter_decode(reader, [cn]):
            if m is None:
                continue
            n += 1
            for k in dir(m):
                if k.startswith("_") or callable(getattr(m, k)):
                    continue
                v = getattr(m, k)
                if isinstance(v, (bool, int)) and v not in (0, False, None):
                    dirty += 1
        if n:
            print(f"  🛟 {cn}: {n} 帧 (非零字段计数 {dirty})")


def analyze_bag(path, sections):
    if sections == ["all"] or sections == ["*"]:
        sections = ["ego_state", "trajectory", "planning_state", "emergency", "objects", "diagnostics", "teleop", "aeb"]
    t_start = _time.time()
    reader, channels, first, last, stats = _scan_bag(path)
    base = os.path.basename(path)
    print("=" * 76)
    print(f"  🧪 bag 深度分析: {base}")
    print("=" * 76)
    if first and last:
        print(f"  ⏱ 时长 {(last-first)/1e9:.0f}s | 开始 {datetime.fromtimestamp(first/1e9).strftime('%Y-%m-%d %H:%M:%S')} | 消息 {sum(stats.channel_message_counts.values()) if stats else '?'}")
    t0 = first or 0
    for s in sections:
        fn = {"ego_state": _ego, "trajectory": _traj, "planning_state": _planning_state,
              "emergency": _emergency, "objects": _objects, "diagnostics": _diagnostics,
              "aeb": _aeb, "teleop": lambda r, t0: _planning_state_all(r, t0)}.get(s)
        if fn:
            print("-" * 76)
            print(f"  ◀ {s}")
            try:
                fn(reader, t0)
            except Exception:
                print(f"  ⚠️ {s} 分析失败(数据格式不兼容)")
    print("=" * 76)
    print(f"  ⏲ 分析耗时 {_time.time()-t_start:.1f}s")
    return ""


def _planning_state_all(reader, t0):
    for cn in ["/planning/teleop_active", "/external/selected/steering_cmd", "/external/selected/pedals_cmd"]:
        n = 0
        on = 0
        for ch, logt, m in _iter_decode(reader, [cn]):
            if m is None:
                continue
            n += 1
            d = getattr(m, "data", None)
            if d is None:
                d = getattr(m, "steering_tire_angle", None)
                d = None if d is None else (abs(d) > 0.01)
            if d:
                on += 1
        if n:
            print(f"  🕹 {cn}: {n} 帧, 激活态帧数 {on}")
