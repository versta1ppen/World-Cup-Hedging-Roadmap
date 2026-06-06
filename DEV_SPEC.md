<!-- Dev specification for Hedging Roadmap system, extending worldcup-predictor. -->
# Developer Specification (DEV_SPEC)

> 版本：0.1 — 开发规范文档
> 最后更新：2026-06-06
> 父项目：[worldcup-predictor](https://github.com/versta1ppen/worldcup-predictor) — 2026 世界杯逐场预测系统

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 核心特点](#2-核心特点)
- [3. 技术选型](#3-技术选型)
- [4. 测试方案](#4-测试方案)
- [5. 系统架构与模块设计](#5-系统架构与模块设计)
- [6. 项目排期](#6-项目排期)
- [7. 可扩展性与未来展望](#7-可扩展性与未来展望)
- [8. 各模块详细规格](#8-各模块详细规格)
- [9. 文件结构](#9-文件结构)
- [10. 附录](#10-附录)

---

## 1. 项目概述

### 1.1 目标

基于 worldcup-predictor 的 Monte Carlo 锦标赛模拟引擎，构建一个**对冲路线图（Hedging Roadmap）系统**，帮助用户在世界杯期间对"夺冠"类 futures 投注进行**逐轮对冲决策**——在赛前生成完整的对冲计划表，赛中根据实际赛果动态更新，赛后审计策略表现。

### 1.2 设计理念

> **核心定位：你的锦标赛投注风控官**
>
> 预测模型告诉你"谁更可能赢"，但对冲路线图回答的是另一个问题：**"你已经押了 Argentina $100 @ 8.5，现在它进了四强——你该不该在你的对手身上下注锁利？下多少？用哪种策略？"** 本系统不替代预测模型，而是在预测模型之上叠加一层**动态资金管理**。

#### 1️⃣ 预测与决策分离 (Prediction ↔ Decision Decoupling)

预测和决策是两个独立的问题，不应耦合：

- **预测层（父项目）**：Dixon-Coles + ELO + 市场锚定 → 每场比赛的概率估计
- **决策层（本项目）**：读取概率输出 + 用户持仓 → 计算最优对冲动作

这种分离意味着：
- 预测模型升级（如切换 xi 参数、增加新因子）不会影响对冲逻辑
- 对冲策略（等利润 / 部分对冲 / Kelly）独立可切换、可回测
- 两个层可以独立迭代

#### 2️⃣ 路径感知 (Path-Aware)

传统的"要不要对冲"决策只看当前轮次。本系统利用 Monte Carlo 的 5 万条模拟路径，做到：

- **条件概率**：P(Argentina 夺冠 | Argentina 已进四强) ≠ P(Argentina 夺冠)
- **对手分布**：四强可能碰 Brazil(35%) / France(28%) / England(22%) / ...
- **对手敏感性**：对 Brazil 需要对冲更多（因为更难赢），对弱队可以少对冲甚至不对冲

#### 3️⃣ 赛前规划 + 赛中执行 (Plan-then-Execute)

- **赛前**：基于 Monte Carlo 模拟生成完整路线图（R16 → QF → SF → Final），每轮列出可能对手及推荐对冲金额
- **赛中**：每轮比赛结束后，移除已淘汰的对手分支，更新剩余路径的条件概率，调整对冲计划
- **赛后**：审计实际执行的对冲策略，对比"如果不对冲"的利润，计算对冲效率

#### 4️⃣ 策略可选，不做建议 (Strategy-Agnostic)

不替用户做决定，而是展示每种策略的结果：

- **等利润对冲**：无论谁赢都赚一样多（最保守）
- **部分对冲（50%）**：锁一半利润，留一半敞口
- **Kelly 最优**：基于 log-wealth 最大化（最激进）
- **不对冲**：全程扛到底（对照组）

用户看到四种策略的情景分析后，自己做选择。

### 1.3 核心价值主张

| 痛点 | 解决方案 |
|------|---------|
| 赛前押了 futures，赛中不知道何时锁利 | 逐轮路线图：每轮告诉你"如果到这轮，该对冲多少" |
| 对冲金额凭感觉，没有量化依据 | 基于 Monte Carlo 条件概率 + Kelly 准则的精确计算 |
| 不同的对手需要不同的对冲策略 | 对手敏感性分析：对强对手多对冲，对弱对手少对冲 |
| 赛后不知道自己决策对不对 | 对冲效率审计：对比实际利润 vs 不对冲利润 |
| 赛中局势变化快，手动算不过来 | `hedge --update` 一键更新路线图 |

---

## 2. 核心特点

### 2.1 路线图引擎 (Roadmap Engine)

赛前为任意 futures 投注生成完整的逐轮对冲计划。

**输入**：
- 投注参数：球队、金额、赔率
- Monte Carlo 模拟输出：条件概率、对手分布
- 模型：Dixon-Coles 攻防参数（用于计算单场胜率）

**输出**：一份包含 5 轮（R32/R16/QF/SF/Final）的路线图 JSON，每轮包含：
- 到达此轮的概率
- 条件夺冠概率（到达此轮后最终夺冠的概率）
- 投注当前期望价值
- 可能对手列表（按碰面概率排序）
- 每种对手 × 四种策略的对冲金额和情景利润

### 2.2 多策略对冲计算 (Multi-Strategy Hedge Calculator)

内置四种对冲策略，每种给出完整的利润情景分析：

| 策略 | 公式 | 风险偏好 | 适用场景 |
|------|------|---------|---------|
| **等利润 (Equal Profit)** | `hedge = (bet × odds) / opp_odds` | 零风险 | 已经满意的利润，完全锁利 |
| **部分对冲 (Partial)** | `hedge = equal_profit × fraction` | 中性 | 想锁一部分，留一部分博更大收益 |
| **Kelly 最优** | `max_f E[ln(1 + r·f)]` | 激进 | 追求长期对数财富最大化 |
| **不对冲 (No Hedge)** | `hedge = 0` | 极大风险 | 全程扛到底（对照组） |

### 2.3 赛中动态更新 (Live Update)

每轮比赛结束后，`hedge --update` 命令：
1. 读取最新的赛果（哪些球队晋级/淘汰）
2. 用晋级球队的实际 ID 替换路线图中的"可能对手"分布
3. 重新运行 Monte Carlo（条件于已知赛果），更新条件概率
4. 移除已淘汰的分支，输出精简后的路线图

### 2.4 对手敏感性分析 (Opponent Sensitivity)

对每个可能对手，计算"对冲敏感度"：

```
敏感度 = |equal_profit_hedge(对手A) - equal_profit_hedge(对手B)| / bet_amount
```

高敏感度意味着"对手不同，对冲金额差异很大"→ 需要等对手确定后再做对冲决策。低敏感度意味着"无论对手是谁，对冲金额差不多"→ 可以提前行动。

### 2.5 对冲效率审计 (Hedge Efficiency Audit)

赛后评估对冲策略的实际表现：

| 指标 | 计算方式 |
|------|---------|
| **对冲效率** | (实际利润 − 不对冲利润) / 总对冲金额 |
| **后悔值** | max(不对冲可获利润, 完全对冲可获利润) − 实际利润 |
| **策略 Sharpe** | 多届赛事对冲利润的均值 / 标准差 |

---

## 3. 技术选型

### 3.1 与父项目的继承关系

本项目作为 worldcup-predictor 的**扩展模块**，深度依赖其现有能力：

| 能力 | 来源 | 对冲路线图如何使用 |
|------|------|-------------------|
| Dixon-Coles 模型 | `skill/model/dixon_coles.py` | 复用 `match_probs()` 计算单场 P(team beats opponent) |
| ELO 评级 | `skill/model/elo.py` | 参与攻防强度计算，间接影响对手胜率 |
| 市场赔率 | `skill/model/market.py` | 有实时赔率时优先用作对冲参考价（替代模型概率） |
| Monte Carlo | `skill/sim/montecarlo.py` | **核心依赖**：需扩展以输出条件概率和对手分布 |
| 情境上下文 | `skill/model/context.py` | 海拔/休息日调整自动体现在 λ 中，传递到对冲计算 |
| 数据加载 | `skill/helpers/data_loader.py` | 完全复用，对冲模块不需要新的外部数据 |
| CLI 框架 | `skill/helpers/cli.py` | 新增 `hedge` 子命令，复用模型加载流程 |
| 回测框架 | `skill/backtest/walkforward.py` | 新增对冲破回测，调用 walkforward 的模型拟合流程 |
| 静态仪表盘 | `site/index.html` | 新增「对冲路线图」面板，复用现有暗色主题和布局 |

### 3.2 新增模块

```
skill/hedge/
├── __init__.py           # 模块入口
├── strategies.py         # 四种对冲策略的纯函数实现
├── roadmap.py            # 路线图生成引擎
└── calculator.py         # 情景分析 + 利润计算
```

### 3.3 存储方案

| 数据类型 | 存储格式 | 位置 | 说明 |
|---------|---------|------|------|
| 路线图（赛前） | JSON | `reports/<date>/hedge_roadmap_<team>.json` | 每队一份 |
| 路线图（赛中更新） | JSON | `reports/<date>/hedge_roadmap_<team>_live.json` | 覆盖写入 |
| 对冲执行记录 | JSON | `reports/<date>/hedge_execution.json` | 用户实际执行的对冲动作 |
| 对冲审计报告 | JSON | `reports/<date>/hedge_audit.json` | 赛后生成 |
| 对冲回测结果 | JSON | `reports/backtests/hedge_backtest_<start>_<end>.json` | 历史回测 |

**JSON 设计原则**（继承父项目规范）：
- 人类可读：格式化缩进，方便调试
- 版本控制：含 `version` 字段，支持未来迁移
- 原子写入：先写 `.tmp` 文件，再重命名

### 3.4 配置管理

在父项目 `config.yaml` 中新增 `hedge` 段（或独立 `hedge_config.yaml`）：

```yaml
hedge:
  version: "1.0"

  # 默认对冲策略
  default_strategy: "equal_profit"   # equal_profit | partial | kelly | none

  # 部分对冲默认比例
  partial_fraction: 0.5              # 0.0 ~ 1.0

  # Kelly 设置
  kelly:
    fraction: 0.5                    # 全 Kelly / 半 Kelly / 四分之一 Kelly
    max_exposure: 0.25               # 单笔最大仓位（占总资金比例）

  # 路线图设置
  roadmap:
    min_opponent_prob: 0.02          # 对手概率低于此值不显示
    min_round_prob: 0.01             # 到达概率低于此值跳过该轮
    max_opponents_per_round: 5       # 每轮最多展示的对手数

  # 审计设置
  audit:
    benchmark_strategy: "none"       # 对照组策略
```

---

## 4. 测试方案

### 4.1 设计理念

对冲路线图系统的测试分为三层：**策略正确性测试**（数学验证）、**数据一致性测试**（与 Monte Carlo 输出一致）、**回测效果评估**（历史赛事表现）。

### 4.2 策略正确性测试

对每种对冲策略，用已知输入验证计算结果：

| 策略 | 测试场景 | 预期结果 |
|------|---------|---------|
| **equal_profit** | bet=100, odds=8.5, opp_odds=2.0 | hedge=425, 两队利润相同 |
| **equal_profit** | bet=100, odds=2.0, opp_odds=1.5 | hedge=133.33, 两队利润相同 |
| **partial** | bet=100, odds=8.5, opp_odds=2.0, frac=0.5 | hedge=212.5, 利润非对称 |
| **partial** | frac=0 | hedge=0（退化为不对冲） |
| **partial** | frac=1 | hedge=425（退化为等利润） |
| **kelly** | p_win=0.6, odds=2.0 | f > 0（正期望 → 下注） |
| **kelly** | p_win=0.4, odds=2.0 | f = 0（负期望 → 不下注） |
| **none** | 任意输入 | hedge=0 |

**验证方法**：
- 手动计算预期值
- 运行 `python -m pytest skill/hedge/` 进行单元测试
- 边界条件测试：odds=1.0（不可能）、bet=0、极端 odds

### 4.3 数据一致性测试

确保路线图输出与 Monte Carlo 模拟结果一致：

- **到达概率一致性**：路线图中的 `prob_reach` 必须等于 Monte Carlo 输出中 `reached[round][team] / n`
- **条件概率一致性**：`conditional_title_prob × prob_reach = P(title)` （允许浮点误差 < 0.001）
- **对手概率归一化**：每轮所有可能对手的 `prob_face` 之和 ≤ 1（允许部分对手因低于阈值被过滤）
- **情景利润自洽**：`if_team_wins.profit + hedge_amount` 和 `if_opponent_wins.profit + hedge_amount` 的交叉验证

**验证脚本**（Python）：

```python
def validate_roadmap_consistency(roadmap: dict, sim_output: dict) -> List[str]:
    """返回不一致项列表，空列表表示一致"""
    errors = []
    team = roadmap["team"]
    for round_data in roadmap["rounds"]:
        round_name = round_data["round"]
        # 到达概率一致性
        sim_prob = sim_output["reach_knockout_" + round_name].get(team, 0)
        if abs(round_data["prob_reach"] - sim_prob) > 0.001:
            errors.append(f"{round_name} prob_reach mismatch: "
                          f"{round_data['prob_reach']} vs sim {sim_prob}")
        # 条件概率一致性
        title_prob = sim_output["title_probability"].get(team, 0)
        implied_title = round_data["conditional_title_prob"] * round_data["prob_reach"]
        if abs(implied_title - title_prob) > 0.005:
            errors.append(f"{round_name} conditional_title inconsistent: "
                          f"implied {implied_title:.4f} vs title {title_prob:.4f}")
    return errors
```

### 4.4 回测效果评估

在历史大赛（WC 2010-2022、Euro 2008-2024）上回测四种对冲策略：

- **平均 ROI**：每届赛事对冲后的平均投资回报率
- **对冲效率**：(对冲后利润 − 不对冲利润) / 总对冲金额
- **最大回撤**：锦标赛期间资金曲线的最大回撤
- **胜率**：有正盈利的赛事占比
- **策略稳定性**：各策略 ROI 的标准差（越低越稳定）

**与父项目的回测纪律一致**：
- Walk-forward only：每届赛事的路线图只用 ≤ 该届开幕日的数据生成
- 策略参数不跨届优化（避免过拟合）
- 对照组：不对冲（裸持 futures 到期）

---

## 5. 系统架构与模块设计

### 5.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         用户交互层 (User Layer)                            │
│                                                                         │
│    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│    │  赛前：生成路线图  │  │  赛中：更新路线图  │  │  赛后：审计报告    │    │
│    │  hedge --team     │  │  hedge --update   │  │  hedge --audit    │    │
│    └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘    │
└─────────────┼─────────────────────┼─────────────────────┼───────────────┘
              │                     │                     │
              ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Hedge 执行层 (Hedge Layer)                         │
│                                                                         │
│    ┌──────────────────────────────────────────────────────────────┐    │
│    │                      roadmap.py                               │    │
│    │                                                               │    │
│    │  1. 读取 Monte Carlo 输出 (simulation.json)                    │    │
│    │  2. 读取用户投注参数 (team, amount, odds)                      │    │
│    │  3. 逐轮生成：可能对手 → 胜率 → 对冲金额 → 情景分析              │    │
│    │  4. 赛中更新：用实际赛果裁剪分支，重新计算                        │    │
│    └──────────────────────────────────────────────────────────────┘    │
│                                                                         │
│    ┌──────────────────────────┐  ┌──────────────────────────┐          │
│    │    strategies.py          │  │    calculator.py          │          │
│    │                          │  │                          │          │
│    │  equal_profit()          │  │  scenario_analysis()     │          │
│    │  partial()               │  │  profit_table()          │          │
│    │  kelly_hedge()           │  │  sensitivity_score()     │          │
│    │  no_hedge()              │  │  current_value()         │          │
│    └──────────────────────────┘  └──────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
              │                     │                     │
              ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              父项目数据层 (worldcup-predictor Data Layer)                   │
│                                                                         │
│    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│    │  montecarlo.py   │  │  dixon_coles.py  │  │  market.py        │    │
│    │  (模拟输出)       │  │  (单场胜率)       │  │  (实时赔率)        │    │
│    └──────────────────┘  └──────────────────┘  └──────────────────┘    │
│                                                                         │
│    ┌──────────────────┐  ┌──────────────────┐                          │
│    │  simulation.json │  │  predictions.json│                          │
│    │  (条件概率+对手)  │  │  (赛果数据)       │                          │
│    └──────────────────┘  └──────────────────┘                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 数据流图

#### 赛前路线图生成 (Pre-Tournament Roadmap)

```
用户输入 (team, bet_amount, bet_odds)
    │
    ▼
┌─────────────────┐
│  加载模型 + 数据  │
│  ├── DC fit      │
│  ├── 情境上下文   │
│  └── 阵容+伤缺   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Monte Carlo 模拟│
│  ├── 50k 次模拟  │
│  ├── 对手分布追踪 │  ← 新增
│  └── 条件概率追踪 │  ← 新增
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  路线图生成      │
│  ├── 逐轮遍历    │
│  ├── 对手筛选    │
│  ├── 策略计算    │
│  └── 情景分析    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  输出 JSON       │
│  hedge_roadmap_  │
│  <team>.json     │
└─────────────────┘
```

#### 赛中路线图更新 (Live Update)

```
用户触发 hedge --update
    │
    ▼
┌─────────────────┐
│  读取最新赛果    │
│  ├── 已完赛结果  │
│  ├── 晋级球队    │
│  └── 淘汰球队    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  裁剪路线图      │
│  ├── 移除淘汰对手│
│  ├── 固定已确定  │
│  │   的碰面      │
│  └── 收缩概率    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  条件化重模拟    │
│  ├── 只模拟剩余  │
│  │   赛程        │
│  └── 更新条件概率│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  输出更新后的    │
│  路线图 JSON     │
└─────────────────┘
```

### 5.3 模块边界

**模块间通信方式**：Hedge 模块通过 JSON 文件读取 Monte Carlo 输出，通过 Python 函数调用使用模型。

| 模块 | 读取 | 写入 | 说明 |
|------|------|------|------|
| **strategies.py** | 无（纯函数） | 无 | 输入参数 → 输出对冲金额 |
| **calculator.py** | 无（纯函数） | 无 | 输入对冲金额 → 输出情景利润 |
| **roadmap.py** | simulation.json, 用户输入 | hedge_roadmap_*.json | 生成/更新路线图 |
| **hedge_backtest.py** | 历史 simulation.json, 历史赛果 | hedge_backtest_*.json | 策略回测 |

**无循环依赖**：
- montecarlo → simulation.json → roadmap → hedge_roadmap.json → dashboard
- roadmap 不修改 montecarlo 的输出，只读取
- strategies / calculator 被 roadmap 单向调用

---

## 6. 项目排期

### 6.1 Phase 1: 核心计算 (P0)

**目标**：实现 Monte Carlo 扩展 + 四种对冲策略 + 赛前路线图生成。

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W1 | Monte Carlo 扩展：对手分布 + 条件概率追踪 | 修改后的 `montecarlo.py`，新增字段写入 `simulation.json` |
| W1 | strategies.py：四种策略纯函数 | 含单元测试 |
| W2 | calculator.py：情景分析 + 利润表 + 敏感度 | 含单元测试 |
| W2 | roadmap.py：赛前路线图生成 | CLI `hedge --team` 可用 |
| W3 | 数据一致性验证脚本 | `validate_roadmap_consistency.py` |

### 6.2 Phase 2: 赛中交互 (P1)

**目标**：赛中路线图更新 + CLI 完善 + 仪表盘面板。

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W4 | roadmap.py：赛中更新逻辑（裁剪分支 + 条件化重模拟） | `hedge --update` 可用 |
| W4 | CLI publish 集成（路线图打包进 data.json） | 仪表盘数据源就绪 |
| W5 | 仪表盘「对冲路线图」面板 | 交互式对冲计划查看 |
| W6 | 对手敏感性分析可视化 | 仪表盘敏感度热力图 |

### 6.3 Phase 3: 回测与审计 (P2)

**目标**：历史回测验证策略 + 赛后审计报告。

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W7 | hedge_backtest.py：历史赛事回测 | 四种策略的 ROI / 回撤 / Sharpe 对比 |
| W7 | hedge_audit.py：赛后审计报告生成 | `hedge --audit` 可用 |
| W8 | 策略推荐引擎（基于回测结果 + 用户风险偏好） | 仪表盘策略推荐卡片 |

### 6.4 Phase 4: 高级功能 (P3)

**目标**：多投注组合对冲 + 实时赔率联动。

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W9 | 组合对冲：同时持有多个 futures 的联合优化 | `hedge --portfolio` 支持多投注 |
| W10 | 实时赔率联动：用实时市场赔率替代模型概率作为对冲参考价 | 对接 market.py |
| W11+ | 自动对冲提醒（Telegram/Discord bot） | 赛中推送 |

---

## 7. 可扩展性与未来展望

### 7.1 多赛事支持

当前路线图硬编码了世界杯的 R32→R16→QF→SF→Final 赛制。通过抽象轮次结构，可以支持：

- **欧洲杯**：24 队 → 16 强 → 8 强 → 半决赛 → 决赛
- **欧冠淘汰赛**：16 强 → 8 强 → 半决赛 → 决赛
- **NBA 季后赛**：7 场 4 胜制系列赛（需要不同的对冲逻辑）

### 7.2 多投注类型支持

当前只支持"夺冠"futures。可扩展至：

- **晋级投注**："Argentina 进四强"的对冲路线图
- **金靴投注**："Mbappé 金靴"的对冲策略（对手进球后是否需要追加投注）
- **小组出线投注**：小组赛阶段的对冲路线图

### 7.3 实时赔率联动

赛中整合实时博彩赔率 API：

- 当对手的实际赔率比模型预测更有利于对冲时（赔率更高 → 对冲成本更低），自动标记为"对冲窗口"
- 监控赔率异动，在对冲成本最低的时刻推送提醒

### 7.4 组合优化

当用户同时持有多个 futures 投注时（如"Argentina 夺冠"+"Mbappé 金靴"+"Brazil 进决赛"），优化问题从"单投注对冲"变为：

- 考虑投注之间的相关性（Argentina 夺冠和 Brazil 进决赛在 knockout 阶段互斥）
- 联合优化所有投注的对冲仓位，最小化总风险敞口

---

## 8. 各模块详细规格

### 8.1 Monte Carlo 扩展模块

#### 8.1.1 新增追踪数据结构

在 `montecarlo.run()` 内部新增以下 numpy 数组：

```python
# 每轮对手碰面矩阵 (nt × nt, 对称)
opponent_faced = {
    "R32": np.zeros((nt, nt), dtype=np.int32),
    "R16": np.zeros((nt, nt), dtype=np.int32),
    "QF":  np.zeros((nt, nt), dtype=np.int32),
    "SF":  np.zeros((nt, nt), dtype=np.int32),
    "final": np.zeros((nt, nt), dtype=np.int32),
}

# 每轮参赛者引用（用于赛后条件概率计算）
round_participants = {}  # round_name → (n, k) array of team IDs

# 每轮条件夺冠追踪 (nt,)
round_title = {
    "R32": np.zeros(nt, dtype=np.int32),
    "R16": np.zeros(nt, dtype=np.int32),
    "QF":  np.zeros(nt, dtype=np.int32),
    "SF":  np.zeros(nt, dtype=np.int32),
    "final": np.zeros(nt, dtype=np.int32),
}
```

#### 8.1.2 修改 `_play()` 内嵌函数

```
新增参数 round_name=None。

在返回 winner 之前，追加对手追踪：

    np.add.at(opponent_faced[round_name], (home.ravel(), away.ravel()), 1)
    np.add.at(opponent_faced[round_name], (away.ravel(), home.ravel()), 1)
```

#### 8.1.3 各淘汰赛轮次的调用改造

```
R32: w32 = _play(home16, away16, "R32")
     记录 round_participants["R32"] = [home16, away16] (concat)
R16: w16 = _play(w32[:, a], w32[:, b], "R16")
     记录 round_participants["R16"] = w32 pairs
QF:  qf  = _play(w16[:, a], w16[:, b], "QF")
     记录 round_participants["QF"] = w16 pairs
SF:  sf  = _play(qf[:, a], qf[:, b], "SF")
     记录 round_participants["SF"] = qf pairs
F:   champ = _play(sf[:, [0]], sf[:, [1]], "final")
     记录 round_participants["final"] = sf pairs
```

#### 8.1.4 冠军确定后计算条件概率

```python
for round_name, participants in round_participants.items():
    is_champ = (participants == champ)          # broadcast (n, k)
    np.add.at(round_title[round_name], participants.ravel(), is_champ.ravel())
```

#### 8.1.5 新增返回字段

```python
# 对手分布
out["opponent_distribution"] = {
    round_name: {
        team: {opponent: prob for opponent, prob in sorted_probs if prob > 0.01}
        for team in teams if reached[round_name][tid[team]] > 0
    }
    for round_name in ["R32", "R16", "QF", "SF", "final"]
}

# 条件夺冠概率
out["conditional_title_prob"] = {
    round_name: {
        team: round(float(round_title[round_name][tid[team]]) / reached_count, 4)
        for team in teams if (reached_count := reached[round_name][tid[team]]) > 0
    }
    for round_name in ["R32", "R16", "QF", "SF", "final"]
}
```

### 8.2 对冲策略模块 (strategies.py)

#### 8.2.1 等利润对冲

```python
def equal_profit(bet_amount: float, bet_odds: float, opponent_odds: float) -> float:
    """
    计算等利润对冲金额。

    Args:
        bet_amount: 原始投注金额
        bet_odds: 原始投注的十进制赔率
        opponent_odds: 对手的十进制赔率（用于对冲的投注选项）

    Returns:
        对冲金额。如果 opponent_odds <= 1.0，返回 0（无效赔率）。

    Formula:
        hedge = (bet_amount × bet_odds) / opponent_odds

    Verification:
        如果原队赢: profit = bet_amount × (bet_odds - 1) - hedge
        如果对手赢: profit = hedge × (opponent_odds - 1) - bet_amount
        两者相等当 hedge = (bet × odds) / opp_odds
    """
    if opponent_odds <= 1.0:
        return 0.0
    return (bet_amount * bet_odds) / opponent_odds
```

#### 8.2.2 部分对冲

```python
def partial(bet_amount: float, bet_odds: float, opponent_odds: float,
            fraction: float = 0.5) -> float:
    """
    部分对冲：只对冲 fraction 比例的风险。

    Args:
        fraction: 0.0 = 不对冲, 1.0 = 等利润对冲
    """
    full = equal_profit(bet_amount, bet_odds, opponent_odds)
    return full * max(0.0, min(1.0, fraction))
```

#### 8.2.3 Kelly 最优对冲

```python
def kelly_hedge(bet_amount: float, bet_odds: float, opponent_odds: float,
                p_team_wins: float, kelly_fraction: float = 0.5) -> float:
    """
    基于对数财富期望最大化的 Kelly 对冲。

    将现有 futures 持仓视为"已持有 asset"，对冲视为"做空对手"。
    最优对冲比例 f* 通过求解 d/df E[log(wealth)] = 0 得到。

    Args:
        p_team_wins: 模型估计的原队胜率 P(原队胜 | 两队碰面)
        kelly_fraction: Kelly 分数（0.5 = 半 Kelly，更保守）
    """
    p_opp_wins = 1.0 - p_team_wins
    # Kelly 公式：f* = (p_opp * opp_odds - p_team) / (opp_odds - 1)
    b = opponent_odds - 1.0
    if b <= 0:
        return 0.0
    f_star = (p_opp_wins * opponent_odds - p_team_wins) / b
    f_star = max(0.0, f_star)  # 只在正期望时对冲
    return bet_amount * f_star * kelly_fraction
```

#### 8.2.4 不对冲（对照组）

```python
def no_hedge(bet_amount: float, **kwargs) -> float:
    """不对冲，作为策略对照组。"""
    return 0.0
```

### 8.3 情景分析模块 (calculator.py)

#### 8.3.1 情景利润计算

```python
def scenario_profit(bet_amount: float, bet_odds: float,
                    hedge_amount: float, opponent_odds: float) -> dict:
    """
    计算两种情景下的利润。

    Returns:
        {
            "if_team_wins": {"profit": float, "roi_pct": float},
            "if_opponent_wins": {"profit": float, "roi_pct": float},
            "guaranteed": float,   # min(两个 profit)
            "max_upside": float,   # max(两个 profit)
            "is_risk_free": bool,  # guaranteed > 0
        }
    """
    total_invested = bet_amount + hedge_amount
    if_team_wins = bet_amount * bet_odds - total_invested
    if_opp_wins = hedge_amount * opponent_odds - total_invested
    return {
        "if_team_wins": {
            "profit": round(if_team_wins, 2),
            "roi_pct": round(if_team_wins / total_invested * 100, 1),
        },
        "if_opponent_wins": {
            "profit": round(if_opp_wins, 2),
            "roi_pct": round(if_opp_wins / total_invested * 100, 1),
        },
        "guaranteed": round(min(if_team_wins, if_opp_wins), 2),
        "max_upside": round(max(if_team_wins, if_opp_wins), 2),
        "is_risk_free": min(if_team_wins, if_opp_wins) > 0,
    }
```

#### 8.3.2 投注当前价值估算

```python
def current_value(bet_amount: float, bet_odds: float,
                  conditional_title_prob: float) -> float:
    """
    估算 futures 投注的当前期望价值。

    Formula:
        EV = bet_amount × bet_odds × P(title | current_state) - bet_amount
    """
    expected_payout = bet_amount * bet_odds * conditional_title_prob
    return round(expected_payout, 2)
```

#### 8.3.3 对手敏感度评分

```python
def sensitivity_score(opponents: list[dict]) -> float:
    """
    计算对手敏感度：不同对手的对冲金额差异有多大？

    高敏感度 → 建议等对手确定后再对冲
    低敏感度 → 可以提前行动

    Returns:
        0.0 ~ 1.0，越高越敏感
    """
    if len(opponents) < 2:
        return 0.0
    hedge_amounts = [o["strategies"]["equal_profit"]["hedge_amount"] for o in opponents]
    spread = max(hedge_amounts) - min(hedge_amounts)
    mean_val = sum(hedge_amounts) / len(hedge_amounts)
    if mean_val == 0:
        return 0.0
    return round(min(1.0, spread / mean_val), 3)
```

### 8.4 路线图引擎 (roadmap.py)

#### 8.4.1 赛前路线图生成

```python
def generate_roadmap(
    team: str,
    bet_amount: float,
    bet_odds: float,
    sim_output: dict,
    model,                       # DCModel instance
    config: dict | None = None,  # hedge config
) -> dict:
    """
    为指定 futures 投注生成完整对冲路线图。

    Algorithm:
        for each round in [R32, R16, QF, SF, Final]:
            1. 查 sim_output → prob_reach, conditional_title_prob
            2. 如果 prob_reach < min_round_prob → 跳过
            3. 查 sim_output → opponent_distribution[round][team]
            4. 对每个对手（按 prob_face 排序，取前 max_opponents）：
               a. 用 model.match_probs → P(team beats opponent)
               b. opp_odds = 1 / P(opponent beats team)  (或市场赔率如果可用)
               c. 计算四种策略的对冲金额
               d. 生成情景利润表
            5. 计算对手敏感度

    Returns:
        HedgeRoadmap JSON (见 8.4.3 输出格式)
    """
```

#### 8.4.2 赛中路线图更新

```python
def update_roadmap(
    roadmap: dict,
    completed_results: list[dict],  # [{round, team1, team2, winner}, ...]
    sim_output: dict,               # 更新后的 simulation（条件于赛果）
    model,
) -> dict:
    """
    根据实际赛果更新路线图。

    Algorithm:
        1. 对每个已完赛的轮次：
           a. 标记该轮为 "completed"
           b. 记录实际碰面的对手和结果
           c. 移除所有未发生的对手分支
        2. 对未进行的轮次：
           a. 移除已被淘汰的对手（从 opponent_distribution 中过滤）
           b. 重新归一化剩余对手的概率
           c. 用更新后的 sim_output 更新 conditional_title_prob
        3. 重新计算剩余轮次的对冲金额和情景分析

    Returns:
        更新后的 HedgeRoadmap JSON
    """
```

#### 8.4.3 路线图 JSON 输出格式

```json
{
  "version": "1.0",
  "generated_at": "2026-06-06T00:00:00Z",
  "updated_at": null,
  "team": "Argentina",
  "bet": {
    "amount": 100.0,
    "odds": 8.5,
    "potential_payout": 850.0
  },
  "status": "pre_tournament",
  "rounds": [
    {
      "round": "R16",
      "status": "pending",
      "prob_reach": 0.8912,
      "conditional_title_prob": 0.2521,
      "current_value": 214.29,
      "sensitivity": 0.42,
      "note": "中敏感度 — 可等对手确定后执行",
      "opponents": [
        {
          "team": "Ecuador",
          "prob_face": 0.1823,
          "p_team_wins": 0.7215,
          "opponent_odds": 3.59,
          "note": "模型估计 fair odds = 1/P(opponent wins)",
          "strategies": {
            "equal_profit": {
              "hedge_amount": 236.77,
              "scenario": {
                "if_team_wins": {"profit": 513.23, "roi_pct": 152.4},
                "if_opponent_wins": {"profit": 513.23, "roi_pct": 152.4},
                "guaranteed": 513.23,
                "is_risk_free": true
              }
            },
            "partial_50": {
              "hedge_amount": 118.38,
              "scenario": {
                "if_team_wins": {"profit": 631.62, "roi_pct": 289.3},
                "if_opponent_wins": {"profit": 206.72, "roi_pct": 94.7},
                "guaranteed": 206.72,
                "is_risk_free": true
              }
            },
            "kelly_half": {
              "hedge_amount": 45.62,
              "scenario": {
                "if_team_wins": {"profit": 704.38, "roi_pct": 483.7},
                "if_opponent_wins": {"profit": -27.31, "roi_pct": -18.8},
                "guaranteed": -27.31,
                "is_risk_free": false
              }
            },
            "no_hedge": {
              "hedge_amount": 0.0,
              "scenario": {
                "if_team_wins": {"profit": 750.00, "roi_pct": 750.0},
                "if_opponent_wins": {"profit": -100.00, "roi_pct": -100.0},
                "guaranteed": -100.00,
                "is_risk_free": false
              }
            }
          }
        }
      ]
    }
  ]
}
```

### 8.5 CLI 模块

#### 8.5.1 新增子命令

```bash
# 赛前：为指定投注生成路线图
python -m skill.helpers.cli hedge --team Argentina --amount 100 --odds 8.5

# 赛前：为所有 48 队批量生成（默认 odds 从市场数据读取）
python -m skill.helpers.cli hedge --all

# 赛中：根据最新赛果更新指定路线图
python -m skill.helpers.cli hedge --update --team Argentina --date 2026-06-20

# 赛后：生成审计报告
python -m skill.helpers.cli hedge --audit --team Argentina

# 指定策略覆盖默认策略
python -m skill.helpers.cli hedge --team Argentina --amount 100 --odds 8.5 \
    --strategy partial --fraction 0.5
```

#### 8.5.2 CLI 参数定义

```python
ph = sub.add_parser("hedge")
ph.add_argument("--team", default=None,
                help="投注的球队名称")
ph.add_argument("--amount", type=float, default=100.0,
                help="投注金额")
ph.add_argument("--odds", type=float, default=None,
                help="投注时的十进制赔率（不提供则尝试从市场数据读取）")
ph.add_argument("--all", action="store_true",
                help="为所有球队生成路线图")
ph.add_argument("--update", action="store_true",
                help="赛中更新已有路线图")
ph.add_argument("--audit", action="store_true",
                help="赛后生成审计报告")
ph.add_argument("--date", default=None,
                help="更新/审计的参考日期")
ph.add_argument("--strategy", default="equal_profit",
                choices=["equal_profit", "partial", "kelly", "none"],
                help="默认策略")
ph.add_argument("--fraction", type=float, default=0.5,
                help="部分对冲比例或 Kelly 分数")
ph.set_defaults(func=_cmd_hedge)
```

### 8.6 仪表盘面板

#### 8.6.1 面板布局

```
┌─────────────────────────────────────────────────────────────┐
│  🛡️ 对冲路线图                              [球队选择 ▼]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  投注：Argentina 夺冠  $100 @ 8.5  期望回报：$850            │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ R16      │  │ QF       │  │ SF       │  │ Final    │   │
│  │ 到达 89% │─▶│ 到达 72% │─▶│ 到达 45% │─▶│ 到达 22% │   │
│  │          │  │          │  │          │  │          │   │
│  │ 可能对手 │  │ 可能对手 │  │ 可能对手 │  │ 可能对手 │   │
│  │ Ecuador  │  │ Brazil   │  │ France   │  │ England  │   │
│  │  对冲$237│  │  对冲$312│  │  对冲$405│  │  对冲$520│   │
│  │          │  │          │  │          │  │          │   │
│  │ [详情]   │  │ [详情]   │  │ [详情]   │  │ [详情]   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                             │
│  策略切换：[等利润] [部分50%] [Kelly半仓] [不对冲]           │
│                                                             │
│  对手敏感度：                                               │
│  R16 ████████░░ 低  — 可提前行动                            │
│  SF  ██████████████████░░ 高  — 建议等对手确定              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 8.6.2 交互行为

- **球队选择器**：下拉搜索 48 支球队，选择后加载对应路线图
- **策略切换按钮**：切换后所有卡片中的对冲金额和利润数字同步更新
- **卡片点击**：展开该轮详情（全部对手列表 + 每种策略的情景对比表）
- **敏感度指示条**：颜色从绿（低）到红（高），hover 显示具体建议
- **赛中模式**：已完成的轮次卡片变灰 + ✅ 标记，显示实际对手和结果

---

## 9. 文件结构

### 9.1 完整目录结构

```
worldcup-predictor/                    # 父项目（保持不变）
│
├── skill/
│   ├── model/                         # 父项目模型层（不改动）
│   ├── sim/
│   │   └── montecarlo.py              # ✦ 修改：新增对手追踪 + 条件概率
│   ├── backtest/
│   │   └── hedge_backtest.py          # ✦ 新增：对冲策略回测
│   ├── helpers/
│   │   └── cli.py                     # ✦ 修改：新增 hedge 子命令
│   └── hedge/                         # ✦ 新增：对冲模块
│       ├── __init__.py
│       ├── strategies.py              # 四种对冲策略
│       ├── calculator.py              # 情景分析 + 利润计算
│       └── roadmap.py                 # 路线图生成 + 更新
│
├── site/
│   └── index.html                     # ✦ 修改：新增对冲路线图面板
│
├── reports/
│   ├── <date>/
│   │   ├── hedge_roadmap_<team>.json          # 赛前路线图
│   │   ├── hedge_roadmap_<team>_live.json     # 赛中更新
│   │   ├── hedge_execution.json               # 执行记录
│   │   └── hedge_audit.json                   # 审计报告
│   └── backtests/
│       └── hedge_backtest_<start>_<end>.json  # 回测结果
│
└── tests/
    └── hedge/
        ├── test_strategies.py         # 策略数学正确性测试
        ├── test_calculator.py         # 情景分析测试
        └── test_consistency.py        # 数据一致性验证
```

### 9.2 共享脚本规范

**Python 脚本设计原则**（继承父项目规范）：
- 纯函数优先：strategies.py 和 calculator.py 全部纯函数，输入确定 → 输出确定
- 文件操作原子化：路线图写入先写 `.tmp`，再重命名
- 异常处理：所有文件操作包裹 try-except
- 日志输出 stderr：不污染 stdout，兼容管道
- 类型注解：所有公共函数使用 type hints

---

## 10. 附录

### 10.1 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 路线图文件名 | `hedge_roadmap_{team_slug}.json` | `hedge_roadmap_argentina.json` |
| 团队 slug | 英文小写，空格换下划线 | `united_states`, `south_korea` |
| 策略名称 | snake_case | `equal_profit`, `partial`, `kelly_hedge`, `no_hedge` |
| 轮次名称 | 大写缩写 | `R32`, `R16`, `QF`, `SF`, `Final` |
| CLI 子命令 | 小写英文 | `hedge` |
| 配置段 | snake_case | `hedge.roadmap.min_opponent_prob` |

### 10.2 JSON 字段规范

**路线图根字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | string | 是 | 数据格式版本 |
| `generated_at` | string | 是 | 生成时间 (ISO 8601) |
| `updated_at` | string/null | 否 | 最后更新时间 |
| `team` | string | 是 | 投注球队名称 |
| `bet` | object | 是 | 投注参数 |
| `status` | string | 是 | `pre_tournament` / `in_progress` / `completed` |
| `rounds` | array | 是 | 逐轮路线图 |

**bet 对象字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `amount` | float | 投注金额 |
| `odds` | float | 十进制赔率 |
| `potential_payout` | float | 最大可能回报 |

**round 对象字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `round` | string | 轮次名称 |
| `status` | string | `pending` / `completed` / `skipped` |
| `prob_reach` | float | 到达此轮的概率 |
| `conditional_title_prob` | float | 到达此轮后最终夺冠的概率 |
| `current_value` | float | 投注当前期望价值 |
| `sensitivity` | float | 对手敏感度 (0-1) |
| `note` | string | 人类可读的建议 |
| `opponents` | array | 可能对手列表 |
| `actual_opponent` | string/null | 实际碰面的对手（仅 completed 轮次） |

**opponent 对象字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `team` | string | 对手名称 |
| `prob_face` | float | 碰面概率 |
| `p_team_wins` | float | 模型估计的 P(你的队胜) |
| `opponent_odds` | float | 对手的十进制赔率（fair odds 或市场赔率） |
| `note` | string | 赔率来源说明 |
| `strategies` | object | 各策略的对冲方案 |

### 10.3 敏感度分级

| 敏感度 | 级别 | 颜色 | 建议行动 |
|--------|------|------|---------|
| 0.00 – 0.25 | 低 | 🟢 绿色 | 可提前行动，对手差异不大 |
| 0.25 – 0.50 | 中 | 🟡 黄色 | 可等对手缩小范围后行动 |
| 0.50 – 0.75 | 高 | 🟠 橙色 | 建议等对手确定后再对冲 |
| 0.75 – 1.00 | 极高 | 🔴 红色 | 必须等对手确定，否则风险极大 |

### 10.4 自检清单 (Quality Checklist)

每次修改或发布前，运行自检：

**计算正确性**：
- [ ] `equal_profit` 对冲后两个方向的利润相等（误差 < $0.01）
- [ ] `partial(frac=0)` 等于 `no_hedge`
- [ ] `partial(frac=1)` 等于 `equal_profit`
- [ ] `kelly_hedge` 在正期望时 f* > 0，负期望时 f* = 0
- [ ] `scenario_profit.guaranteed` ≤ 两个方向的利润

**数据一致性**：
- [ ] 路线图 `prob_reach` 与 simulation.json 一致
- [ ] `conditional_title_prob × prob_reach` 与 `title_probability` 自洽
- [ ] 每轮对手 `prob_face` 之和 ≤ 1.0

**Monte Carlo 集成**：
- [ ] 对手追踪不影响原有概率输出（回归测试）
- [ ] 条件概率在所有轮次自洽
- [ ] 性能影响 < 5%（50k 模拟耗时对比）

**仪表盘**：
- [ ] 球队选择器包含全部 48 队
- [ ] 策略切换后数字实时更新
- [ ] 赛中模式正确显示已完成轮次
- [ ] 移动端布局正常

---

> **文档版本历史**
>
> | 版本 | 日期 | 说明 |
> |------|------|------|
> | 0.1 | 2026-06-06 | 初始版本，完整对冲路线图开发规范 |