# 流体/结构数值模拟软件自动测试系统方案

## 建设目标

建设一个面向数值模拟软件的自动测试系统，使同一物理案例能够在多个求解器内核及其不同版本上自动准备、执行、采集、判定和对比。

系统应回答三类问题：

1. **差异量化**：计算量相对参考解或基准版本的偏差是多少；
2. **一致性**：不同内核、不同版本的监控量和场结果是否具有可解释的一致性；
3. **运行稳定性与性能**：计算是否正常完成，是否出现崩溃、超时、性能退化或结果漂移；收敛可靠性由用户结合完整曲线判断。

本系统不是用某一求解器的输入格式替代其他格式，而是在其上建立统一的案例语义、执行接口和结果协议。

## 设计原则

- **规范案例与原生案例分离**：公共物理定义、网格、监控项和参考比较定义放在规范层；每个求解器保留自己的原生配置。
- **求解器与版本双重隔离**：不能假定同一内核不同版本的命令、默认值和文件格式完全兼容。
- **统一网格资产**：每个案例只维护一个 `.cgns`、`.msh` 网格文件或 `polyMesh` 文件夹；多域信息及接口配对共同保存在该资产中，各求解器的目标格式均在启动前由它转换生成。
- **显式而非默认**：湍流模型、离散格式、松弛、精度、初始化、参考值、停止条件等尽量显式声明，避免版本默认值变化造成伪回归。
- **最小化结果归档**：运行期原生结果只用于标准化和验证，不长期归档；监控曲线保存为 CSV，流场仅保存工况 `references` 实际用于精度验证的物理量及域，覆盖求解器实际输出的所有时刻，矢量包含全部分量和模长。
- **可追溯和可复现**：记录代码版本、求解器版本、输入文件哈希、CPU/内存等计算资源。
- **数值等价优先于参数名相同**：跨内核对比必须描述参数映射和不可等价项，不能只比较界面选项名称。

## 总体架构

### 核心模块

| 模块 | 职责 |
|---|---|
| 案例注册表 | 发现案例、校验清单、管理标签和依赖 |
| 求解器注册表 | 自动发现 Adapter，并将其固有版本/能力与本机部署配置绑定 |
| 案例物化器 | 将公共参数、统一网格资产和内核参数文件生成独立运行目录 |
| 网格服务 | 转换格式，输出网格指纹和质量/拓扑核验报告 |
| 适配器 | 准备输入、构造命令、解析状态、采集结果 |
| 执行器 | 本地、容器或调度器运行；超时、取消、资源和日志管理 |
| 标准化器 | 将不同内核输出转换为统一单位和统一列定义 |
| 分析器 | 提取监控值，执行参考解/基线比较和性能比较，不判定是否收敛 |
| 报告器 | 生成机器可读结论和人类可读报告 |
| 产物库 | 保存输入快照、日志、结果、图表和追溯元数据 |

## 仓库目录与机器配置


### 目录结构

```text
repository/
├── config.yaml                       # 本机部署配置，不提交代码仓库
├── cases/                            # 案例库
│   └── cylinder-2d/
│       ├── README.md                 # 案例描述
│       ├── case.yaml                 # 规范案例清单
│       ├── mesh.cgns                 # 或 mesh.msh、polyMesh/，仅保留一个网格资产
│       ├── conditions/               # 每个文件定义一个具体工况，给 case.yaml 中定义的变量赋值
│       │   ├── Re=100.yaml
│       │   └── Re=1000.yaml
│       ├── references/               # 论文、实验数据和解析公式说明等参考解原始资料
│       │   ├── cylinder-experiment.pdf
│       │   └── manufactured-solution.md
│       └── templates/                # 不同求解器内核的模板文件，引用 case.yaml 中定义的变量
│           ├── OpenFOAM/
│           │   ├── template.yaml
│           │   ├── 0/
│           │   ├── constant/
│           │   └── system/
│           ├── OpenFOAM-v2312/       # 与 OpenFOAM/ 同级的模板变体
│           │   ├── template.yaml
│           │   └── system/
│           ├── Fluent/
│           │   ├── template.yaml
│           │   └── setup.jou
│           ├── StarCCM/
│           │   ├── template.yaml
│           │   └── setup.java
│           └── AICFD/
│               ├── template.yaml
│               └── setup.json
├── solvers/                          # 求解器适配器
│   ├── __init__.py
│   ├── base.py                       # 抽象基类
│   ├── registry.py                   # 求解器名称 + 实际版本 → 最近的 Adapter 变更点
│   ├── exceptions.py                 # 统一异常类型
│   ├── models.py                     # 运行上下文及阶段结果模型
│   ├── OpenFOAM/
│   │   ├── __init__.py
│   │   ├── adapter.py                # 公共实现
│   │   └── versions/                 # 仅记录行为变更点
│   │       ├── __init__.py
│   │       ├── v2312.py
│   │       └── v2406.py
│   ├── Fluent/
│   │   ├── __init__.py
│   │   └── adapter.py
│   ├── StarCCM/
│   │   ├── __init__.py
│   │   └── adapter.py
│   └── AICFD/
│       ├── __init__.py
│       ├── adapter.py
│       └── versions/                 # 只保存真正发生行为变化的派生 Adapter
│           ├── __init__.py
│           ├── 20260910_a13f7c2.py
│           └── 20260911_f82bd91.py
├── runs/                             # 可清理的运行工作区
└── artifacts/                        # 计算产物归档
```

根目录下的 `solvers/` 保存“如何运行某个求解器”的 Python 适配器，`cases/<case-id>/templates/` 保存“该案例在某个求解器中如何设置”。前者不得包含具体案例的边界值和物理参数，后者不得重复实现求解器启动、进程监督和通用结果标准化逻辑。

`config.yaml` 只保存当前机器或集群的部署信息，例如求解器安装路径、环境激活参数；该文件由 `simtest setup` 创建，并必须加入 `.gitignore`。Adapter 变更点与继承关系、求解器固有能力、命令构造和默认探测规则保存在 Adapter 中。

## 案例、工况与参考解

### 规范案例清单示例

```yaml
id: cylinder-2d
version: "1.0"
title: 二维圆柱定常绕流
tags: [external-flow, incompressible, steady]

execution:
  backend: openmp              # serial | openmp | cuda
  openmp_threads: 32           # 仅 backend: openmp 时使用
  processes: 2

constants:
  diameter:
    type: real
    value: 0.1
    unit: m
  length:
    type: real
    value: 0.2
    unit: m

variables:
  density:
    type: real
    required: true
    unit: kg/m^3
  dynamic_viscosity:
    type: real
    required: true
    unit: Pa*s
  inlet_velocity:
    type: real
    required: true
    unit: m/s

derived_variables:
  reference_area:
    type: real
    expression: "diameter * length"
  reynolds_number:
    type: real
    expression: "density * inlet_velocity * diameter / dynamic_viscosity"

monitors:
  drag_coefficient:
    display_name: 阻力系数
    type: real
    mapping:
      - solver: OpenFOAM
        name: Cd
      - solver: AICFD
        name: DragCoefficient
  outlet_mass_flow:
    display_name: 出口质量流量
    type: real
    unit: kg/s
    mapping:
      - solver: OpenFOAM
        name: Q
        unit: kg/s
      - solver: AICFD
        compatibility: "<20260910-a13f7c2"
        name: MassFlow
        unit: kg/s
      - solver: AICFD
        compatibility: ">=20260910-a13f7c2"
        name: MassFlowRate
        unit: kg/s

fields:
  pressure:
    display_name: 压力
    type: real
    unit: Pa
    mapping:
      - solver: OpenFOAM
        name: p
        unit: Pa
      - solver: AICFD
        name: StaticPressure
        unit: Pa
```

`case.yaml` 不配置 `mesh` 字段。案例根目录按约定提供唯一的 `mesh.cgns`、`mesh.msh` 或 `polyMesh/` 网格资产，由准备阶段发现；未找到或存在多个候选资产时报告配置错误。

`execution` 声明案例的默认并行方式。`backend` 表示每个 MPI 进程内部使用的计算后端，`processes` 表示 MPI 进程数，两者相互独立：`serial` 表示每个 MPI 进程使用单 CPU 线程，`openmp` 表示每个 MPI 进程使用 `openmp_threads` 个线程，`cuda` 表示每个 MPI 进程使用 Nvidia GPU。因此 `backend: serial` 与 `processes: 1` 的组合才是完全串行运行。

并行配置必须满足以下规则：

