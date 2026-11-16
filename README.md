# bagdiag

**MCAP 录包离线诊断工具** —— 一条命令回答"这段包到底停没停住、刹得猛不猛、跟丢了没有、变没变道、有没有误触发 MRM"。

面向自动驾驶回归测试：不连车、不依赖运行中的 ROS、纯离线读包。

```
$ bagdiag stop ./sample_11205.mcap
最高车速 31.1 km/h   停稳: 是
减速 35.6 m / 11.88 s   峰值 -2.52 / 平均 -1.2 m/s²
停稳时最近目标 9.0 m   MRM NORMAL   AEB False
判定: PASS
```

## 为什么需要它

回归测试一天产出几十甚至上百个短分片，每个都要人看。难点其实不是"看不过来"，而是**两个人看同一个包会得出相反的结论** —— 因为口径没定下来：

| 同一个问题 | 直觉做法 | 实际会错成什么样 |
|---|---|---|
| 变没变道 | 用初始航向投影算横移 | 弯道能放大出十几米的假值；改成分段航向积分，又把转向吸收掉算成接近 0（真值约一个车道宽） |
| 有没有漏检 | 位置 + 尺寸双匹配 | 类别判错的目标被算成漏检，漏检率被虚高一个数量级 |
| 刹得猛不猛 | 看控制指令峰值 | 指令会出现短时尖峰，但车速其实是十几秒平缓降完、平均不到 −0.5 m/s²，属正常停车 |
| 轨迹是不是卡了 | 点数 ≥ 100 | 新版规划器输出**固定点数**，永远"不达标"，把正常规划误判成卡死 |
| 有没有漏掉场景 | 看分片号连不连续 | 分片号连续（101→102），但时间戳可能断层半小时以上，那段测试根本没录到 |

这个工具就是把这些口径**固化成代码**，让同一个包在任何人手里都得出同一个数。

## 效果

- 单包诊断 **< 1 秒**（十几秒的分片、约 5 万条消息）
- **几百个分片**批量跑完约 **2 分钟**，输出可直接接 CI / 平台
- 上面 5 条口径，每条都对应一个**实测反例**（下方「口径说明」逐条写明了错误做法、错误数值、正确数值）

## 安装

```bash
git clone https://github.com/<your-name>/bagdiag-toolkit.git
cd bagdiag-toolkit
pip install -e .
```

依赖只有 `mcap`、`mcap-ros2-support`、`zstandard`。支持 `.mcap` 和整文件 zstd 压缩的 `.mcap.zst`（自动解到临时目录）。

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
| `cat` | **检测↔跟踪 类别一致性配对**（逐帧换算到 map 后配对，区分"类别不一致"与"跟踪丢失"） |
| `turn` | **转向灯 / 控制模式一致性**（灯状态 vs 系统指令 vs 自动驾驶模式） |
| `gap` | **分片连续性**：录制中断、短分片、片号跳号 |
| `rosout` | 日志检索（bag 内 `/rosout` 或车机 `1_stdout.log`） |

`path` 可以是单个 `.mcap`，也可以是目录（批量跑）。

加 `--json` 输出结构化结果：

```bash
bagdiag --json stop ./segments/ > stop.json
```

## 口径说明（重要）

这些口径是踩过坑之后定下来的，用错会得出完全相反的结论。

### 1. 坐标系

```
/perception/object_recognition/detection/objects             base_link 帧
/perception/object_recognition/detection/bevfusion/objects   base_link 帧
/perception/object_recognition/tracking/objects              map 帧
/perception/object_recognition/objects                       map 帧
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

### 6. 类别不一致 ≠ 跟踪丢失

检测层和跟踪层**都有**同一位置的目标，但类别不同 —— 这不是漏检，也不是跟踪丢失。
必须用 `cat` 逐帧配对确认（检测是 base_link，跟踪是 map，**不换算会得到一堆假异常**）：

```bash
bagdiag cat ./segments/
```

输出会给出「检测 X → 跟踪 Y」的配对矩阵。典型实测：

```
检测 CONSTRUCTION_VEHICLE -> 跟踪 TRAILER      81 帧   <-- 不一致
检测 CAR                  -> 跟踪 CONSTRUCTION 303 帧  <-- 反向不一致
```

两个方向都出现过，说明跟踪层的类别不是简单照抄检测输入，需要单独定位。

### 7. 判"急刹"看车速曲线，不看指令峰值

`/control/command/control_cmd` 里可能出现短时尖峰，但实际车速是缓慢
下降的（实测二十几秒从三十几降到 0，平均不到 −0.5 m/s²，属正常平缓停车）。
**用指令峰值判急刹会误报**，要看 `/localization/kinematic_state` 的速度曲线。

### 8. 判"轨迹甩"看方向盘，不看路径弯曲量

路径在变道时会正常横弯 3.5 m（一个车道宽），按"路径横向散布"判摆动会把正常变道
误判成震荡。可靠的判据是：

- 方向盘 1 秒内变化 > 10°（实测异常帧明显超阈值，正常帧远低于它）
- 相邻帧路径跳变 > 1 m（实测异常帧可达数米）

### 9. 录制中断不会体现在片号上

分片号是连续的（101 → 102），但时间戳可能断层。实测一天内会有多次中断，
最长可达半小时以上，中断时段的分片根本不存在，**对应时间点的测试场景完全无法分析**：

```bash
bagdiag gap ./segments/                 # 目录
bagdiag gap ./session.info               # 会话 info
```

## 典型用法

```bash
# 1. 先看包完整不完整
bagdiag info ./segments/

# 2. 停障类场景
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

## scripts/ —— 实战分析脚本

`bagdiag` 是把常用判定固化成包；`scripts/` 里是没进包的、按现场问题临时写的分析脚本，
每个都能单独跑，用来回答具体问题。

| 脚本 | 用法 | 回答什么 |
|---|---|---|
| `话题体检.py` | `python3 scripts/话题体检.py <bag.mcap>` | 各话题帧数、最长时间断档、频率是否正常 |
| `目标统计.py` | `python3 scripts/目标统计.py <bag.mcap>` | 逐帧目标数、类别分布、跟踪 ID 连续性 |
| `健康体检.py` | `python3 scripts/健康体检.py <health.json>` | 读 diag JSON，打印各模块得分与最低项 |
| `批量体检.py` | `python3 scripts/批量体检.py <目录>` | 批量跑 diag health，按缺失/频率异常排序，落盘 JSON |
| `bag.py` | import 用 | mcap 读取与话题抽取（消息解码、时间窗裁剪） |
| `text_log.py` | import 用 | 文本日志按级别统计、按关键词聚类 |

依赖同主包（`mcap` + `mcap-ros2-support`）。

## 适用版本

面向 Autoware（Humble）。话题名按 `autoware_universe` 的命名，老版本如果话题不同，改 `bagdiag/path.py`、`ego.py` 顶部的常量即可。

## 不做的事

- 不连车、不发指令、不改参数 —— 纯离线读包
- 不替你下结论的边界：碰撞与否、体感好坏、场地是否允许，仍需现场判断
- 不做可视化渲染，只出数字

## License

MIT

## 贡献

话题名 / 阈值 / 口径都欢迎按你们车队实际情况提 PR。口径类的改动请在 PR 里写清楚"为什么原来的口径不对、实测反例是什么"，比改代码本身更重要。
