# 数值模拟软件自动测试系统

把案例输入交给已登记的求解器，自动完成准备、计算、结果标准化、解析解比较和 **HTML 交互报告**。

系统不设置数值通过阈值；`SUCCEEDED` 表示执行和必需结果完整，数值偏差需要结合解析解比较结果判断。

## 从这里开始

- [日常使用](#日常使用)：查看案例 → 校验 → 运行 → 打开报告。
- [报告查看](#报告查看)：曲线操作、数值含义和数据下载。
- [目录与运行流程](#目录与运行流程)：各部分职责。
- [首次配置与排错](#首次配置与排错)：其他机器部署、Linux 和 WSL 常见提示。

报告由实际运行自动生成，路径会显示在命令输出中；也可使用 `report` 汇总已保存作业。新案例完成计算前不提供固定报告链接。

## 日常使用

Windows 用户先在 PowerShell 中进入 WSL：

~~~powershell
wsl -d Ubuntu
~~~

进入 Linux 后切换到工程根目录：

~~~bash
cd /mnt/c/Users/Administrator/PycharmProjects/repository
~~~

原生 Linux 用户切换到实际的工程路径。以下平台命令均在 Linux / WSL 终端的工程根目录执行，使用真实案例名称，可以直接复制。

### 1. 查看并校验

~~~bash
python3 -m simtest list cases
python3 -m simtest list solvers
python3 -m simtest validate couette-2d
~~~

| 命令 | 结果含义 |
|---|---|
| `list cases` | 扫描 `cases/` 下符合结构的案例和工况。 |
| `list solvers` | 列出代码中登记的 Adapter 版本。 |
| `validate` | 检查案例、工况、模板与实际安装版本；返回 `valid: true` 后可运行。 |

### 2. 运行

~~~bash
# 依次运行 case.yaml 中声明的全部执行配置；完成后合并成一份 HTML 报告
python3 -m simtest run couette-2d

# 显式指定发行分支版本
python3 -m simtest run couette-2d --solver OpenFOAM@12
python3 -m simtest run couette-2d --solver OpenFOAM@2506
~~~

`OpenFOAM@12` 选择 Foundation 12，`OpenFOAM@2506` 选择 OpenCFD 2506；`OpenFOAM@latest` 只在同一分支内选择最新版本，同时登记两个分支时会明确报歧义，不会跨分支比较版本大小。

执行参数在 `cases/<案例>/case.yaml` 的 `execution` 中声明，可以是单个映射，也可以是映射列表：

~~~yaml
execution:
  - name: serial-1proc
    backend: serial
    processes: 1
  - name: mpi-2proc
    backend: serial
    processes: 2
~~~

`run` 按声明顺序逐个执行，全部作业进入同一份报告；命令行不再提供 `--processes`、`--backend`、`--openmp-threads` 覆盖。

作业 ID 是按 `simtest-identity` 协议对当前运行的有效身份计算得到的 64 位 SHA-256；协议名不使用数字后缀。同身份重复命令会校验并复用已有成功归档，返回 `reused: true`，不重新求解。不同身份使用独立工作区；同身份并发请求等待文件锁后复用，避免重复计算。标准结果和归档均校验成功后，删除整个 `runs/作业ID/`，日志、输入和标准结果只保留在归档中。失败或校验未完成时保留现场，重复请求返回原失败，不自动重试。

身份只包含本次运行会实际使用并可能改变计算结果或执行条件的内容：案例清单、当前动态发现的工况文件及解析参数、唯一源网格、当前 Adapter 选中的有效模板；当前求解器的实际分支、版本、构建、可执行文件和所选 Adapter/version code；以及 execution、超时、部署环境、硬件/载体、Python 运行时和依赖版本。工况无需预先写入固定列表；新增或修改其他工况不改变当前工况的 ID，选择不同工况名称或修改当前工况有效输入则产生新 ID。

完整案例仓库清单和完整平台代码清单仍写入 `manifest.json` 作为追溯证据，但不参与作业 ID。README、解释器缓存（`.pyc`/`__pycache__`）、报告代码或生成物、其他工况、未选模板和无关求解器/Adapter 的变化均不改变当前 ID；当前 Adapter 继承链及其显式身份辅助文件发生变化时会改变 ID。创建时间、实际耗时、随机数、生成的工作目录及运行后统计也不参与判重。

`reused` 的耗时是原计算记录，不能当成本次性能测量。损坏归档拒绝复用和覆盖，须恢复完整数据后再处理。

只准备输入、暂不计算：

~~~bash
python3 -m simtest run couette-2d --prepare-only
~~~

此时输出 `QUEUED` 表示准备完成，**没有后台队列继续运行**，也没有已归档结果可生成报告。要实际计算，重新执行相同参数、不带 `--prepare-only` 的 `run`，校验输入和工作区快照后接续同一作业；若该身份已成功归档，则直接复用。

需要调整超时：

~~~bash
python3 -m simtest run couette-2d --timeout 300 --heartbeat-timeout 120
~~~

单位为秒；心跳超时指原生日志长时间没有进度输出。Ctrl+C 会终止受监督的求解器进程组。

### 3. 查看作业 ID，重新生成报告

~~~bash
# 查看已归档作业的真实 ID、工况、进程数、状态和时间
python3 -m simtest list runs --case couette-2d

# 选择具体作业时，在命令后追加 --job-id 和上面查到的真实 ID

# 汇总本案例的成功归档和 runs 中保留的终态失败作业
python3 -m simtest report couette-2d
~~~

`report` 从归档 CSV/VTU 独立读取观测数据，使用归档中的参考定义计算报告，不启动求解器，也不修改归档。同一选集与相同报告代码复用同一报告目录；重复 ID 自动去重。可重复指定 `--job-id` 选取不同作业。选择同一目的、可比较的运行集合，避免混合不同开发阶段的结果。

**不要原样输入 `<job-id>`。** 它是说明中的占位符，尖括号在 shell 中有特殊含义。请用 `list runs` 输出中的真实 ID 替换，直接填写，不带尖括号。

### 4. 打开最新报告(待添加新功能)

在 Linux / WSL 中查找最新报告：

~~~bash
python3 - <<'PY'
from pathlib import Path

reports = list(Path("artifacts/couette-2d/reports").glob("*/report.html"))
if reports:
    print(max(reports, key=lambda path: path.stat().st_mtime).resolve())
else:
    print("暂无报告，请先运行计算或生成报告。")
PY
~~~

使用浏览器打开输出的 HTML 文件。原生 Linux 图形环境可使用文件管理器打开；WSL 中的 `/mnt/c/...` 对应 Windows 的 `C:\...`，可在 Windows 文件资源管理器中双击 `report.html`。也可在 WSL 执行 `explorer.exe .` 打开当前工程目录，再进入 `artifacts/couette-2d/reports/`。

## 报告查看

报告使用固定 Jinja2 HTML 模板和 Apache ECharts 5.6.0 图表框架。图表数据、框架、样式和交互脚本全部内嵌，**无需联网、无需启动 Web 服务**。固定模板位于 `report_assets/report.html`，图表行为和样式分别位于 `report.js`、`report.css`；官方框架资源保持原样，版本、SHA-256 和许可证随项目保存。

工况名称直接采用 `conditions/` 下的 YAML 文件名（如 `Re=10`）。报告图表只分为解析解对比、监控量和残差三类，横轴统一为 `Step`（迭代步）。存在解析场参考时显示解析解对比，不再同时显示普通监控量；残差始终独立显示。解析解对比只展示归一化误差，速度 X、Y、Z 分量及模长分别成图，每张图可切换最大值、均值或 RMS。

| 操作 | 用法 |
|---|---|
| 放大 / 缩小 | 滚轮，或图表上方的“放大 +”“缩小 −”按钮 |
| 查看局部 | 点击“框选”后拖动，或拖动图下方范围滑条；“末段放大”查看最后 20% |
| 移动视区 | 点击“平移”，再拖动；再次点击回到框选 |
| 恢复全貌 | 双击图表或点击“重置” |
| 查看具体值 | 鼠标悬停在曲线采样点附近 |
| 显示 / 隐藏曲线 | 点击图例；重合曲线可逐条查看 |
| 线性 / 对数坐标 | 切换 Y 轴；对数轴不能显示零和负数，页面会提示数量 |
| 查看不同误差指标 | 解析解对比图可切换归一化误差的最大值、均值和 RMS |
| 放大工作区 / 导出 | 使用“全屏”或“导出当前 SVG” |

页面包括作业状态、交互曲线、最后一步监控值和最后一步解析解归一化偏差。页面不展开完整数值记录，也不显示绝对误差；归档中的完整监控 CSV、验证场、绝对误差、参数、硬件、版本、状态和参考来源保持不变，可从“追溯与下载”访问。曲线展示各工况 / 求解器所选作业中的最新实际版本，并按发行分支分别选择，跨分支不会互相覆盖。

阅读时注意：

- 保留全部采样点。无效值产生断点，不平滑、不插值、不前向填充；最后记录无效时不回退到较早有效值。
- 所有图像横轴均为 `Step`（迭代步）；悬浮提示同时保留归档中已有的物理时间。`residual_p` 纵轴默认使用 log₁₀ 对数刻度，数据仍是原始残差值。零值、负值与无效值在对数轴显示为断点并提示，可切回线性轴。
- 本例残差是**每个时间步首个线性求解的初始残差**。原生日志保留完整校正器记录；不能单凭这条曲线认定整个瞬态过程已收敛。
- 场误差仍按各实际保存时刻计算，报告将这些时刻映射到经过验证的求解器迭代步；均值和 RMS 按单元体积加权，页面只显示归一化误差。
- 归一化误差以百分比显示，归一化尺度不是容差。`UNAVAILABLE` 或“—”不等于零。
- 默认轴范围避免把近似常数的浮点扰动画成大幅变化；可自行缩放查看细节。

每份报告目录包含：

~~~text
report.html     浏览器阅读与交互入口
summary.csv     监控末条记录与比较数据，包含完整 job_id
summary.json    完整作业元数据、标准观测、全部比较、单位、来源和诊断
monitors.csv    全部监控逐点记录（包含原始值与质量标记）
field_errors.csv 各时刻、分量和误差统计
ECHARTS-*.txt   离线图表框架及子组件许可证
figures/        默认视图的 PNG、SVG、PDF
integrity.json  报告产物完整性清单
~~~

单独复制 HTML 仍可交互查看图表；要使用追溯链接，应保留报告同目录文件及其相对归档路径。报告目录中的 CSV/JSON 继续保存既有机器数据，但不在页面展开；三维场可用 ParaView 打开归档中的 `normalized/fields/fields.pvd`。

## 目录与运行流程

| 位置 | 作用 | 什么时候使用 |
|---|---|---|
| `simtest.py` | 命令入口，解析参数并调用各业务模块 | 所有平台命令 |
| `config.yaml` | 本机求解器安装路径和环境配置 | 首次配置后由平台读取 |
| `cases/` | 案例物理定义、工况、模板、网格与参考解 | 所有计算的源输入 |
| `cases/<case-id>/mesh-preparation/` | 案例专属的源网格制备脚本和配置 | 显式制备网格时 |
| `case_management/` | 公共案例/工况/参数解析、唯一源网格发现；模板选择、继承、安全检查与一次渲染 | 发现、校验及准备阶段 |
| `solvers/` | 注册与安装绑定、环境加载、公共进程执行，以及 Adapter 的原生输入、网格、监控和场处理 | setup、校验、准备、求解、后处理 |
| `jobs.py` | 创建作业、记录版本和硬件追溯信息、管理状态并依次调用 Adapter 各阶段 | run |
| `analysis.py` | 使用统一公式计算监控及解析场参考偏差 | 标准化完成后 |
| `archive.py` | 查询归档、检查标准文件和哈希、保存归档并控制工作区清理 | 作业收尾及 list runs / report |
| `report.py`、`report_assets/` | 汇总报告、HTML 交互、静态图及 CSV / JSON；资源支持安装后离线读取 | run 结束或 report 命令 |
| `platform_support/` | 文件操作、表达式、单位换算与平台版本；不主动启动求解 | 各业务模块复用 |
| `runs/` | 活动、准备和失败作业的工作区；成功归档后整目录移除 | 计算、失败排查 |
| `artifacts/` | 经校验的结果归档和派生报告 | 长期留存、比较、阅读 |
| `tests/` | 单元、Reader 及集成回归测试 | 修改代码后验证 |
| `tests/report/` | HTML 报告的浏览器交互回归 | 开发或专项检查 |

`simtest.py` 负责命令入口；根目录 jobs、analysis、archive、report 对应作业组织、分析器、产物库和报告器。`case_management/`、`platform_support/` 保留已有公共能力，`solvers/` 集中求解器相关行为；不再分别建立运行控制、后处理、存储和报告代码目录。`cases/` 保存物理输入，`runs/` 和 `artifacts/` 保存数据；归档按案例 / 工况 / 内核 / 实际版本 / 稳定作业 ID 组织。

`solvers/registry.py` 登记和选择本机已有安装，使用 Adapter 的主程序标识与版本比较规则；`base.py` 统一进程监督及辅助执行。OpenFOAM Adapter 的 `read_log()`、`read_tables()`、`read_monitors()`、`output_times()` 和 `read_fields()` 处理原生结果，`postprocess()` 通过实例方法调用，版本类可以只重载发生变化的部分。`vtk_bridge.py` 位于对应内核目录，由独立 pvpython 执行，平台 Python 不直接加载 VTK。

`case_management/` 处理公共语义，不规定 OpenFOAM、Fluent 等内核的原生目录。`templates.py` 的 `template_files()` 供 `validate` 和实际物化共用：先拒绝符号链接及模板内附带的源网格，再调用当前 Adapter 的 `validate_template()` 检查原生布局，最后叠加文件；物化时只渲染最终文件一次。OpenFOAM 的 `0/constant/system` 限制位于对应 Adapter，版本类可重载。

`cases.py` 的 `mesh_asset()` 只发现唯一源资产并检查文件/目录类型；`polyMesh` 的 points、faces、owner、neighbour、boundary 由 OpenFOAM Adapter 的 `validate_mesh()` 检查。因此 `list cases` 用于发现案例；原生网格不完整时由 `validate` 和准备阶段报错。`validate` 检查模板布局和源网格结构，不渲染文件或启动原生工具；`run --prepare-only` 才会物化输入并执行原生预检及 checkMesh。


运行顺序：

~~~text
发现案例 / 工况
  → 探测实际求解器版本并选择 Adapter
  → 解析参数、物化输入模板、复制并核验源网格
  → 网格准备；MPI 作业分区
  → 启动并监督求解器，记录日志、时间与资源
  → MPI 作业重构全部保存时刻
  → 标准化监控和参考解所需场
  → 按实际物理时刻计算解析偏差
  → 校验标准结果、保存归档、校验哈希
  → 两项校验通过后删除整个 runs/作业ID/
  → 生成 HTML 报告
~~~

场读取优先原生 OpenFOAM Reader，能力不满足时尝试 `foamToVTK`。本例归档速度、各分量、模长、体积、真实单元中心坐标和追溯 ID，压力等未用于参考比较的场不额外归档。

标准监控表采用 `step,time,各监控量` 的宽表。不同监控的采样位置留空。报告读取归档 CSV/VTU 并使用归档参考定义计算偏差；之后修改源案例公式不会改写旧归档或改变旧身份的参考定义。

## 当前案例：couette-2d

`couette-2d/Re=10` 是二维启动 Couette 流。两块平行板间充满不可压缩层流流体：下壁静止，上壁从 `t=0` 起以恒定速度 `U` 沿 X 方向运动，X 方向采用周期边界，Z 方向为 `empty`。内部速度初始为零，随后由黏性作用从上壁向流体内部扩散，并逐渐接近线性稳态速度分布。

速度解析解为：

~~~text
Ux(y,t) / U = y/H
              + (2/π) Σ[n=1..∞] {(-1)^n / n
                  × sin(nπy/H)
                  × exp[-n²π²νt/H²]}
Uy = Uz = 0
~~~

其中 `H` 为板间距，`ν` 为运动黏度。数值参考在正时间使用有限项级数计算，并记录截断方式；`t=0` 的初始条件和壁面不连续点单独处理，不能用有限项级数的振荡判断求解错误。

| 参数 | 当前设置 |
|---|---|
| 工况 | `Re=10`，其中 `Re=UH/ν` |
| 上壁速度 U | 1 m/s |
| 运动黏度 ν | 0.1 m²/s |
| 板间距 H | 1 m |
| 初始内部速度 | `(0, 0, 0)` m/s |
| 边界 | 上壁移动、下壁静止、X 周期、Z 为 `empty` |
| 网格 | `16 × 32 × 1`，共 512 个单元 |
| 时间 | 步长 0.01 s，终止 10 s，共 1000 步；每 1 s 保存一次场 |

案例输出保留实际保存时刻的速度场及 `Ux`、`Uy`、`Uz`、速度模长，记录速度与压力残差、体积平均速度和求解资源。报告按时刻比较数值场与解析解，分别给出各速度分量和模长的最大误差、体积加权平均误差及 RMS；压力用于求解监控，不作为 Couette 速度解析解的一部分。

一个工况和两种执行配置是当前示例选择；平台的发现机制不限制案例、工况或执行配置数量。更换 `U`、`ν`、`H`、时间设置或网格时，需要同步维护工况参考参数、参考来源和案例版本，避免比较不同物理条件。

唯一源网格为 `cases/couette-2d/polyMesh/`。运行过程只复制并核验，不隐式重新生成源网格。`cases/couette-2d/mesh-preparation/create_example_mesh.py` 与同目录 `blockMeshDict` 用于显式制备新网格，脚本拒绝覆盖已有源网格。

## 首次配置与排错

### 本机环境

当前项目已有安装登记：WSL Ubuntu、OpenFOAM Foundation 12（`/opt/openfoam12`）与 OpenCFD 2506（`/usr/lib/openfoam/openfoam2506`），以及 ParaView 的 `pvpython`（`/opt/paraviewopenfoam510/bin`）。WSL Python 要求 3.8+，依赖 PyYAML、Jinja2、matplotlib。HTML 交互不增加第三方 JS 或联网依赖。

其他机器先安装对应的 Linux 环境，再在 Linux / WSL 的项目根目录安装平台并登记求解器：

~~~bash
python3 -m pip install -e .
python3 -m simtest setup \
  --solver OpenFOAM \
  --version 12 \
  --path /opt/openfoam12 \
  --environment script \
  --environment-script /opt/openfoam12/etc/bashrc

python3 -m simtest setup \
  --solver OpenFOAM \
  --version 2506 \
  --path /usr/lib/openfoam/openfoam2506 \
  --environment script \
  --environment-script /usr/lib/openfoam/openfoam2506/etc/bashrc \
  --path-prepend /opt/paraviewopenfoam510/bin
~~~

OpenCFD 的 bashrc 不包含 ParaView，需用 `--path-prepend` 把 `pvpython` 加入环境；否则场读取阶段会报告找不到 `pvpython`。

`config.yaml` 只保存安装和环境，并在 `.gitignore` 中忽略。替换已登记安装时显式加 `--force`，平台写入前会探测实际版本。日常直接使用 `python3 -m simtest`，安装包后也可在同一 Linux 环境使用 `simtest`。

使用普通安装的命令入口时，显式指定案例库所在的工程根目录，例如 `simtest --root /实际工程路径 list cases`。在源码根目录执行 `python3 -m simtest` 时会自动使用该目录。

### 常见现象

| 现象 | 判断 / 处理 |
|---|---|
| `No module named simtest` | 确认已进入 Linux / WSL 的工程根目录，并使用正确的 Python 环境；按首次配置说明安装项目。 |
| 命令中的作业 ID 报错 | 不输入尖括号占位符，用 `list runs` 的真实 ID，按 `list runs` 输出填写。 |
| WSL 提示 localhost 代理未镜像 | 来自 WSL 的代理提示。若已正常返回结果，不表示案例识别失败。本地仿真和离线报告无需外网。 |
| 只列出一个案例 | 当前仓库只提供一个示例案例，属于预期；`list solvers` 会列出已登记的两个分支版本。 |
| prepare-only 返回 QUEUED | 输入已准备，未启动求解；重新执行普通 run 进行计算。 |
| report 提示未归档 | 用 `list runs` 查找真实归档 ID；仅准备的作业无法生成结果报告。 |
| report 提示哈希不匹配 | 归档文件被修改或局部删除；恢复完整归档；相同身份不会覆盖损坏归档，不要修改清单掩盖损坏。 |

### 当前能力边界

当前 OpenFOAM Adapter 支持 `icoFoam` 和 `simpleFoam`，由案例模板 `controlDict` 的 `application` 选择；模板指定其他 application 时明确拒绝。

已验证 Foundation 12 与 OpenCFD 2506、单流体域、同格式 polyMesh、层流稳态、serial 后端及 MPI。OpenMP / CUDA 在运行前返回 `UNSUPPORTED`。

AICFD-NewPre 当前未安装。CGNS / MSH 跨格式路径明确返回 `MeshConversionError`；多域同字段归档、张量参考和跨网格插值仍需扩展及真实样本验证。跨分支不能比较版本新旧，`OpenFOAM@latest` 同时存在两个分支时明确报歧义。

参考表达式使用受限解析器；单位服务支持常用乘法型 SI / 前缀单位。未知单位、带偏置温标和未知数据结构明确拒绝。无可读 Git commit 时记录原因，并保留源码及输入 SHA-256。

## 开发验证

在 Linux / WSL 的项目根目录执行：

~~~bash
python3 -m unittest discover -s tests -v
~~~

测试覆盖公共模板布局、Adapter 读取方法重载、非 icoFoam 安装绑定、自定义版本排序、跨分支版本选择及环境隔离，覆盖 CLI 默认参数和映射校验、工况选择、失败作业报告、准备模式、参数与单位、模板、受限表达式、版本规则、监控边界与坏值、矢量误差、归档损坏、失败数据保留、进程组超时、原生 Reader 与导出回退，以及 HTML 报告分组和安全嵌入。

另提供可选浏览器回归脚本（Node 22+，默认使用 Windows 已安装的 Edge）。这项检查在 **Windows PowerShell 的工程根目录** 单独执行，平台运行命令仍在 Linux / WSL 执行：

~~~powershell
# 将路径替换为本次命令输出的 report.html 实际路径
node .\tests\report\check_html_report.cjs "报告的实际路径"
~~~
