# -*- coding: utf-8 -*-
"""MCAP 读取与解码（支持 .mcap 与 .mcap.zst，自动缓存 reader）。"""
import os
import tempfile
from mcap.reader import make_reader
from mcap_ros2.decoder import Decoder

_READERS = {}
_DECODER = Decoder()


def resolve(path):
    """.mcap.zst 就地解压到临时目录后返回 .mcap 路径。"""
    if not path.endswith(".zst"):
        return path
    out = os.path.join(tempfile.gettempdir(),
                       os.path.basename(path)[:-4])
    if not os.path.exists(out):
        from zstandard import ZstdDecompressor
        with open(path, "rb") as i, open(out, "wb") as o:
            ZstdDecompressor().copy_stream(i, o)
    return out


def open_bag(path):
    p = resolve(path)
    if p not in _READERS:
        fh = open(p, "rb")
        _READERS[p] = (make_reader(fh), fh)
    return _READERS[p][0]


def stamp(msg, fallback_ns=0):
    """有 header 用 header.stamp，否则用 bag 的 log_time。"""
    h = getattr(msg, "header", None)
    s = getattr(h, "stamp", None) if h is not None else None
    if s is None:
        return fallback_ns
    return int(s.sec) * 10**9 + int(s.nanosec)


def iter_msgs(reader, topics):
    """按话题迭代 (topic, t_ns, msg)；解码失败的跳过。"""
    if isinstance(topics, str):
        topics = [topics]
    for schema, channel, msg in reader.iter_messages(topics=topics):
        try:
            mo = _DECODER.decode(schema, msg)
        except Exception:
            continue
        if mo is not None:
            yield channel.topic, stamp(mo, msg.log_time), mo


def info(path):
    """包概览：时长、消息数、话题数、零消息话题。"""
    reader = open_bag(path)
    s = reader.get_summary()
    if not s or not s.statistics:
        return {"path": path, "error": "no summary"}
    st = s.statistics
    chans = {c.id: c for c in s.channels.values()}
    counts = dict(st.channel_message_counts or {})
    topics = []
    for cid, c in chans.items():
        topics.append({"topic": c.topic, "messages": counts.get(cid, 0)})
    topics.sort(key=lambda x: -x["messages"])
    return {
        "path": os.path.basename(path),
        "duration_s": round((st.message_end_time - st.message_start_time) / 1e9, 2),
        "start_ns": st.message_start_time,
        "end_ns": st.message_end_time,
        "messages": st.message_count,
        "topics": len(chans),
        "schema_count": len(s.schemas),
        "topic_detail": topics,
        "zero_msg_topics": [t["topic"] for t in topics if t["messages"] == 0],
    }