- `backend` 只能是 `serial`、`openmp` 或 `cuda`；
- `processes` 是大于等于 1 的整数；
- `serial` 后端不允许配置大于 1 的 `openmp_threads`；
- `openmp` 后端要求 `openmp_threads >= 1`，并将其转换为目标求解器参数或 `OMP_NUM_THREADS`；
- 求解器适配器必须在启动前检查对应版本是否支持请求的 MPI、OpenMP 或 CUDA 组合，不支持时返回 `UNSUPPORTED`；
- 网格分区数默认等于 `processes`，除非相应求解器明确采用其他并行模型。
- `execution` 只允许 `backend`、`processes` 和 `openmp_threads`，不得提供展示性 `name`；列表中规范化后的三元组必须唯一。

`constants`、`variables` 和 `derived_variables` 共享同一个名称空间，三类条目之间禁止同名；加载案例时一旦发现冲突立即报错。`monitors` 和 `fields` 内部的 ID 也必须各自唯一。

`unit` 可以省略，省略时内部统一按无量纲处理，报告中可显示为空。有量纲的变量和结果仍建议显式声明单位。`mapping` 条目不写 `unit` 时继承所属 `monitor` 或 `field` 的单位。

`mapping` 中 `solver` 和 `compatibility` 分开声明；没有 `compatibility` 表示适用于该求解器的所有 Adapter。兼容条件按已选 Adapter 的变更点版本比较，规则与模板 `compatibility` 相同，不参与 Adapter 选择。如果某个求解器没有匹配到 `mapping`，则默认使用当前 `monitor` 或 `field` 的名称，不做名称映射和单位换算；如果同时匹配多个 `mapping`，则视为配置错误。

### 工况变量与参考解

`case.yaml` 只声明案例允许使用的变量、类型、规范单位、是否必填、取值约束和派生公式，不保存具体工况变量值。每个具体工况在 `conditions/` 下使用一个独立 YAML 文件定义；系统按目录约定自动发现 `*.yaml`，无需在 `case.yaml` 中逐个引用。

例如 `conditions/Re=1000.yaml`：

```yaml
values:
  density: {value: 1.225, unit: kg/m^3}
  dynamic_viscosity: {value: 1.7894e-5, unit: Pa*s}
  inlet_velocity: {value: 0.01461, unit: m/s}

references:
  experimental_drag_coefficient:
    kind: experimental
    monitor: drag_coefficient
    value: 3.9
    reference_scale: {value: 1.0}
    source:
      kind: paper
      file: references/cylinder-experiment.pdf
      locator: "Table 2, Re=1000"
  analytical_pressure:
    kind: analytical
    field: pressure
    domain: external-fluid
    reference_scale: {value: 1.0, unit: Pa}
    expression: "p0 + ax*x + ay*y + az*z + omega*t"
    parameters:
      p0: {value: 101325.0, unit: Pa}
      ax: {value: 10.0, unit: Pa/m}
      ay: {value: 0.0, unit: Pa/m}
      az: {value: 0.0, unit: Pa/m}
      omega: {value: 2.0, unit: Pa/s}
    source:
      kind: formula
      file: references/manufactured-solution.md
      locator: "Equation 3"
```

工况文件必须满足以下规则：

- `values` 只能赋值给 `case.yaml` 已声明的变量；
- `constants` 和 `derived_variables` 不能在工况文件中覆盖；
- 所有 `required: true` 的变量在解析后必须有值；
- 输入值先转换到 `case.yaml` 声明的规范单位，再计算派生变量；
- 工况文件内容及 SHA-256 必须写入运行元数据。

`references` 应当记录数据来源 `source`。`source.kind` 常用值包括 `paper`、`experiment-report`、`standard`、`web` 和 `manual`等。系统不对 `source` 及其子节点做任何形式的检查，但建议用户在新增案例时能够注明这些信息。

监控标量和解析场统一报告绝对误差与归一化误差：

```text
absolute_error = abs(x - x0)
normalized_error = absolute_error / max(abs(x0), reference_scale)
```

其中 `x` 是数值结果，`x0` 是实验值或解析值；二者先换算到 monitor 或 field 注册的标准单位。每条参考定义显式提供正且有限的 `reference_scale`，采用 `{value, unit}` 形式，省略单位时继承对应物理量的规范单位；示例尺度仅演示配置形式，实际案例应按物理尺度设置。尺度与比较对象换算到同一单位后参与计算，不是通过阈值。绝对误差保留物理单位，归一化误差以百分比展示；场量在各单元中心逐点计算，均值和均方根采用体积加权。系统只报告偏差，不设置容差，也不输出 PASS/FAIL。


### 工况内的参考解定义

参考解定义在对应的 `conditions/<condition-id>.yaml` 的 `references` 字典中，而不放在 `case.yaml`。参考解原始文件仍存放在案例的 `references/` 目录，由 `source` 引用。

字典键即工况内唯一的 reference ID，条目内不再重复设置 `id`。每个条目必须包含 `kind`、`reference_scale`、一个指向 `monitors` 或 `fields` 注册项的键以及 `source`。`kind` 当前支持 `analytical` 与 `experimental`。场参考解还应声明适用 `domain` 以及表达式和参数，不配置比较时刻；对已声明的验证场，比较求解器实际输出的所有时刻。矢量场的每个分量和模长都必须分别比较。

### 追溯要求

- PDF 原件在许可允许时纳入受控文档库；
- 精确标注页码、表号、图号、公式号和工况；
- 数字化曲线保留原始点、工具、操作者和处理脚本；
- 保存单位换算和无量纲化定义；
- 记录实验不确定度或解析解适用范围；
- 参考数据变更要产生新 revision，不能覆盖历史数据；
- 报告中直接展示来源短引和可点击链接，机器结果保存 reference ID。

实验参考解可能不是“绝对真值”，其测量不确定度和工况差异应记录在来源说明中，供用户解释偏差百分比。

## 模板变量与渲染

### 模板变量表示

求解器文本模板统一使用 Jinja2 语法：

```jinja2
{{ namespace.variable }}
```

`constants`、`variables` 和 `derived_variables` 已被禁止同名，因此案例物理量直接使用扁平名称；运行控制、求解器和工况元数据仍使用独立命名空间：

```jinja2
{{ inlet_velocity | real }}
{{ dynamic_viscosity | real }}
{{ reynolds_number | real }}
{{ execution.backend | string }}
{{ execution.processes | integer }}
{{ execution.openmp_threads | integer }}
```

示例：

```cpp
// OpenFOAM 0/U
internalField uniform ({{ inlet_velocity | real }} 0 0);
```

```scheme
; Fluent setup.jou
/define/boundary-conditions/velocity-inlet inlet () no {{ inlet_velocity | real }}
```

```java
// StarCCM setup.java
double inletVelocity = {{ inlet_velocity | real }};
```

### 渲染与覆盖顺序

解析和渲染顺序固定为：

```text
读取 case.yaml 变量声明
→ 读取所选 conditions/<condition-id>.yaml
→ 校验变量名称、类型、范围和必填项
→ 换算到规范单位
→ 计算并校验 derived_variables
→ 自动注册 Adapter，选择安装并探测实际版本
→ 按实际版本选择不晚于它的最近 Adapter 变更点
→ 选择匹配的模板叶子节点
→ 按 extends 链叠加模板文件
→ 构建只读变量上下文
→ 对最终模板执行一次渲染
→ 检查残留占位符并执行原生输入预检
```

版本覆盖必须在模板渲染之前完成，模板只能渲染一次，防止公共模板和版本模板使用不同变量值。

### 类型、安全与转义

模板环境使用 `StrictUndefined`，任何缺失变量立即导致准备失败。若案例或模板可能来自非完全可信来源，使用 `SandboxedEnvironment`。只向模板开放批准的变量命名空间和白名单过滤器，禁止模板读取环境变量、文件、网络或任意调用 Python 对象。

公共模板使用五个稳定的语义过滤器：

```text
real, integer, boolean, string, path
```

过滤器不是全局固定的字符串转换函数，而是由当前求解器 Adapter 提供实现：OpenFOAM 输出其字典语法，Fluent 输出 journal/scheme 语法，StarCCM 输出 Java 字面量，AICFD 输出合法 JSON 字面量。`string` 和 `path` 必须完成目标语言需要的引号及转义；`real` 必须拒绝 NaN/Inf 并生成目标语言可接受的实数字面量；`integer` 必须拒绝非整数值，不能静默截断。

