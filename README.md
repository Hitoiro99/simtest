# 数值模拟软件自动测试系统

把案例输入交给已登记的求解器，自动完成准备、计算、结果标准化、解析解比较和 **HTML 交互报告**。

当前已验证：**WSL Ubuntu + OpenFOAM Foundation 12 + shear-decay-2d/default**，支持串行及两个 MPI 进程。系统不设置数值通过阈值；`SUCCEEDED` 表示执行和必需结果完整。

## 从这里开始

- [日常使用](#日常使用)：查看案例 → 校验 → 运行 → 打开报告。
- [报告怎么看](#报告怎么看)：曲线操作、数值含义和数据下载。
- [目录与运行流程](#目录与运行流程)：各部分职责。
- [首次配置与排错](#首次配置与排错)：其他机器部署、PowerShell 和 WSL 常见提示。
- [验证记录](VALIDATION.md)：正式串行 / MPI 计算证据与能力范围。

现有报告可直接用浏览器打开：

| 报告 | 作业范围 |
|---|---|
| [正式验证 HTML](artifacts/shear-decay-2d/reports/20261013T080759Z-d8ae69e0/report.html) | 正式串行与两进程 MPI，共 2 次 |
| [后续运行 HTML](artifacts/shear-decay-2d/reports/20261013T081125Z-47ae3c03/report.html) | 用户后续运行，共 4 次 |

## 日常使用

在本项目目录打开 PowerShell。以下命令均使用真实案例名称，可以直接复制。

### 1. 查看并校验

~~~powershell
.\simtest.ps1 list cases
.\simtest.ps1 list solvers
.\simtest.ps1 validate shear-decay-2d
~~~

| 命令 | 结果含义 |
|---|---|
| `list cases` | 扫描 `cases/` 下符合结构的案例和工况。当前只有 `shear-decay-2d/default`，因此只显示一项是正常的。 |
| `list solvers` | 列出代码中登记的 Adapter 版本，当前为 OpenFOAM 12；不是扫描机器上所有安装。 |
| `validate` | 检查案例、工况、模板与实际安装版本；返回 `valid: true` 后可运行。 |

### 2. 运行

~~~powershell
# 串行计算；完成后自动生成本次作业的 HTML 报告
.\simtest.ps1 run shear-decay-2d

# 两个 MPI 进程；自动分区并重构全部已保存时刻
.\simtest.ps1 run shear-decay-2d --processes 2

# 调试时保留求解器原生结果
.\simtest.ps1 run shear-decay-2d --keep-raw
~~~

每次运行创建独立作业 ID 和目录，不覆盖已有作业。默认在标准化检查及归档完整性检查均成功后清理该作业的 `work/`；失败时保留原生结果。

只准备输入、暂不计算：

~~~powershell
.\simtest.ps1 run shear-decay-2d --prepare-only
~~~

此时输出 `QUEUED` 表示准备完成，**没有后台队列继续运行**，也没有已归档结果可生成报告。要实际计算，重新执行不带 `--prepare-only` 的 `run`，将创建新作业。

需要调整超时：

~~~powershell
.\simtest.ps1 run shear-decay-2d --timeout 300 --heartbeat-timeout 120
~~~

单位为秒；心跳超时指原生日志长时间没有进度输出。Ctrl+C 会终止受监督的求解器进程组。

### 3. 查看作业 ID，重新生成报告

~~~powershell
# 查看已归档作业的真实 ID、工况、进程数、状态和时间
.\simtest.ps1 list runs --case shear-decay-2d

# 汇总两次正式验证；这两个 ID 已在当前仓库保留
.\simtest.ps1 report shear-decay-2d --job-id 0049661a44a93dfc51bb3ff1 --job-id 0b80aa28a4cb5fe15eb630ca

# 汇总本案例当前保留的全部归档（包含失败作业）
.\simtest.ps1 report shear-decay-2d
~~~

`report` 只读取并校验归档，不启动求解器。可以重复指定 `--job-id` 选取多次作业。选择同一目的、可比较的运行集合，避免混合不同开发阶段的结果。

**不要原样输入 `<job-id>`。** 它是占位符；PowerShell 会把 `<` 当作语法符号，命令尚未进入程序便报错。请用 `list runs` 输出中的真实 ID 替换，像上面示例那样直接填写。

### 4. 打开最新报告

~~~powershell
$latestReport = Get-ChildItem .\artifacts\shear-decay-2d\reports\*\report.html |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($latestReport) { Invoke-Item $latestReport.FullName }
~~~

也可以在文件资源管理器中双击 `report.html`。终端输出中的 `/mnt/c/...` 是 WSL 路径，对应 Windows 的 `C:\...`。

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
| `simtest.ps1` | Windows → WSL 入口及路径转换 | PowerShell 执行命令时 |
| `simtest/cli.py` | 解析命令，组织校验、运行、报告 | 所有命令 |
| `simtest/cases.py`、`templates.py` | 读取案例与工况，检查参数，物化模板 | 准备阶段 |
| `simtest/runner.py` | 安装探测、作业隔离、运行调度与收尾 | setup / validate / run |
| `solvers/` | Adapter、进程监督、OpenFOAM 执行及结果读取 | 网格预处理、求解、后处理 |
| `simtest/analysis.py`、`expression.py`、`units.py` | 参考式求值、单位换算及偏差计算 | 标准化之后 |
| `simtest/archive.py` | 标准文件检查、归档哈希和原生数据清理边界 | 作业收尾及报告读取 |
| `simtest/report*.py`、`report_assets/` | HTML、静态图、CSV / JSON 报告 | run 结束或 report 命令 |
| `cases/` | 案例物理定义、工况、模板、网格与参考解 | 所有计算的源输入 |
| `config.yaml` | 本机求解器安装路径和环境配置 | 首次配置后由平台读取 |
| `runs/` | 每次运行的输入快照、工作区、日志和状态 | 计算、失败排查 |
| `artifacts/` | 经校验的结果归档和派生报告 | 长期留存、比较、阅读 |
| `tests/` | 单元、Reader 及集成回归测试 | 修改代码后验证 |
| `tools/` | 显式网格制备等辅助工具 | 开发或专项检查 |
| `VALIDATION.md` | 已完成验证的证据与范围 | 判断当前实现能力 |

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

## 哪些可以删除

| 内容 | 是否可删 | 影响与做法 |
|---|---|---|
| 不需要的 `artifacts/.../reports/报告ID/` | 可以 | 派生产物；保留源归档就能重新生成。按整个报告目录删除。 |
| 不再需要的 `artifacts/.../runs/.../作业ID/` | 可以，但需确定不再保留该证据 | 按整个作业目录删除；之后无法用该 ID 重建报告。保留正式验证及当前关注的运行。 |
| 归档内单独的 `logs/`、`input/`、`normalized/` | 不应单独删除 | 都在哈希清单中；局部删除会使归档完整性校验失败。 |
| `runs/作业ID/work/` | 已确认成功归档后可以 | 默认已自动清理；`--keep-raw` 保留者删除后无法再检查完整原生场。失败作业先保留排查。 |
| 已完成且成功归档的整个 `runs/作业ID/` | 可在确认无需现场排查后删除 | 归档是独立副本；准备中、运行中或失败现场不要作为重复文件处理。 |
| `__pycache__/`、`.inspection/` | 可以 | Python 缓存、临时检查产物可再生成。 |
| `cases/`、`simtest/`、`solvers/`、`config.yaml` | 保留 | 源输入、代码及本机配置。 |
| `cases/.../mesh-provenance/` | 保留 | 源网格制备与检查证据，不是普通重复日志。 |
| `tests/fixtures/` 等测试样本 | 保留 | Reader 回归所需数据，不是过期仿真结果。 |

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

唯一源网格为 `cases/shear-decay-2d/polyMesh/`。运行过程只复制并核验，不隐式重新生成源网格。`tools/create_example_mesh.py` 用于显式制备新网格。

## 首次配置与排错

### 本机环境

当前项目已有安装登记：WSL Ubuntu、OpenFOAM Foundation 12、`/opt/openfoam12/etc/bashrc`，以及 ParaView 的 `pvpython`。WSL Python 要求 3.8+，依赖 PyYAML、Jinja2、matplotlib。HTML 交互不增加第三方 JS 或联网依赖。

其他机器先安装上述环境，再在 WSL 的项目目录登记：

~~~bash
python3 -m pip install -e .
python3 -m simtest setup --solver OpenFOAM --version 12 \
  --path /opt/openfoam12 --environment script \
  --environment-script /opt/openfoam12/etc/bashrc
~~~

`config.yaml` 只保存安装和环境，并在 `.gitignore` 中忽略。替换已登记安装时显式加 `--force`，平台写入前会探测实际版本。WSL 中也可直接使用 `python3 -m simtest`，安装包后可用 `simtest`。

### 常见现象

| 现象 | 判断 / 处理 |
|---|---|
| PowerShell 报“< 运算符是为将来使用而保留的” | 用真实 ID 替换占位符，见前面的双作业示例。 |
| PowerShell 报“禁止运行脚本” | 对本次调用使用下面的进程级命令；无需永久更改系统策略。 |
| WSL 提示 localhost 代理未镜像 | 来自 WSL 的代理提示。若已正常返回结果，不表示案例识别失败。本地仿真和离线报告无需外网。 |
| 同一代理提示出现两次 | 包装器分别调用 WSL 转换路径和执行 Python。 |
| 只列出一个案例 / 一个版本 | 当前仓库只提供一个示例案例和 Foundation 12 Adapter，属于预期。 |
| prepare-only 返回 QUEUED | 输入已准备，未启动求解；重新执行普通 run 进行计算。 |
| report 提示未归档 | 用 `list runs` 查找真实归档 ID；仅准备的作业无法生成结果报告。 |
| report 提示哈希不匹配 | 归档文件被修改或局部删除；恢复完整归档或重新运行，不要修改清单掩盖损坏。 |

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\simtest.ps1 list cases
~~~

### 当前能力边界

已验证 Foundation 12、单流体域、同格式 polyMesh、层流瞬态、serial 后端及 MPI。OpenMP / CUDA 在运行前返回 `UNSUPPORTED`。

AICFD-NewPre 当前未安装。CGNS / MSH 跨格式路径明确返回 `MeshConversionError`；其他 OpenFOAM 分支、多域同字段归档、张量参考和跨网格插值仍需扩展及真实样本验证。Foundation 整数版本与 OpenCFD vYYMM 不能混排。

参考表达式使用受限解析器；单位服务支持常用乘法型 SI / 前缀单位。未知单位、带偏置温标和未知数据结构明确拒绝。无可读 Git commit 时记录原因，并保留源码及输入 SHA-256。

## 开发验证

在 WSL 的项目目录执行：

~~~bash
python3 -m unittest discover -s tests -v
~~~

当前 20 项测试通过，覆盖参数与单位、模板、受限表达式、版本规则、监控边界与坏值、矢量误差、归档损坏、失败数据保留、进程组超时、原生 Reader 与导出回退，以及 HTML 报告分组和安全嵌入。

另提供可选浏览器回归脚本（Node 22+，默认使用 Windows 已安装的 Edge）：

~~~powershell
node .\tools\check_html_report.cjs .\artifacts\shear-decay-2d\reports\20261013T080759Z-d8ae69e0\report.html
~~~

该脚本使用隔离的临时无头浏览器配置，验证本例的四张图、交互、SVG 导出和窄屏布局。历史正式计算数据及其限制见 [VALIDATION.md](VALIDATION.md)。
