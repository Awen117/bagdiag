# -*- coding: utf-8 -*-
"""文本日志分析: 远驾日志(camera streamer) + 自驾日志(autoware node logs)."""

import os
import re
import glob
from collections import Counter, defaultdict

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
REMOTE_DIR = os.path.join(DESKTOP, "远驾日志")
AUTO_DIR = os.path.join(DESKTOP, "自驾日志")

DT_RE = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+")
LVL_RE = re.compile(r"\[(FATAL|ERROR|WARN|WARNING|INFO|DEBUG)\]", re.IGNORECASE)

ROS_LINE_RE = re.compile(
    r"^\s*[\(\[][^\)\]]+[\)\]]?\s*(?:[" + re.escape("[]()[]") + r"]*)?.*"
)
LOG_PREFIX_RE = re.compile(
    r"^\s*(?:\(\w+-\d+\)\s*)?(?:\[\d+:\d+:\d+(?:\.\d+)?\]\s*)?\[(FATAL|ERROR|WARN|WARNING|INFO|DEBUG)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]\s*\[([^\]]+)\]:?\s*(.*)$",
    re.IGNORECASE,
)
CAM_LAT_RE = re.compile(r"Camera (\d+)\s+(h265|rgb) latency:\s*(\d+)\s*ms\s*\(Size:\s*(\d+)\s*bytes\)")
CAM_INIT_RE = re.compile(r"Node initialized with name:\s*(\w+)", re.IGNORECASE)
SRT_RE = re.compile(r"srt://[^ ?]+")

ERROR_KW = [
    "timeout", "timed out", "超时", "disconnect", "断连", "connection",
    "fail", "failed", "错误", "exception", "traceback", "abort", "crash",
    "unable", "cannot", "refused", "lost", "dropped", "overrun", "latched",
    "invalid", "does not match", "mismatch", "calib", "fixate", "no device",
]


def _level_of(line):
    m = LVL_RE.search(line)
    return m.group(1).upper() if m else None


def _parse_structured(line):
    """ROS2 stdout 格式 [node] [LEVEL 2026-08-25 11:45:54.609] [module@fn:line]: msg"""
    m = LOG_PREFIX_RE.match(line)
    if not m:
        return None
    lvl, ts, module, msg = m.groups()
    return {"level": lvl.upper(), "time": ts, "module": module, "msg": msg.strip(), "raw": line}


def _camera_stats(lines):
    stats = defaultdict(lambda: {"h265": [], "rgb": []})
    names = {}
    for ln in lines:
        m = CAM_INIT_RE.search(ln)
        if m:
            names.setdefault(len(names), m.group(1))
    for ln in lines:
        m = CAM_LAT_RE.search(ln)
        if m:
            cam, kind, lat, size = m.groups()
            d = stats[cam]
            d[kind].append(int(lat))
    out = []
    for cam in sorted(stats, key=int):
        h = stats[cam]["h265"]
        r = stats[cam]["rgb"]
        label = names.get(int(cam), f"Camera{cam}")
        def fmt(arr):
            if not arr:
                return "无数据"
            return f"n={len(arr)} avg={sum(arr)//len(arr)}ms min={min(arr)}ms max={max(arr)}ms"
        out.append(f"  Camera {cam} [{label}]\n    h265: {fmt(h)}\n    rgb : {fmt(r)}")
    return "\n".join(out)


def _analyze_remote_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    errors = []
    warns = []
    warns_kw = Counter()
    srt_uris = set()
    for i, ln in enumerate(lines, 1):
        lvl = _level_of(ln)
        if lvl == "ERROR":
            errors.append((i, ln.strip()))
        elif lvl in ("WARN", "WARNING"):
            warns.append((i, ln.strip()))
            if "GST" in ln:
                warns_kw["GST/camera issue"] += 1
            m = SRT_RE.search(ln)
            if m:
                srt_uris.add(m.group(0))
    cam = _camera_stats(lines)
    print("=" * 76)
    print(f"  📹 远驾日志分析: 相机推流(远程驾驶视频链路)")
    print(f"  📁 {path}")
    print(f"  📊 总行数 {len(lines)} | ❌ ERROR {len(errors)} | ⚠️ WARN {len(warns)}")
    says = [
        "  🔗 推流目标: " + (", ".join(sorted(srt_uris)) or "未发现SRT推流配置"),
    ]
    print("\n".join(says))
    print(f"  📡 相机延时统计:")
    print(cam or "  (无延时日志)")
    print("  ⚠️ 主要警告模式:")
    if warns_kw:
        for k, v in warns_kw.most_common():
            print(f"    {k}: {v} 条")
    else:
        print("    无")
    if errors:
        print("  ❌ 错误明细(前20条):")
        for i, ln in errors[:20]:
            print(f"    L{i}: {ln[:160]}")
        if len(errors) > 20:
            print(f"    ... 共 {len(errors)} 条错误")
    return path


def _collect_auto_files(path):
    files = []
    if os.path.isfile(path):
        return [path]
    patterns = ["*.log", "*.txt"]
    for p in patterns:
        files.extend(glob.glob(os.path.join(path, "**", p), recursive=True))
    uniq = []
    seen = set()
    for f in files:
        if f not in seen and ".log.txt" not in f.split(os.sep)[-1]:
            seen.add(f)
            uniq.append(f)
    return uniq