每次渲染必须为该 Run 创建独立的 Jinja2 环境，再注册所选 Adapter 返回的过滤器。禁止修改进程级共享环境，否则并行渲染不同求解器时，同名过滤器会互相覆盖。求解器版本类可以继承默认过滤器，只重载确实发生语法变化的方法。派生变量表达式同样使用受限表达式解析器，只允许已声明变量、基本算术和白名单数学函数，禁止使用 Python `eval()`。

渲染完成后必须：

- 检查是否残留 `{{ ... }}` 或 `{% ... %}`；
- 对生成文件计算 SHA-256；
- 保存工况来源和完整变量解析链；
- 调用求解器适配器执行原生输入检查；
- 不把渲染结果写回 `cases/`。

## 求解器和版本适配

### 适配器接口

每个适配器至少实现以下能力：

```text
probe()            检测可执行文件、真实版本和能力
validate(case)     检查案例是否可由该版本运行
preprocess(run)    转换网格、物化原生输入并生成审计信息
build(run)         返回可审计的参数数组、环境和资源要求
execute(run)       启动并监督求解器进程
postprocess(run)   标准化监控曲线和场结果，并准备解析解验证数据
```

适配器以求解器内核名称注册。先由运行请求确定安装并通过 `probe()` 探测实际版本，再选择不晚于该实际版本的最近 Adapter 变更点，最后选择兼容模板。模板不得反向决定 Adapter。实际版本和构建号同时写入运行元数据。适配器可声明能力：稳态/瞬态、可压缩、多相、动网格、GPU、用户自定义函数等。不支持的功能组合应在运行前返回 `UNSUPPORTED`，而不是执行后失败。

### Adapter 自动注册与机器部署配置

系统启动时递归扫描受信任的 `solvers/` Python 包，导入各求解器的 `adapter.py` 和 `versions/*.py`，通过注册装饰器收集 Adapter 类。新增求解器时只需增加相应目录和 Adapter，无需再在 YAML 中登记 Adapter。注册器按各求解器的版本比较规则排列变更点，并拒绝重复的 `name + version`、同一求解器重复的版本排序键、跨求解器继承和缺失的必需接口。Python 继承仅用于实现复用，不用于确定版本先后。

求解器固有信息放在 Adapter 中，例如：

```python
@register_adapter
class FluentAdapter(SolverAdapter):
    name = "Fluent"
    version = "2024R1"
    capabilities = frozenset({
        "steady", "transient", "compressible", "multiphase"
    })
```

根目录的 `config.yaml` 由 `simtest setup` 生成，只描述本机实际安装：

```yaml
installations:
  - solver: Fluent
    version: 2025R2
    path: /ansys_inc/v252/fluent/
    environment:
      kind: module
      modules: [ansys/2025R2]

  - solver: AICFD
    version: 20260910-a13f7c2
    path: D:/AICFD/
    environment:
      kind: existing
```

加载顺序为：自动注册 Adapter → 读取 `config.yaml` → 按运行请求确定安装 → 探测可执行文件和真实版本 → 按版本排序选择最近的适用 Adapter 变更点 → 合并 Adapter 固有能力与本机可用资源 → 注册可运行实例 → 按已选 Adapter 选择模板。版本探测逻辑放在求解器公共实现中，不依赖尚未选定的版本派生类。`config.yaml` 无需声明安装版本对应哪个 Adapter；配置版本与探测版本不一致时报告 `VersionMismatchError`，不静默按错误的配置版本运行。

案例的 `execution` 描述测试要求的默认并行规模，`config.yaml` 描述机器上如何找到并启动安装，Adapter 描述求解器本身能做什么。三者由适配器合并校验后生成最终命令。

### 各内核建议策略

| 内核 | 原生案例资产 | 批处理方式 | 推荐监控输出 |
|---|---|---|---|
| OpenFOAM | `constant/polyMesh/` + `0/` + `system/` | shell + 求解器命令，必要时 `decomposePar`/MPI | function objects 写表格，辅以日志解析 |
| Fluent | 转换生成的 `.msh` + 版本化 `.jou` | 无界面批处理 journal | report definitions/report files 输出文本/CSV |
| StarCCM | 转换生成的 `.cgns` + 版本化 Java 宏 | 命令行 batch + Java macro | monitor/history 导出 CSV |
| AICFD | 支持的网格文件 + `.json` 参数文件 | 约定 CLI | 原生直接实现标准 CSV 最佳 |

商业软件的自动化 API/TUI 在版本间可能变化，因此 journal/macro 必须版本控制并在对应版本做烟雾测试。

### Python 求解器适配器体系

根目录 `solvers/` 是一个 Python 包。`base.py` 定义统一生命周期抽象，各求解器的 `adapter.py` 实现内核公共行为。版本管理采用**稀疏变更点**：只有某个版本真正改变了命令、输入格式、API 或结果格式时，才在 `versions/` 中增加派生类；没有行为变化的小版本不创建 Python 文件。

```text
SolverAdapter
├── OpenFOAMAdapter
├── FluentAdapter
├── StarCCMAdapter
└── AICFDAdapter
    └── AICFDAdapterV2
        └── AICFDAdapterV3
```

版本变更类沿用前一个变更点的行为，只重载发生变化的方法。以 AICFD 为例，若某次提交改变输入接口，之后另一提交改变结果格式，而其间大量内部版本均无 Adapter 行为变化，则只保留 `20260910_a13f7c2.py` 和 `20260911_f82bd91.py`。Python 文件名使用可导入的下划线形式，类中的 `version` 仍保存求解器报告的`<date>-<commit>`；先后关系由版本中的日期确定，commit 仅用于标识和追溯。

#### `base.py`：抽象生命周期

`SolverAdapter` 至少定义以下接口：

```python
from abc import ABC, abstractmethod
from collections.abc import Callable

class SolverAdapter(ABC):
    name: str
    version: str

    def template_filters(self) -> dict[str, Callable]:
        return {
            "real": self.format_real,
            "integer": self.format_integer,
            "boolean": self.format_boolean,
            "string": self.format_string,
            "path": self.format_path,
        }

    def format_real(self, value) -> str: ...
    def format_integer(self, value) -> str: ...
    def format_boolean(self, value) -> str: ...
    def format_string(self, value) -> str: ...
    def format_path(self, value) -> str: ...

    @abstractmethod
    def probe(self, context: RunContext) -> SolverInfo: ...

    @abstractmethod
    def validate(self, context: RunContext) -> None: ...

    @abstractmethod
    def preprocess(self, context: RunContext) -> StageResult: ...

    @abstractmethod
    def build(self, context: RunContext) -> Command: ...

    def execute(self, context: RunContext) -> StageResult:
        command = self.build(context)
        return self.run_process(command, context)

    @abstractmethod
    def postprocess(self, context: RunContext) -> StageResult: ...
```

`base.py` 的默认格式化实现定义输入校验和“返回完整目标语言字面量”的契约。每个求解器 Adapter 根据自己的输入语言重载 `format_real()`、`format_integer()`、`format_boolean()`、`format_string()` 或 `format_path()`；版本类仍可只重载某个发生变化的方法。模板物化器使用 `adapter.template_filters()` 创建本次 Run 专属的 Jinja2 环境。

基类的 `execute()` 负责公共进程启动、日志、超时、取消、心跳和退出码处理。各内核通常只实现 `build()`；只有启动模型确实特殊时才重载 `execute()`。底层仍可通过 `subprocess` 调用求解器或脚本。

生命周期职责如下：

| 方法 | 职责 |
|---|---|
| `probe()` | 检测可执行文件、真实版本和能力 |
| `validate()` | 校验案例、网格、参数、请求能力和模板兼容条件 |
| `preprocess()` | 转换网格、物化原生输入并生成审计信息 |
| `build()` | 生成参数数组、工作目录和脱敏环境，不拼接不安全的脚本字符串 |
| `execute()` | 执行求解器并监督进程 |
| `postprocess()` | 读取原生监控和场结果，统一坐标、时间、变量及单位，生成标准结果 |

#### `models.py`：统一数据模型

`models.py` 定义适配器之间传递的结构化对象，避免每个求解器自行约定字典键和环境变量。建议至少包括：

