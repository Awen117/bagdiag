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
