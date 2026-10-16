# 数值模拟软件自动测试系统

把案例输入交给已登记的求解器，自动完成准备、计算、结果标准化、解析解比较和 **HTML 交互报告**。

当前已验证：**WSL Ubuntu + OpenFOAM Foundation 12 + shear-decay-2d/default**，支持串行及两个 MPI 进程。系统不设置数值通过阈值；`SUCCEEDED` 表示执行和必需结果完整。

## 从这里开始

- [日常使用](#日常使用)：查看案例 → 校验 → 运行 → 打开报告。
- [报告怎么看](#报告怎么看)：曲线操作、数值含义和数据下载。
- [目录与运行流程](#目录与运行流程)：各部分职责。
- [首次配置与排错](#首次配置与排错)：其他机器部署、Linux 和 WSL 常见提示。

现有报告可直接用浏览器打开：

| 报告 | 作业范围 |
|---|---|
| [正式验证 HTML](artifacts/shear-decay-2d/reports/20261013T080759Z-d8ae69e0/report.html) | 正式串行与两进程 MPI，共 2 次 |
| [后续运行 HTML](artifacts/shear-decay-2d/reports/20261013T081125Z-47ae3c03/report.html) | 用户后续运行，共 4 次 |

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
python3 -m simtest validate shear-decay-2d
~~~

| 命令 | 结果含义 |
|---|---|
| `list cases` | 扫描 `cases/` 下符合结构的案例和工况。当前只有 `shear-decay-2d/default`，因此只显示一项是正常的。 |
| `list solvers` | 列出代码中登记的 Adapter 版本，当前为 OpenFOAM 12；不是扫描机器上所有安装。 |
| `validate` | 检查案例、工况、模板与实际安装版本；返回 `valid: true` 后可运行。 |

### 2. 运行

~~~bash
# 串行计算；完成后自动生成本次作业的 HTML 报告
python3 -m simtest run shear-decay-2d

# 两个 MPI 进程；自动分区并重构全部已保存时刻
python3 -m simtest run shear-decay-2d --processes 2

# 调试时保留求解器原生结果
python3 -m simtest run shear-decay-2d --keep-raw
~~~

每次运行创建独立作业 ID 和目录，不覆盖已有作业。默认在标准化检查及归档完整性检查均成功后清理该作业的 `work/`；失败时保留原生结果。

只准备输入、暂不计算：

~~~bash
python3 -m simtest run shear-decay-2d --prepare-only
~~~

此时输出 `QUEUED` 表示准备完成，**没有后台队列继续运行**，也没有已归档结果可生成报告。要实际计算，重新执行不带 `--prepare-only` 的 `run`，将创建新作业。

需要调整超时：

~~~bash
python3 -m simtest run shear-decay-2d --timeout 300 --heartbeat-timeout 120
~~~

单位为秒；心跳超时指原生日志长时间没有进度输出。Ctrl+C 会终止受监督的求解器进程组。

### 3. 查看作业 ID，重新生成报告

~~~bash
# 查看已归档作业的真实 ID、工况、进程数、状态和时间
python3 -m simtest list runs --case shear-decay-2d

# 汇总两次正式验证；这两个 ID 已在当前仓库保留
python3 -m simtest report shear-decay-2d --job-id 0049661a44a93dfc51bb3ff1 --job-id 0b80aa28a4cb5fe15eb630ca

# 汇总本案例当前保留的全部归档（包含失败作业）
python3 -m simtest report shear-decay-2d
~~~

`report` 只读取并校验归档，不启动求解器。可以重复指定 `--job-id` 选取多次作业。选择同一目的、可比较的运行集合，避免混合不同开发阶段的结果。

**不要原样输入 `<job-id>`。** 它是说明中的占位符，尖括号在 shell 中有特殊含义。请用 `list runs` 输出中的真实 ID 替换，像上面示例那样直接填写。

### 4. 打开最新报告(待添加新功能)

在 Linux / WSL 中查找最新报告：

~~~bash
python3 - <<'PY'
from pathlib import Path

reports = list(Path("artifacts/shear-decay-2d/reports").glob("*/report.html"))
if reports:
    print(max(reports, key=lambda path: path.stat().st_mtime).resolve())
else:
    print("暂无报告，请先运行计算或生成报告。")
PY
~~~

使用浏览器打开输出的 HTML 文件。原生 Linux 图形环境可使用文件管理器打开；WSL 中的 `/mnt/c/...` 对应 Windows 的 `C:\...`，可在 Windows 文件资源管理器中双击 `report.html`。也可在 WSL 执行 `explorer.exe .` 打开当前工程目录，再进入 `artifacts/shear-decay-2d/reports/`。

## 报告查看

HTML 的图表数据、样式和交互脚本全部内嵌，**无需联网、无需启动 Web 服务**。

| 操作 | 用法 |
|---|---|
| 放大 / 缩小 | 滚轮，或图表上方的“放大 +”“缩小 −”按钮 |
| 查看局部 | 在图内拖动框选 |
| 移动视区 | 点击“平移”，再拖动；再次点击回到框选 |
| 恢复全貌 | 双击图表或点击“重置” |
| 查看具体值 | 鼠标悬停在曲线采样点附近 |
| 显示 / 隐藏曲线 | 点击图例；重合曲线可逐条查看 |
| 线性 / 对数坐标 | 切换 Y 轴；对数轴不能显示零和负数，页面会提示数量 |
| 查看不同误差指标 | 场误差图可切换最大值、均值、RMS，以及绝对 / 归一化误差 |
| 放大工作区 / 导出 | 使用“全屏”或“导出当前 SVG” |
| 查找数值 | 在“数值明细”输入作业 ID、字段、分量或状态 |

报告包括作业状态、诊断、完整监控曲线、场误差、末条监控记录、参考来源和数据下载。曲线展示各工况 / 求解器所选作业中的最新实际版本；状态和明细保留全部所选作业。

阅读时注意：

- 保留全部采样点。无效值产生断点，不平滑、不插值、不前向填充；最后记录无效时不回退到较早有效值。
- 本例残差是**每个时间步首个线性求解的初始残差**。原生日志保留完整校正器记录；不能单凭这条曲线认定整个瞬态过程已收敛。
- 场误差按各实际保存时刻计算，均值和 RMS 按单元体积加权；矢量模长误差为两个模长之差的绝对值。
- 归一化误差以百分比显示，归一化尺度不是容差。`UNAVAILABLE` 或“—”不等于零。
- 默认轴范围避免把近似常数的浮点扰动画成大幅变化；可自行缩放查看细节。

每份报告目录包含：

~~~text
report.html     浏览器阅读与交互入口
summary.csv     监控末条记录与比较数据，包含完整 job_id
summary.json    完整作业元数据、全部比较、单位、来源和诊断
figures/        默认视图的 PNG、SVG、PDF
~~~

单独复制 HTML 仍可交互查看内嵌数据；要使用下载和来源链接，应保留报告同目录文件及其相对归档路径。三维场可用 ParaView 打开归档中的 `normalized/fields/fields.pvd`。

## 目录与运行流程

| 位置 | 作用 | 什么时候使用 |
|---|---|---|
| `simtest.py` | 命令入口，解析参数并调用各业务模块 | 所有平台命令 |
| `config.yaml` | 本机求解器安装路径和环境配置 | 首次配置后由平台读取 |
| `cases/` | 案例物理定义、工况、模板、网格与参考解 | 所有计算的源输入 |
| `cases/<case-id>/mesh-preparation/` | 案例专属的源网格制备脚本和配置 | 显式制备网格时 |
| `case_management/` | `cases.py` 读取案例/工况；`templates.py` 选择、继承并物化模板 | 校验及准备阶段 |
| `solvers/` | Adapter、进程监督、OpenFOAM 执行及结果读取 | 网格预处理、求解、后处理 |
| `run_control/` | `install.py` 登记和选择已有安装；`environment.py` 加载环境及执行辅助命令；`jobs.py` 创建作业并组织各阶段 | setup / validate / run |
| `postprocessing/` | `analysis.py` 计算参考偏差；`vtk_bridge.py` 由 pvpython 独立执行场标准化 | 求解之后 |
| `reporting/` | `report.py` 组织报告；`report_html.py` 与 `report_assets/` 生成 HTML、图表及 CSV / JSON | run 结束或 report 命令 |
| `storage/` | `archive.py` 检查标准文件、校验归档哈希并控制原生数据清理 | 作业收尾及报告读取 |
| `common/` | 文件操作、表达式、单位换算与平台版本；不主动启动求解 | 各业务模块复用 |
| `cases/` | 案例物理定义、工况、模板、网格与参考解 | 所有计算的源输入 |
| `runs/` | 每次运行的输入快照、工作区、日志和状态 | 计算、失败排查 |
| `artifacts/` | 经校验的结果归档和派生报告 | 长期留存、比较、阅读 |
| `tests/` | 单元、Reader 及集成回归测试 | 修改代码后验证 |
| `tests/report/` | HTML 报告的浏览器交互回归 | 开发或专项检查 |

`simtest.py` 只负责命令入口；各同级业务目录使用轻量 Python 包组织导入。`solvers/` 继续独立保存内核行为，`cases/` 保存物理输入，`runs/` 和 `artifacts/` 保存数据。目录拆分不改变命令、数值定义及历史归档格式。

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
  → 按保留策略清理 work/
  → 生成 HTML 报告
~~~

场读取优先原生 OpenFOAM Reader，能力不满足时尝试 `foamToVTK`。本例归档速度、各分量、模长、体积和追溯 ID，压力等未用于参考比较的场不额外归档。

标准监控表采用 `step,time,各监控量` 的宽表。不同监控的采样位置留空。报告使用归档中的监控与比较结果，之后修改案例公式不会重算旧归档。

## 首个案例：shear-decay-2d

静止壁面之间的层流速度扩散，解析式为：

~~~text
Ux = A × sin(πy/H) × exp[-ν(π/H)²t]
Uy = Uz = 0
~~~

| 参数 | 当前设置 |
|---|---|
| 运动黏度 ν | 0.001 m²/s，案例常量 |
| 幅值 A | 0.1 m/s，default 工况变量 |
| 高度 H | 0.1 m，固定网格高度与参考参数 |
| 网格 | 128 单元、330 节点 |
| 时间 | 步长 0.001 s，终止 1 s，每 0.1 s 保存场 |

一个常量、一个变量、一个工况是示例选择；平台的字典和发现机制不限制数量。更换 A、物性或网格时，需要同步维护工况参考参数、参考来源和案例版本，避免比较不同物理条件。

唯一源网格为 `cases/shear-decay-2d/polyMesh/`。运行过程只复制并核验，不隐式重新生成源网格。`cases/shear-decay-2d/mesh-preparation/create_example_mesh.py` 与同目录 `blockMeshDict` 用于显式制备新网格，脚本拒绝覆盖已有源网格。

## 首次配置与排错

### 本机环境

当前项目已有安装登记：WSL Ubuntu、OpenFOAM Foundation 12、`/opt/openfoam12/etc/bashrc`，以及 ParaView 的 `pvpython`。WSL Python 要求 3.8+，依赖 PyYAML、Jinja2、matplotlib。HTML 交互不增加第三方 JS 或联网依赖。

其他机器先安装对应的 Linux 环境，再在 Linux / WSL 的项目根目录安装平台并登记求解器：

~~~bash
python3 -m pip install -e .
python3 -m simtest setup --solver OpenFOAM --version 12 \
  --path /opt/openfoam12 --environment script \
  --environment-script /opt/openfoam12/etc/bashrc
~~~

`config.yaml` 只保存安装和环境，并在 `.gitignore` 中忽略。替换已登记安装时显式加 `--force`，平台写入前会探测实际版本。日常直接使用 `python3 -m simtest`，安装包后也可在同一 Linux 环境使用 `simtest`。

使用普通安装的命令入口时，显式指定案例库所在的工程根目录，例如 `simtest --root /实际工程路径 list cases`。在源码根目录执行 `python3 -m simtest` 时会自动使用该目录。

### 常见现象

| 现象 | 判断 / 处理 |
|---|---|
| `No module named simtest` | 确认已进入 Linux / WSL 的工程根目录，并使用正确的 Python 环境；按首次配置说明安装项目。 |
| 命令中的作业 ID 报错 | 不输入尖括号占位符，用 `list runs` 的真实 ID，见前面的双作业示例。 |
| WSL 提示 localhost 代理未镜像 | 来自 WSL 的代理提示。若已正常返回结果，不表示案例识别失败。本地仿真和离线报告无需外网。 |
| 只列出一个案例 / 一个版本 | 当前仓库只提供一个示例案例和 Foundation 12 Adapter，属于预期。 |
| prepare-only 返回 QUEUED | 输入已准备，未启动求解；重新执行普通 run 进行计算。 |
| report 提示未归档 | 用 `list runs` 查找真实归档 ID；仅准备的作业无法生成结果报告。 |
| report 提示哈希不匹配 | 归档文件被修改或局部删除；恢复完整归档或重新运行，不要修改清单掩盖损坏。 |

### 当前能力边界

已验证 Foundation 12、单流体域、同格式 polyMesh、层流瞬态、serial 后端及 MPI。OpenMP / CUDA 在运行前返回 `UNSUPPORTED`。

AICFD-NewPre 当前未安装。CGNS / MSH 跨格式路径明确返回 `MeshConversionError`；其他 OpenFOAM 分支、多域同字段归档、张量参考和跨网格插值仍需扩展及真实样本验证。Foundation 整数版本与 OpenCFD vYYMM 不能混排。

参考表达式使用受限解析器；单位服务支持常用乘法型 SI / 前缀单位。未知单位、带偏置温标和未知数据结构明确拒绝。无可读 Git commit 时记录原因，并保留源码及输入 SHA-256。

## 开发验证

在 Linux / WSL 的项目根目录执行：

~~~bash
python3 -m unittest discover -s tests -v
~~~

当前 25 项测试通过，覆盖 CLI 默认参数和映射校验、工况选择、失败作业报告、准备模式、参数与单位、模板、受限表达式、版本规则、监控边界与坏值、矢量误差、归档损坏、失败数据保留、进程组超时、原生 Reader 与导出回退，以及 HTML 报告分组和安全嵌入。

另提供可选浏览器回归脚本（Node 22+，默认使用 Windows 已安装的 Edge）。这项检查在 **Windows PowerShell 的工程根目录** 单独执行，平台运行命令仍在 Linux / WSL 执行：

~~~powershell
node .\tests\report\check_html_report.cjs .\artifacts\shear-decay-2d\reports\20261013T080759Z-d8ae69e0\report.html
~~~