- `RunContext`：案例路径、运行目录、求解器、版本、可执行文件、计算资源和已解析的 `case.yaml`；
- `Command`：参数数组 `argv`、工作目录、环境变量和允许的超时；
- `StageResult`：阶段状态、消息、产物、警告、耗时和诊断信息；
- `SolverInfo`：探测到的真实版本、构建号和能力；
- `MonitorRecord`：标准监控量的一条记录；
- `FieldMesh`：节点坐标、单元连接、单元类型、域、区域和接口；
- `FieldDataset`：本次 `references` 请求的网格、物理时刻、变量位置、场数组和单位组成的标准场数据；
- `FieldSample`：域、时刻、单元中心坐标、物理量和数值结果；
- `FieldComparisonResult`：解析解表达式、误差统计、最大偏差位置和可用性状态；
- `RunStatus`：`SUCCEEDED`、`TIMEOUT`、`CRASHED`、`INFRA_ERROR` 等运行状态枚举，不包含收敛结论。

模型本身只表达数据，不读取文件、不启动进程，也不包含某个求解器的业务逻辑。

#### `exceptions.py`：统一异常分类

`exceptions.py` 定义可由编排器稳定识别的异常类型，例如：

```text
SolverError
├── ConfigurationError
├── UnsupportedCaseError
├── VersionMismatchError
├── PreprocessError
│   └── MeshConversionError
├── ExecutionError
│   ├── SolverCrashError
│   └── SolverTimeoutError
└── PostprocessError
    ├── MissingOutputError
    ├── MonitorParseError
    ├── FieldParseError
    └── UnsupportedResultFormatError
```

统一异常使上层能够将失败准确映射为 `UNSUPPORTED`、`TIMEOUT`、`CRASHED` 或 `INFRA_ERROR`，并决定是否可以重试。异常对象应携带阶段、求解器、版本、可公开诊断信息和日志路径；不得包含许可证密钥等敏感值。

系统不判定数值是否收敛。只要求解器进程正常结束且结果可读取，`postprocess()` 就返回有效结果；残差和监控曲线按原始顺序完整标准化并交由用户判断。

#### Adapter 稀疏版本变更

每个 `adapter.py` 实现该内核的初始稳定行为。新版本 Adapter 可以继承最近的旧版本 Adapter，并仅重载发生变化的方法；没有行为变化的内部小版本不创建 Python 文件。每个类声明 `name` 和变更点标识 `version`。

```python
# solvers/AICFD/adapter.py
class AICFDAdapter(SolverAdapter):
    name = "AICFD"
    version = "20260801-12ab34"

    def build(self, context: RunContext) -> Command:
        ...

    def postprocess(self, context: RunContext) -> StageResult:
        ...


# solvers/AICFD/versions/20260910_a13f7c2.py
class AICFDAdapterV2(AICFDAdapter):
    name = "AICFD"
    version = "20260910-a13f7c2"

    def build(self, context: RunContext) -> Command:
        ...


# solvers/AICFD/versions/20260911_f82bd91.py
class AICFDAdapterV3(AICFDAdapterV2):
    name = "AICFD"
    version = "20260911-f82bd91"

    def postprocess(self, context: RunContext) -> StageResult:
        ...
```

Adapter 的 `version` 表示该实现开始适用的软件版本，也是变更点标识。继承关系仅用于代码复用；版本排序和自动选择均不依赖 `issubclass()`、MRO 或继承深度。

#### AICFD 版本比较规则

当前版本格式为 `<date>-<commit>`，其中 `date` 为有效的八位日期 `YYYYMMDD`。暂时约定每天最多发布一个版本：解析日期作为排序键，commit 不参与先后比较，但完整版本字符串必须保留用于身份识别和追溯。不得按哈希字典序推断版本先后。

同一求解器不能注册两个日期相同的 Adapter 变更点。如果实际安装与已知变更点日期相同但 commit 不同，或发现同一天存在不同发布构建，说明当前“一天一个版本”约定已不成立，应明确报告版本歧义，不按 commit 或继承关系猜测顺序。不同路径下同一完整版本的安装副本不属于不同发布构建。格式非法或日期无效时报告版本解析错误。

后续可将日期扩展为包含小时和分钟的时间戳，或增加单调递增的构建号。届时统一升级软件版本和 Adapter 变更点的比较器，明确新旧格式的转换及排序规则；不能直接混用不同长度字符串排序，也不能在无法确定先后时回退到继承排序。

#### `registry.py`：按实际版本选择最近变更点

注册器自动发现实现类，不维护手写实现列表。同一求解器使用统一的版本比较器：AICFD 当前使用日期键；其他求解器按各自版本格式解析为可排序键，不对任意版本字符串直接采用字典序。比较器属于求解器公共实现，不由用户在 `config.yaml` 配置。

选择规则为：

```text
actual_key = version_key(probe().version)
candidates = 同一求解器中 version_key(adapter.version) <= actual_key 的 Adapter
selected = candidates 中 version_key(adapter.version) 最大的 Adapter
```

例如只有以下稀疏变更点：

| Adapter 变更点 | 自动适用的实际软件版本日期 |
|---|---|
| `20260801-12ab34` | `[20260801, 20260910)` |
| `20260910-a13f7c2` | `[20260910, 20260911)` |
| `20260911-f82bd91` | `[20260911, latest)` |

实际安装为 `20260905-b72c901` 时，自动选择 `20260801-12ab34`；不需要为 `20260905-b72c901` 新增 Adapter，也不需要用户填写映射。区间上界由下一个已注册变更点自动确定。

实际版本早于最早变更点时返回 `UNSUPPORTED`；晚于最新变更点时沿用最新 Adapter。这依赖维护约定：影响命令、输入、API 或结果格式的发布必须同步增加变更点。该规则适用于同一条接口演进序列，不推断不同发布分支之间的兼容性；选择成功也不代替能力校验和原生输入预检。

Adapter 一旦选定，模板及 monitor/field mapping 的 `compatibility` 仅针对其变更点版本求值：

- `*`：兼容已选 Adapter；
- 精确匹配 `<version>`：已选 Adapter 的完整变更点标识必须相同；
- 大于等于 `<version>`：已选 Adapter 的版本排序键不小于指定变更点；
- 小于 `<version>`：已选 Adapter 的版本排序键小于指定变更点；
- 同时存在上下界时，按同一比较器计算区间。

条件引用的变更点必须已经注册。没有兼容模板时报告 `UNSUPPORTED`；多个同优先级模板匹配时报告配置歧义。两种情况均不回退或改选 Adapter。

## 求解器模板变体

### 扁平化模板变体

求解器默认模板和版本变体全部作为 `templates` 同级目录，每个目录包含一个 `template.yaml`；目录名只方便人工阅读，系统选择以清单内容为准：

```text
templates/
├── OpenFOAM/
│   ├── template.yaml
│   ├── 0/
│   ├── constant/
│   └── system/
├── OpenFOAM-v2312/
│   ├── template.yaml
│   └── system/
│       └── fvSchemes
├── Fluent/
│   ├── template.yaml
│   └── setup.jou
├── Fluent-2025R2/
│   ├── template.yaml
│   └── setup.jou
├── AICFD/
│   ├── template.yaml
│   └── setup.json
└── AICFD-new-input/
    ├── template.yaml
    └── setup.json
```

`template.yaml` 描述模板 ID、求解器、Adapter 兼容条件和可选父模板。`compatibility` 表示模板可与哪些 Adapter 配合，而不是指定系统必须运行某个固定版本：

```yaml
id: openfoam-default
solver: OpenFOAM
compatibility: "*"
```

```yaml
id: openfoam-v2312
solver: OpenFOAM
compatibility: "v2312"
extends: openfoam-default
```

```yaml
id: aicfd-default
solver: AICFD
compatibility: "*"
```

```yaml
id: aicfd
solver: AICFD
compatibility: ">=20260910-a13f7c2"
extends: aicfd-default
```

`extends` 显式表达模板内容继承，但不改变目录的同级扁平布局。子模板只保存发生变化的文件；物化时先递归加载父模板，再用子模板的同名文件覆盖，最后统一执行一次 Jinja2 渲染。完全独立的模板可以省略 `extends`。

### 模板选择与物化

模板选择优先级为“精确条件 > 有上下界的范围 > 单边范围 > `*`”。系统先选择兼容条件最具体的叶子模板，再沿其 `extends` 链向上解析；不得把所有碰巧匹配的模板自动叠加。相同优先级仍有多个匹配项时视为配置歧义，不依赖目录扫描顺序决定。加载时必须检查：

- `template.id` 在案例内唯一；
- `extends` 指向的模板存在且父子 `solver` 相同；
- 不存在循环继承；
- 同一优先级不存在多个同时匹配的叶子模板；
- `compatibility` 中引用的 Adapter 变更点已经注册；
- 同一求解器的 Adapter 版本排序键唯一且可解析。

