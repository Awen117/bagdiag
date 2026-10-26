# -*- coding: utf-8 -*-
"""冒烟测试：不依赖真实包，验证模块能导入、纯函数正确。"""
import math

from bagdiag import path as path_mod


def test_length():
    assert path_mod.length([(0, 0), (3, 4)]) == 5.0
    assert path_mod.length([(0, 0)]) == 0.0


def test_length_multi():
    p = [(0, 0), (0, 3), (4, 3)]
    assert path_mod.length(p) == 7.0


def test_lateral_calc():
    from bagdiag.ego import body_frame
    # 车头朝 +x，前方 10m 偏左 2m
    ego = (0, 0.0, 0.0, 0.0, 0.0)
    lon, lat = body_frame(ego, 10.0, 2.0)
    assert abs(lon - 10.0) < 1e-6
    assert abs(lat - 2.0) < 1e-6


def test_new_modules_importable():
    """新增的三个模块至少能导入且暴露 analyze()。"""
    from bagdiag.modules import category, turnsignal, gap
    for mod in (category, turnsignal, gap):
        assert hasattr(mod, "analyze"), mod.__name__


def test_gap_on_tmp_info(tmp_path):
    """构造一个含时间断层的 .info，验证 gap 能检出。"""
    import json

    from bagdiag.modules import gap

    rows = []
    # 两片正常相邻
    rows.append({"bag_path": "/x/seg_20260101120000_0.mcap",
                 "start_time_cst": "20260101120000", "end_time_cst": "20260101120015"})
    rows.append({"bag_path": "/x/seg_20260101120000_1.mcap",
                 "start_time_cst": "20260101120015", "end_time_cst": "20260101120030"})
    # 第三片与前面断 100 秒
    rows.append({"bag_path": "/x/seg_20260101120000_2.mcap",
                 "start_time_cst": "20260101120210", "end_time_cst": "20260101120225"})
    f = tmp_path / "s.info"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    r = gap.analyze(str(f))
    assert r["session"] == "20260101120000"
    assert len(r["time_gaps"]) == 1
    assert r["time_gaps"][0]["gap_s"] == 100.0
    assert r["ok"] is False
