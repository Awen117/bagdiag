# bagdiag

Autoware / ROS2 **MCAP 录包诊断工具**。离线跑，不依赖运行中的 ROS。

面向回归测试与现场排查：把"这段包到底停没停住、刹得猛不猛、跟丢了没有、变没变道、有没有误触发 MRM"这类问题，用一条命令算出来。

```
$ bagdiag stop ./sample_11205.mcap
最高车速 31.1 km/h   停稳: 是
减速 35.6 m / 11.88 s   峰值 -2.52 / 平均 -1.2 m/s²
停稳时最近目标 9.0 m   MRM NORMAL   AEB False
判定: PASS
```

## 安装

```bash
git clone https://github.com/<your-name>/bagdiag.git
cd bagdiag
pip install -e .
```

依赖只有三个：`mcap`、`mcap-ros2-support`、`zstandard`。支持 `.mcap` 和整文件 zstd 压缩的 `.mcap.zst`（自动解到临时目录）。

## 命令

| 命令 | 用途 |
|---|---|
| `info` | 包概览：时长、消息数、话题数、零消息话题 |
| `stop` | 停障场景：减速起点、停车距离、峰值/平均减速度、与目标距离、AEB/MRM |
| `traj` | 轨迹健康度：点数/长度塌缩、发布间隔、output guard hold（含 near_jump） |
| `mrm` | MRM 状态机时间线、急停次数 |
| `track` | 跟踪质量：跟踪丢失率、类别混淆、UUID 续存 |
| `lane` | 变道/取消变道：地图绝对坐标横移量、变道意图时段 |
| `avoid` | 绕行意图：路径相对车体中心线的横向偏移 |
| `rosout` | 日志检索（bag 内 `/rosout` 或车机 `1_stdout.log`） |

`path` 可以是单个 `.mcap`，也可以是目录（批量跑）。

加 `--json` 输出结构化结果，方便接到平台或 CI。

```bash
bagdiag --json stop ./segments/ > stop.json
```

## 口径说明（重要）

这些口径是踩过坑之后定下来的，用错会得出完全相反的结论。

### 1. 坐标系

```
/perception/object_recognition/detection/objects        base_link 帧
/perception/object_recognition/detection/bevfusion/objects  base_link 帧
/perception/object_recognition/tracking/objects         map 帧
/perception/object_recognition/objects                  map 帧
```

做"检测有、跟踪无"对比时，**必须先用 ego 位姿把检测转到 map**，否则会得到大量假漏检。`track` 命令内部已处理。

### 2. 跟踪丢失 vs 类别混淆

- **跟踪丢失** = 检测层有目标，但跟踪层同位置 **2m 内完全没有任何目标**
- **类别混淆** = 跟踪层有目标、位置对得上，只是类别标签不同

不要用"位置 + 尺寸"双匹配算漏检 —— 类别判错但尺寸差得多时会被算成漏检，漏检率虚高（实测同一场景漏检率虚高一个数量级）。

### 3. 横移量（判变道）

只有 **地图绝对坐标** 可靠：

- ❌ 用初始 yaw 投影 —— 弯道/长距离会放大成假值（实测能放大成十几米假值）
- ❌ 用分段航向积分 —— 车自己转向会把横移吸收掉，算出 ≈0（实测真值约一个车道宽，却算出接近 0）
- ✅ 先确认路段走向，再看垂直方向坐标的绝对变化量。一个车道宽约 3.0–3.5m

另外：**lane ID 变化 ≠ 变道**（相邻 lanelet 沿路连续编号，沿路行驶本来就会变）。

### 4. 轨迹点数 / output guard

- `traj` 的"点数塌缩"：新版规划器会输出**固定点数**的轨迹（点数由规划周期与时间步长决定），用老的"点数 ≥100"阈值校验会一直失败 → 表现为规划卡住、放权不走、甚至反复触发 MRM
- `output guard` 的 `near_jump` 在 `/rosout` 日志里，才是 #758 类跳变判定的权威值；自己拿 path 相邻帧算的是另一个口径

```bash
bagdiag traj ./segments/          # 点数/长度 + guard hold
bagdiag rosout ./segments/ -k "Output guard"
bagdiag rosout ./segments/ -k "trajectory_check"
```

### 5. 减速距离的定义

`stop` 命令的 `decel_distance_m` = **从首次达到最高车速的点，到速度降到 0.3 km/h 以下的点**，沿自车轨迹累计的行驶距离。换定义（比如从"开始掉速"算起）数值会不同，对比时注意口径一致。

## 典型用法

```bash
# 1. 先看包完整不完整
bagdiag info ./segments/

# 2. 停障类场景（1.1 / 1.2 / 1.3 / 1.4 / 1.6）
bagdiag stop ./segments/

# 3. 轨迹是不是塌缩了 / guard 有没有 hold
bagdiag traj ./segments/

# 4. 有没有误触发急停
bagdiag mrm ./segments/

# 5. 感知跟丢了多少
bagdiag track ./segments/

# 6. 变道到底发生没有
bagdiag lane ./segments/

# 7. 规划想不想绕
bagdiag avoid ./segments/
```

## 适用版本

面向 Autoware（Humble）+ Autoware。话题名按 `autoware_universe` 的命名，老版本如果话题不同，改 `bagdiag/path.py`、`ego.py` 顶部的常量即可。

## 不做的事

- 不连车、不发指令、不改参数 —— 纯离线读包
- 不替你下结论的边界：碰撞与否、体感好坏、场地是否允许，仍需现场判断
- 不做可视化渲染，只出数字

## License

MIT

## 贡献

话题名 / 阈值 / 口径都欢迎按你们车队实际情况提 PR。口径类的改动请在 PR 里写清楚"为什么原来的口径不对、实测反例是什么"，比改代码本身更重要。