系统先按实际软件版本选定 Adapter，再根据 `compatibility` 筛选模板，模板继承只负责文件叠加。归档目录使用探测到的实际软件版本；运行元数据分别保存实际软件完整版本、所选 Adapter 的变更点 `version`、模板 ID 和兼容条件，不得将 Adapter 版本当作实际软件版本。

## 网格转换与求解器输入

### 统一网格资产

每个案例只提供一个经过批准的**统一网格资产**。即使案例包含多个流体域，也不得按域拆成多个源网格；所有域、zone、region、边界及接口配对关系必须共同保存在同一个 OpenFOAM `polyMesh/`、StarCCM `.cgns` 或 Fluent `.msh` 网格中。所有求解器运行均从该资产派生，禁止各求解器或各流体域分别维护未经关联的网格。

网格资产按案例根目录约定发现，不在 `case.yaml` 中声明格式或路径。推荐优先使用 CGNS 作为统一网格格式。

### 启动前网格转换流程

网格转换是每次运行的标准准备步骤，由求解器适配器调用已注册的相关可执行文件完成。转换目标固定如下：

```text
案例唯一统一网格资产（内部可包含多个流体域）
├── Fluent 适配器    → <run>/input/mesh.msh（包含多个 cell zone）
├── StarCCM 适配器   → <run>/input/mesh.cgns（包含多个 zone/domain）
├── OpenFOAM 适配器  → <run>/input/constant/<region>/polyMesh/
└── AICFD 适配器
```

若统一网格资产本身已经是目标格式，则直接复制。

转换器使用 AICFD-NewPre 可执行文件。

### 四类流体内核的输入契约

#### Fluent：`.msh + .jou`

```text
case/
├── mesh.msh
└── setup.jou
```

- `.msh` 由统一网格资产在启动前转换生成；多流体域写成同一网格中的多个 cell zone，并保留域名、边界名和接口信息；
- `.jou` 定义物理模型、材料、边界条件、数值格式、初始化、迭代/时间步、监控项、输出和退出流程；
- 初始输入不依赖 `.cas`；
- 运行期生成 `.cas.h5`、`.dat.h5`、transcript 和监控文件；标准化结果和归档完整性校验均成功后，只保留归档日志、监控 CSV 及 reference 所需 VTU，不归档 `.cas.h5/.dat.h5`；
- `.jou` 按 Fluent 版本维护并在对应版本做批处理回放测试。

#### StarCCM：`.cgns + .java`

```text
case/
├── mesh.cgns
└── setup.java
```

- `.cgns` 由统一网格资产在启动前转换或受控复制生成；多流体域应保存在可明确区分的 zone/domain 中；
- Java 宏负责导入 CGNS、创建或映射 Region/Boundary、定义物理模型和数值参数、创建 Monitor/Report、启动求解并导出结果；
- 初始输入不把预制 `.sim` 作为必需条件；
- 运行过程中可以生成本次计算的 `.sim` 供后处理读取，但该原生文件不纳入长期归档，仅在标准化结果和归档完整性校验均成功后自动删除；
- Java API 可能随 StarCCM 版本变化，因此宏按版本维护，并优先通过稳定名称和标签查找对象，不依赖易变的内部编号。

#### OpenFOAM：`constant/polyMesh + 0 + system`

```text
case/
├── 0/
├── constant/
│   └── polyMesh/
└── system/
```

- 单流体域使用 `constant/polyMesh/`；多流体域使用 `constant/<region>/polyMesh/`，并在需要时使用 `0/<region>/` 保存各区域初始场；
- 所有 `polyMesh/` 均由案例唯一的统一网格资产在启动前转换生成，域名和耦合 patch 必须与源网格中的域及接口配对一致；
- `0/` 定义初始场和边界场；
- `constant/` 中除 `polyMesh/` 外的文件定义物性、湍流模型等；
- `system/` 定义求解控制、离散格式、线性求解器、并行分区和 function objects。

#### AICFD：`多格式网格 + JSON`

```text
case/
├── mesh.<polyMesh|msh|cgns>
└── config.json
```

- 案例唯一的统一网格资产转换为当前 AICFD 版本明确支持的一个文件或 `polyMesh` 文件夹，其中保留全部域及接口配对信息；
- `config.json` 定义物理模型、材料、边界条件、数值参数、停止条件、监控项和输出；
- AICFD 适配器使用 Jinja2 渲染版本化的 `config.json` 模板，通过其重载的 `real`、`integer`、`boolean`、`string` 和 `path` 过滤器生成合法 JSON 字面量；渲染后再用标准 JSON 解析器执行语法、字段及语义校验。

四类输入契约都要求网格区域名称与参数文件中的边界引用一致。适配器应在求解前验证所有必需区域“恰好匹配一次”，不得将找不到的边界静默设为默认类型。

## 作业执行、并发与归档

```text
CREATED → VALIDATING → PREPROCESSING → QUEUED → RUNNING → POSTPROCESSING → SUCCEEDED/TIMEOUT/CRASHED/INFRA_ERROR
```

状态含义必须互斥：

- `SUCCEEDED`：进程正常结束且必需结果完整；该状态不表示数值已经收敛；
- `TIMEOUT`：超过墙钟时间或无心跳时限；
- `CRASHED`：求解器异常退出；
- `INFRA_ERROR`：节点、文件系统、调度器等基础设施错误；
- `UNSUPPORTED`：准备前发现能力不支持，不进入执行状态。

基础设施错误不应计为数值回归。系统不得根据残差或监控曲线自动重试并挑选看似更稳定的结果。

`runs/` 是可清理的并发工作区，不对应单个案例。一次原子作业只计算一个“案例 × 工况 × 求解器 × 实际版本 × 执行参数”组合，并使用独立子目录；因此在计算资源允许时，可以同时运行多个案例、工况和求解器：

```text
runs/
├── <job-id-1>/               # case × condition × solver
│   ├── manifest.json
│   ├── status.json
│   ├── input/                # 物化后的只读输入
│   ├── work/                 # 求解器原生工作目录，仅运行期保留
│   ├── logs/
│   └── normalized/
│       ├── monitors.csv
│       └── fields/           # 没有场参考解时不创建
│           ├── fields.pvd    # 多时刻时可选
│           └── <field>-<time>.vtu
├── <job-id-2>/
└── <job-id-3>/
```

`<job-id>` 由案例、工况、求解器及版本等运行信息生成 Hash；具体参与字段、规范化方法、重复运行和截断长度稍后单独设计。本阶段只要求 `<job-id>` 在并发工作区中唯一、任何路径都不得由多个作业共同写入，且 `manifest.json` 保存生成该 ID 时使用的完整运行身份信息。

求解结束后的固定流程为：

```text
读取原生监控和场结果
→ 将全部已注册监控曲线标准化为 monitors.csv
→ 提取 references 所需场量及域，覆盖求解器实际输出的所有时刻和矢量全部分量及模长
→ 执行解析解精度验证
→ 只为这些验证场生成 VTU/PVD
→ 归档标准化结果、日志、输入快照和元数据
→ 校验标准化结果和归档完整性
→ 仅在两项校验均成功后删除运行目录中的原生计算结果；失败则保留
→ 汇总同一案例下各求解器结果并生成报告
```

`artifacts/` 按案例组织不可变归档。建议结构为：

```text
artifacts/
└── <case-id>/
    ├── runs/
    │   └── <condition-id>/
    │       └── <solver-id>/
    │           └── <actual-version>/
    │               └── <job-id>/
    │                   ├── manifest.json
    │                   ├── status.json
    │                   ├── input/
    │                   ├── logs/
    │                   └── normalized/
    │                       ├── monitors.csv
    │                       └── fields/
    │                           ├── fields.pvd
    │                           └── <field>-<time>.vtu
    └── reports/
        └── <report-id>/
            ├── report.md
            ├── summary.csv
            ├── summary.json
            └── figures/
```

归档不保存求解器原生场结果、临时交换文件或运行期 `work/`。原生结果的自动删除必须以标准化结果校验和归档完整性校验均成功为前提；任一校验失败或未完成时，保留运行目录中的原生结果并记录原因。校验至少确认所需监控 CSV、全部输出时刻的验证场（含矢量全部分量及模长）、日志、输入快照和元数据完整，标准化文件可读取，归档文件清单与哈希一致。即使求解器输出更多物理量，VTU 也只包含当前工况 `references` 中定义的精度验证场；若只存在监控参考值，则只归档 `monitors.csv`，不创建 `fields/`。报告器在所需作业都进入终态后读取各归档的标准 CSV/VTU，生成同图曲线、汇总表和参考解比较；失败作业也必须进入报告，并显示状态及日志摘要。