def _analyze_auto_file(path, keyword=None, errors_only=False):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    errors = []
    warns = []
    err_msgs = Counter()
    mod_errors = Counter()
    mod_warns = Counter()
    for i, ln in enumerate(lines, 1):
        if keyword and keyword.lower() not in ln.lower():
            continue
        p = _parse_structured(ln)
        if p:
            if p["level"] == "ERROR":
                errors.append((i, p))
                err_msgs[p["msg"][:120]] += 1
                mod_errors[p["module"]] += 1
            elif p["level"] in ("WARN", "WARNING"):
                warns.append((i, p))
                mod_warns[p["module"]] += 1
        else:
            if keyword and keyword.lower() in ln.lower() and ("error" in ln.lower() or "fail" in ln.lower()):
                errors.append((i, {"raw": ln.strip(), "msg": ln.strip()[:120], "module": "?", "level": "ERROR"}))
    print(f"  📁 {os.path.basename(path)}")
    print(f"     📊 总行 {len(lines)} | ❌ ERROR {len(errors)} | ⚠️ WARN {len(warns)}")
    if errors_only and not errors and not warns:
        return
    if mod_errors:
        print("     ❌ 报错模块 Top5:")
        for m, c in mod_errors.most_common(5):
            print(f"        {m}: {c}")
    if mod_warns:
        print("     ⚠️ 警告模块 Top5:")
        for m, c in mod_warns.most_common(5):
            print(f"        {m}: {c}")
    if errors:
        print("     ❌ 首条错误:")
        i, p = errors[0]
        print(f"        L{i} [{(p.get('time') or '')}\u2003{p.get('module','')}]: {p.get('msg','')[:200]}")


def analyze_text_logs(path=None, kind="auto", errors_only=False, keyword=None):
    print("=" * 76)
    print("  🚗 ROS2 日志分析")
    print("=" * 76)
    if path is None:
        found = []
        if os.path.isdir(REMOTE_DIR):
            found.extend(sorted(glob.glob(os.path.join(REMOTE_DIR, "*"))))
        if os.path.isdir(AUTO_DIR):
            found.extend(sorted(glob.glob(os.path.join(AUTO_DIR, "*"))))
        if not found:
            print("  未找到桌面日志目录(远驾日志/自驾日志)")
            return ""
        for p in found:
            analyze_text_logs(p, kind, errors_only, keyword)
        return ""

    if os.path.isdir(path):
        absp = os.path.abspath(path)
        name = os.path.basename(os.path.normpath(path))
        if os.path.isdir(REMOTE_DIR) and absp.startswith(os.path.abspath(REMOTE_DIR)):
            print(f"📂 远驾日志会话: {path}")
            rfiles = sorted(glob.glob(os.path.join(path, "**", "*.log*"), recursive=True))
            if not rfiles:
                print("   (无日志文件)")
                return ""
            for f in rfiles:
                _analyze_remote_file(f)
            return ""
        if os.path.isdir(AUTO_DIR) and absp.startswith(os.path.abspath(AUTO_DIR)):
            files = _collect_auto_files(path)
            if not files:
                print(f"  (空目录) {path}")
                return ""
            print(f"📂 自驾日志会话: {path}")
            print(f"   📁 {len(files)} 个节点日志文件")
            cnt = Counter()
            for f in files:
                m = os.path.basename(f)
                m = re.sub(r"_\d+_\d+.*$", "", m)
                cnt[m] += 1
            print(f"   节点分类: {', '.join(f'{k}({v})' for k, v in cnt.most_common(20))}")
            for f in files:
                _analyze_auto_file(f, keyword, errors_only)
            return ""
        if re.match(r"^\d{10,14}$", name) and os.path.basename(path) == name:
            files = _collect_auto_files(path)
            if not files:
                print(f"  (空目录) {path}")
                return ""
            print(f"📂 自驾日志会话: {path}")
            print(f"   📁 {len(files)} 个节点日志文件")
            for f in files:
                _analyze_auto_file(f, keyword, errors_only)
            return ""

    if path.lower().endswith((".log", ".txt")) or os.path.isfile(path):
        kind_name = "远驾" if ("远驾" in path or "remote" in path.lower()) else "自驾"
        if kind != "auto" and kind in ("远驾", "自驾"):
            kind_name = kind
        if kind_name == "远驾" or ("camera" in path.lower()):
            _analyze_remote_file(path)
        else:
            _analyze_auto_file(path, keyword, errors_only)
        return ""

    print(f"  (未找到路径) {path}")
    return ""


def show_log_lines_impl(path, line, context=5):
    if not os.path.isfile(path):
        return f"文件不存在: {path}"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    line = int(line)
    start = max(1, line - context)
    end = min(len(lines), line + context)
    out = [f"📄 {path}  (共 {len(lines)} 行), 显示 {start}-{end}:"]
    for i in range(start, end + 1):
        mark = "  ▶" if i == line else "   "
        out.append(f"{mark} L{i}: {lines[i - 1].rstrip()[:300]}")
    return "\n".join(out)
