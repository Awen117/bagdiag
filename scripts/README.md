# scripts/

按现场问题临时写的分析脚本，没进主包，但每个都能单独跑。

```bash
python3 scripts/话题体检.py  <bag.mcap>
python3 scripts/目标统计.py  <bag.mcap>
python3 scripts/健康体检.py  <diag输出的.json>
python3 scripts/批量体检.py  <bag目录>
```

`bag.py` / `text_log.py` 是被上面几个 import 的底层模块。