## 结果采集与标准化
### 监控量定义

监控项必须由案例决定，而非平台写死。典型类型包括：

- 残差；
- 力、力矩及其系数；
- 质量流量、体积流量；
- 面平均/质量加权平均的压力、温度等；
- 压降、效率、总压恢复系数；
- 用户表达式。

每个监控项声明唯一 ID（字典键）、显示名和类型，并按需声明单位及求解器名称映射；单位省略规则遵循前文约定。规范监控项不要求声明区域、采样轴、方向/矩心、积分或平均方法及无量纲参考参数；具体监控设置由各求解器原生模板负责。适配器从原生输出读取步号和物理时间，以生成标准 CSV。

### 标准 CSV

采用宽表格式，每个监控量对应一列：

```csv
step,time,drag_coefficient,outlet_mass_flow,...
0,0.0,1.0234,5.678,...
1,0.1,1.0198,5.543,...
```

要求：

- `step` 是记录序号或迭代步，不能混同物理时间；
- 瞬态案例必须提供 `time`；
- 所有值转换到案例约定单位；
- NaN/Inf 不得静默丢弃；
- 不同采样频率按原始步号和物理时间对齐，未采样位置留空，不插值或前向填充；适配器保留各监控量自身的记录边界，最后一步比较依据该监控量的最后记录，不能把其他监控量引入的尾部空白当作它的最后记录。


### 监控和残差读取

`postprocess()` 处理两类结果：一是读取并标准化残差、力、力矩、流量等监控值或曲线；二是在当前工况 `references` 请求场量时，读取求解器场结果、物理时刻和网格单元中心坐标。不同求解器的文件格式和导出能力不同，因此各内核适配器实现公共读取逻辑，版本派生类只在格式或 API 确实变化时重载相关方法。本章只负责结果读取与标准化，参考偏差计算在后文单独处理。

典型差异包括：

| 内核 | 常见原生输出特征 | 读取重点 |
|---|---|---|
| OpenFOAM | Function objects 生成的 `.dat`，常含 `#` 注释头和空白分隔列 | 忽略注释、识别时间/迭代列、处理向量或分量列 |
| Fluent | Report file 可为 CSV 或文本，不同设置下可能包含标题、引号或括号 | 识别表头、报告名称、迭代/时间步和数值列 |
| StarCCM | Monitor/Plot 导出的 CSV | 处理带单位列名、引号、不同采样轴和版本字段差异 |
| AICFD | 由自研接口约定的 CSV 或文本 | 优先让内核直接输出统一协议，读取器负责校验 |

#### 实现方式

读取器优先使用标准库 `csv`、`json`、`re` 和 `pathlib`，避免在计算节点引入不必要依赖。采用以下原则：

- 内核公共类负责该求解器的默认监控文件解析；
- 版本类默认继承公共逻辑，只有格式变化时才重载读取方法或 `postprocess()`；
- 残差和其他监控量的绘图由上层报告器完成；系统不根据曲线自动判定是否收敛。

标准处理过程为：

```text
发现原生文件
→ 识别并解析格式
→ 将原生监控名称映射到 `case.yaml` 中定义的 monitor 名称
→ 规范迭代步/时间轴
→ 执行单位换算
→ 检查重复点、缺失值、NaN 和 Inf
→ 写标准 monitors.csv
```

`postprocess()` 只负责忠实读取、映射和标准化，不应擅自平滑、删除震荡点或截断曲线。残差文件的发现和解析必须实现在对应的 `adapter.py` 中；格式变化时由派生 Adapter 重载。任何被跳过的坏行都必须记录；必需监控量或残差文件缺失时抛出 `PostprocessError`。

#### 推荐实现结构

```text
solvers/<solver>/
├── adapter.py                  # 内核公共 postprocess() 与读取逻辑
└── <version>.py                # 默认继承公共实现，可按需重载监控读取逻辑
```

#### 监控曲线标准输出

无论原生格式如何，读取器最终统一生成本文规定的宽表 `monitors.csv`。

### 残差和监控数据采集

每个求解器的 `adapter.py` 负责发现并解析其默认残差文件和监控文件，派生 Adapter 只在文件格式或字段语义变化时重载相应读取方法。标准化时必须：

- 保留完整迭代步或物理时间序列，不截取末段；
- 不平滑、不重采样、不删除震荡点；
- 保留原始步号、物理时间、变量名和单位映射；
- 将 NaN/Inf 标记为 `invalid`，不得静默替换；
- 分别标识残差和力、力矩、流量等普通监控量；
- 将解析警告和缺失文件写入作业状态及报告。

### 场结果读取与标准化

当工况的 YAML 文件中通过 `references` 请求 `field` 时，`postprocess()` 还必须执行场量读取与标准化。读取对象由以下信息唯一确定：

- 根据 `domain` 区域筛选；
- `references` 声明的物理量；矢量必须包含每个分量和模长；
- 数据位置统一采用网格中心；
- 求解器实际输出的所有物理时刻，不在案例或工况文件中配置时间选择；
- 坐标系、长度单位和物理量单位。

#### 求解器侧场数据获取

系统采用“原生直读能力检测 + 求解器内导出回退”的双路径。能够稳定读取原生结果时优先直读，以减少二次导出开销；原生格式未公开、当前 VTK 不支持或自研读取器尚未覆盖时，由求解器在计算过程或计算结束时导出 ParaView/VTK 支持的交换格式。两条路径都只提取当前工况 `references` 请求的场量及域，覆盖求解器实际输出的所有时刻，完成读取及 VTU 标准化后不归档原生计算结果。

每个内核的 `adapter.py` 提供场结果获取逻辑：直接读取可用时调用对应的 `FieldResultReader`，否则调用版本化导出器并交给通用交换格式读取器。最终至少获得：

- 网格节点坐标、单元类型和单元连接关系；
- 流体域、cell zone、boundary zone 及接口信息；
- 文件中记录的物理时刻或时间序列；
- 指定标量、向量或张量场及其数据位置；
- 单位、坐标系以及每个单元的体积；体积可直接读取或由网格几何计算；
- 原生 cell/node ID，用于结果追溯。

| 内核 | 原生结果 | 默认策略 |
|---|---|---|
| OpenFOAM | `constant/<region>/polyMesh/`、各时间目录下的 ASCII/二进制场文件 | 使用 ParaView OpenFOAM Reader 或自研读取器直接读取，计算或读取单元中心并关联时间目录 |
| Fluent | legacy `.cas + .dat` | 当前 VTK/ParaView 提供兼容读取器时直接读取，否则由 journal 导出 EnSight Gold 或 CGNS |
| Fluent | CFF `.cas.h5 + .dat.h5` | 启动时探测当前 VTK 构建是否支持；不支持时由 journal 导出 EnSight Gold 或 CGNS |
| StarCCM | `.sim` | 不假定 ParaView 能直接读取；默认通过 Java 宏导出 EnSight Gold、CGNS 或当前版本支持的 VTK 系列格式 |
| AICFD | 自定义结果文件 | 优先实现原生读取器，并建议内核直接支持 VTK/VTU、CGNS 或 XDMF/HDF5 输出 |

直接解析器属于版本敏感组件，必须用小型固定结果文件建立回归样本，验证网格计数、坐标、拓扑、时间、变量名称和数值。读取器遇到未知版本或未知数据块时必须明确失败，不能静默忽略，也不能仅依据扩展名断言兼容。

#### ParaView/VTK 兼容性与导出回退

ParaView/VTK 对求解器原生格式的支持并不对称：

- OpenFOAM 案例目录可以通过 OpenFOAM Reader 读取；
- VTK 提供 Fluent legacy case/data 读取能力，但具体可读取的变量和网格特征仍需用目标版本验证；
- Fluent CFF `.cas.h5/.dat.h5` 的可用性取决于所部署的 ParaView/VTK 版本及其构建选项，系统必须执行能力探测；
- StarCCM `.sim` 不作为 ParaView 可直接读取的通用格式，默认使用求解器内导出。

统一决策流程为：

```text
原生结果文件
→ 探测当前 FieldResultReader/VTK reader 是否支持该格式和版本
  ├── 支持：直接读取并校验网格、时刻和变量
  └── 不支持：调用版本化 journal/Java 宏导出 EnSight Gold、CGNS 或 VTK 系列格式
→ 通用交换格式读取器
→ 标准 FieldDataset
→ references 请求的标准 FieldDataset
```

Fluent 的 `.jou` 应按照当前工况 `references` 请求的域和物理量，在求解器实际输出的所有时刻导出验证所需的最小网格及场数据；推荐优先使用 EnSight Gold 或 CGNS，若当前 Fluent 版本明确支持可靠的 VTK 导出，也可直接生成 VTK 系列文件。版本适配器负责维护实际 TUI 命令及交互参数。

StarCCM 的 Java 宏应按当前工况 `references` 的验证清单导出所需 Region/Boundary、网格拓扑及求解器实际输出的所有时刻的场数据。推荐优先使用 EnSight Gold 或 CGNS；当前版本 Java API 支持时也可输出 VTK/VTU。Java API 和导出选项随版本变化，由相应版本派生类重载。

CSV 只用于监控曲线、截面或离散采样点，不用作完整三维/瞬态流场的标准交换格式。

适配器必须从结果元数据读取真实物理时间，不能仅凭目录名或文件名猜测。系统遍历求解器实际输出的全部场结果时刻，并在各实际时刻计算参考解；不设置时间选择或时间匹配容差，不只取最后时刻。所有时刻指已实际保存的场结果时刻，不要求重建未输出的内部时间步。任一输出时刻缺少已声明的验证场时，必须明确报告结果缺失，不得静默跳过。

#### 统一场数据与采样格式

场量归档采用最小集合：只有当前工况 `references` 中通过 `field` 注册并实际用于精度验证的物理量，才保存对应网格拓扑和场数组。归档覆盖求解器实际输出的所有时刻；每个 VTU 只能包含比较所需的域、物理量及必要的单元体积，矢量包含全部分量和模长，不得顺带保存其他求解器输出字段；没有场参考解的运行不生成 VTU。多个时刻可附带生成 PVD 索引：

```text
fields/
├── fields.pvd
└── fields-<time>.vtu
```

## 参考偏差计算

### 最后一个迭代步的监控值

当 `references` 为某个 monitor 定义参考值时，系统只取该监控曲线最后一个迭代步的记录作为 `x`，不计算最后窗口均值、标准差或震荡指标。最后记录由标准化后的轴值确定，而不是依赖原生文件行顺序。

如果最后一个迭代步的值为 NaN、Inf、缺失或质量标记为 `invalid`，参考比较结果记为 `UNAVAILABLE`，不得回退到更早的有效值。报告同时展示该步号或物理时间，并保留完整曲线；最后一步仍可能处于震荡或漂移状态，其数值可靠性由用户判断。


### 标量比较

监控标量统一使用下式：

```text
absolute_error = abs(x - x0)
normalized_error = absolute_error / max(abs(x0), reference_scale)
```

`x` 为监控曲线最后一个迭代步的值，`x0` 为相应工况的参考值；两者及正值 `reference_scale` 必须先换算到 monitor 注册的标准单位。报告显示带单位的 `absolute_error` 和 `normalized_error × 100%`，不判断是否通过。该偏差只针对最后一步数值，不表示曲线已经收敛；版本回归比较可以复用同一公式，但基线值不属于 `references`。

### 曲线比较

- 同一迭代轴上的残差和监控曲线用于如实展示计算过程，不据此自动判定收敛；
- 不同求解器的迭代定义可能不同，报告不得把相同步号解释为相同物理状态；
- 瞬态结果优先使用物理时间轴展示；
- 当前阶段不自动执行曲线平滑、相位对齐、周期识别或曲线误差统计。

### 场量与解析解比较

当参考分布是解析函数 `f(x,y,z,t)` 时，直接在每个求解器自身网格的单元中心，对实际输出的所有物理时刻求值，再逐点计算绝对误差和归一化误差，不需要跨网格插值。解析式、参数、单位、适用域、归一化尺度和来源由对应的工况文件声明，不声明比较时刻。报告按时刻分别给出最大误差、体积加权平均误差、体积加权均方根误差及最大误差位置，不判断是否通过。

当比较对象是另一个求解器的离散场或实验离散数据时，不同网格上的场不能按单元编号直接比较。应定义公共采样对象：坐标点、线、截面、表面或统一参考网格，并记录插值方法。建议指标包括 L1/L2/L∞、守恒积分差、剖面误差和关键位置偏移。

#### 解析函数求值

公共分析器在每条单元中心记录上计算：

```text
reference_value = f(x, y, z, t; parameters)
absolute_error  = abs(numerical_value - reference_value)
normalized_error = absolute_error / max(abs(reference_value), reference_scale)
```

禁止直接对工况文件中的表达式字符串使用 Python `eval()`。表达式应通过受限表达式解析器执行，只允许 `x`、`y`、`z`、`t`、已声明参数以及白名单数学函数；禁止文件、网络、模块导入和任意对象访问。解析函数的表达式、参数、单位和文献/公式来源都必须写入结果追溯信息。

比较前必须将坐标、时间、数值结果和解析函数参数转换到一致单位。由于解析解可以直接在各自网格的单元中心求值，这种验证不需要在不同求解器网格之间插值。

#### 误差计算与汇总

对每个 `time × domain × field × component` 分组，在每个单元中心计算：

```text
absolute_error[i] = abs(x[i] - x0[i])
normalized_error[i] = absolute_error[i] / max(abs(x0[i]), reference_scale)

# e 分别取 absolute_error 或 normalized_error；V[i] 是当前时刻单元体积
mean_error = sum(V[i] * e[i]) / sum(V[i])
rms_error = sqrt(sum(V[i] * e[i]**2) / sum(V[i]))
max_error = max(e[i])
```

其中 `x[i]` 是数值结果，`x0[i] = f(x,y,z,t)` 是解析值。场比较通常针对体域，均值和均方根统一采用当前时刻的单元体积加权，最大值不加权；不跨时刻混合统计。绝对误差统计保留物理单位，归一化误差统计以百分比展示，并分别记录最大误差所在的单元中心坐标。体积必须为正且有限；无法取得有效体积或存在无效场值时，明确报告比较不可用，不得静默改用单元数量平均或丢弃无效单元。

矢量解析式使用以 `x`、`y`、`z` 等实际分量名为键的 `expression` 字典，每个值为相应分量的解析表达式。数值矢量和参考矢量先统一坐标系，各分量分别执行上述比较；再分别计算二者的欧氏模长，并对模长执行同样的比较。模长绝对误差为 `abs(norm(u) - norm(u0))`，不是 `norm(u - u0)`。同一参考条目的正值 `reference_scale` 用于各分量及模长。系统不设置通过阈值，也不生成验收结论。

## 图表与报告

报告固定使用 `residual`、`monitor` 和 `analytical` 三类语义区段，只有本次选集实际存在对应报告数据时才显示。每类区段内部根据标准化记录或场比较结果动态构造任意数量的图表，不在 HTML 模板中固定 monitor 名称、场、分量、参考 ID 或图表数量。新增同类输出时扩展图表描述生成逻辑，不复制固定图表模板；报告不得猜测或展示未进入标准化归档的数据。

`monitors.csv` 同时保存求解器输出的残差和其他标量历史，其中非残差标量是求解器观测值，不等于实验监控值。报告中的 `monitor` 区段只表示工况 `references` 中 `kind: experimental` 指向的监控值比较，并同时绘制求解器观测曲线与实验参考线；没有实验参考时，非残差标量仍可留在标准化归档中，但不生成 `monitor` 图表。`analytical` 区段表示工况公式生成的场参考比较。三类数据通常按案例验证方式选择，但实现不以互斥关系拒绝同时存在的合法配置。

纵轴主刻度根据当前可见数据范围、线性或对数坐标类型及可用图表高度计算；对数跨度较大时允许减少主刻度并使用较淡次刻度补充。刻度优化不得转换、截断或修改原始数据。

### 监控曲线图

每个具有实验参考值的 monitor 一张主图，将所有 `solver` 的 latest 版本（默认）结果叠加：

- 颜色区分内核，线型或标记区分版本；
- 图例使用 `内核 / 版本 / 运行配置`；
- 坐标轴含单位；
- 参考标量画水平线；来源提供测量不确定度时可显示不确定度带，但不据此判定 PASS/FAIL；
- 标出用于参考比较的最后一个迭代步；
- 残差曲线独立绘制，并允许使用对数纵轴，但不自动标注收敛结论；
- 默认导出 PNG 供报告查看，同时导出 SVG/PDF 供出版或放大。

当不同运行实际步数差异很大时，报告应提供完整过程图和末段放大图，不要人为截齐而隐藏后期行为。

汇总表的筛选与排序相互独立。可排序字段在表头提供升序和降序入口，多字段按用户选择顺序逐级比较，只有前置字段相同时才使用后续字段；作业 ID、显示序号和操作列不排序。

### 汇总表

| 案例 | 监控量 | 内核 | 版本 | 最后步 | 最后值 | 参考值 | 绝对误差 | 归一化误差 | 运行状态 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| cylinder-2d | Cd | Fluent | 2025R2 | 2000 | 1.02 | 1.00 | 0.02 | 2.0% | SUCCEEDED |
| cylinder-2d | Cd | OpenFOAM | v2312 | 2000 | 1.08 | 1.00 | 0.08 | 8.0% | SUCCEEDED |

表中示例采用 `reference_scale = 1.0`，Cd 为无量纲量。“绝对误差”和“归一化误差”只量化最后一个迭代步的监控值与参考值之间的差异，不代表该结果已经收敛或在物理上可靠。最终报告分别展示运行状态、偏差百分比和完整曲线，判断监控值是否可信由用户完成。

## 命令行设计建议

```text
simtest setup
simtest list cases
simtest list solvers
simtest validate cases/cylinder-2d
simtest run cylinder-2d --condition Re=1000 --solver OpenFOAM@v2312 --solver Fluent@2025R2
simtest run cylinder-2d --all-conditions --solver AICFD@latest
simtest report cylinder-2d
```

命令行中的 `--solver AICFD@latest` 是求解器安装选择器，表示按该求解器的部署发现策略选择最新版安装；它不是 `template.yaml.compatibility` 的取值，二者不冲突。AICFD 的 `latest` 按探测到的版本日期选择最新安装，使用与 Adapter 选择一致的版本比较器；同一天不同构建按版本歧义处理。归档时必须把命令行别名固化为探测到的实际求解器版本。

### 创建机器部署配置

`simtest setup` 默认在仓库根目录创建 `config.yaml`。它只负责机器部署配置，不把求解器固有能力或 Adapter 版本关系写入 YAML。

```text
# 使用当前进程已有的环境
simtest setup \
  --solver AICFD --version 20260910-a13f7c2 \
  --path D:/AICFD/ --environment existing

# 运行前加载集群模块
simtest setup \
  --solver Fluent --version 2025R1 \
  --path /ansys_inc/v252/fluent/ \
  --environment module --environment-module ansys/2025R2

# 运行前加载环境脚本
simtest setup \
  --solver AICFD --version 20260910-a13f7c2 \
  --path /opt/aicfd/ \
  --environment script --environment-script /opt/aicfd/activate.sh
```

建议参数如下：

| 参数 | 含义 |
|---|---|
| `--config <path>` | 输出位置，默认为仓库根目录的 `config.yaml` |
| `--solver <solver>` | 已自动注册的求解器名称，如 Fluent 或 AICFD |
| `--version <version>` | 求解器版本 |
| `--path <path>` | 求解器安装根目录 |
| `--environment <kind>` | 环境类型：`existing`、`module` 或 `script` |
| `--environment-module <name>` | 运行前加载的模块，可重复；仅用于 `module` |
| `--environment-script <path>` | 运行前加载的环境脚本；仅用于 `script` |
| `--force` | `--solver` 和 `--version` 已存在时替换安装记录 |

若 `config.yaml` 已存在，普通调用只追加新安装。写入前应完成以下校验：求解器 Adapter 已注册、环境类型与专属参数匹配、安装标识和别名不冲突，并在激活所选环境后探测可执行文件及实际版本。配置采用临时文件加原子替换方式写入。

## 可复现性、性能与安全

### 稳定作业身份与追溯边界

每个作业使用 `simtest-identity` 协议构造规范身份对象，并对其规范 JSON 计算 SHA-256 作为稳定作业 ID。协议名保持稳定，不通过 `/2`、`-v2` 等数字后缀表达实现演进；协议内容发生不兼容变化时，应显式迁移和校验已有身份，不能依靠改名绕过兼容责任。

身份只包含当前运行的有效输入和执行条件：

- 当前 `case.yaml` 去除 `execution` 后的共同案例定义、动态发现并选中的 `conditions/<condition-id>.yaml`、解析后的当前工况参数、唯一源网格，以及所选 Adapter 对应模板继承链叠加后的有效模板文件；
- 当前求解器的内核名称、发行分支、探测到的实际版本与构建、可执行文件，所选 Adapter 变更点及其继承链源码和显式声明的身份辅助文件；
- execution 配置、超时、安装与环境指纹、硬件/载体信息，以及实际参与运行的 Python 运行时和依赖版本。

工况按 `conditions/*.yaml` 动态发现，不维护固定工况注册列表。工况 ID 是身份的一部分；新增、删除或修改其他工况不得改变当前工况的作业 ID，修改当前工况文件、共同案例定义、源网格、有效模板或解析参数则必须产生新 ID。相同内容使用不同工况 ID 时仍视为不同作业，避免归档语义混淆。`execution` 列表的每项都是独立配置：当前项由 identity 的 `execution` 字段参与判重，新增、删除或修改其他项不得改变当前项的作业 ID。

完整案例仓库 inventory 和完整平台代码 inventory 只作为追溯信息写入 `manifest.json`，不参与作业 ID。README 等说明文档、`.pyc`/`__pycache__`、报告代码及报告生成物、其他工况、未选模板、无关求解器或无关 Adapter 的变化不得使当前计算失去复用资格。当前 Adapter/version code 的变化必须进入身份；平台代码清单仍应完整记录，以便解释历史运行环境。

### OpenMP 与 CUDA 接入前提

`backend: openmp` 和 `backend: cuda` 是对每个 MPI 进程内部计算方式的请求，不是通过设置环境变量即可默认启用的能力。Adapter 只有在 `probe()` 确认当前求解器版本、构建和本机资源具备对应能力后，才能声明 `openmp` 或 `cuda`；`validate()` 必须校验进程、线程或 GPU 组合；`build()` 必须构造经验证的命令、环境和绑定策略；`postprocess()` 必须与串行/MPI 基线做结果可读性和数值偏差回归。

OpenMP 接入至少应验证目标求解器的实际线程运行契约、`OMP_NUM_THREADS` 传递、`processes × openmp_threads` 的资源限制，以及串行、纯 MPI、纯 OpenMP 和混合 MPI×OpenMP 的真实样例。CUDA 接入必须绑定到明确的 GPU 求解器构建和版本变更点，探测驱动、可见设备和每个 MPI 进程的设备映射；未经验证不得让多个 MPI 进程隐式共享 GPU。当前 OpenFOAM 12 与 2506 Adapter 只声明 serial/MPI，OpenMP/CUDA 继续返回 `UNSUPPORTED`，直到上述探测、命令与真实回归完成。

创建时间、运行目录、实际耗时、资源使用结果、随机 nonce 和其他运行后统计不参与身份。复用时必须同时校验作业 ID、完整规范身份和归档完整性；损坏或身份不一致的归档拒绝覆盖和复用。

### 运行元数据

至少记录：

- 测试系统和适配器 Git commit；
- 案例 revision 与全部输入 SHA-256；
- 探测到的求解器完整版本/构建号、所选 Adapter 变更点版本、模板 ID 及版本比较规则；
- 操作系统、容器镜像 digest、主机和 CPU/GPU；
- MPI 实现、进程/线程数、分区方法；
- 环境变量白名单和值的脱敏摘要；
- 完整参数映射、命令和退出码；
- 开始/结束时间、墙钟时间、CPU 时间和峰值内存。

性能回归只应在可比硬件、并行规模、分区和系统负载约束下判定。首次运行缓存、文件系统波动等不能混入求解耗时。

### 安全与许可证

- 案例中的 journal、macro、用户子程序都视为可执行代码，只运行受信仓库中的已审查版本；
- 禁止将许可证密钥、服务器凭据或商业二进制打包进产物；
- 日志归档前做敏感信息过滤；
- 对命令参数使用数组化构造和白名单，避免 shell 注入；
- 商业求解器容器化和并发方式须符合许可证条款；
- 只有标准化结果和归档完整性校验均成功后，才能自动删除求解器原生场结果和临时交换文件；校验失败或未完成时保留原生结果，并在状态及日志中记录原因。
