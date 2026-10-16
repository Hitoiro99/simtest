# 项目功能状态与变更记录

需求依据：[流体结构数值模拟软件自动测试系统方案.md](流体结构数值模拟软件自动测试系统方案.md)。

## 记录规则

- 本文件只用于保存功能状态和文件操作记录。
- 状态使用：已实现、部分实现、未实现；已实现但示例未使用不算未实现。
- 每次完成一批代码修改后，在文档尾部追加一条记录，包括日期、目的、操作和验证结果。
- 文件操作注明仓库相对路径：修改写文件路径；新增/删除列出文件；移动/重命名写 `原路径 → 新路径`。没有发生的操作写“无”，目录批量操作需说明范围。
- 历史记录不覆盖、不删除；未执行的修改和测试不能写成已完成。
- 此后按上述规则追加。

## 功能状态


| 功能 | 状态 | 当前范围或缺口 |
|---|---|---|
| 案例、工况发现和参数解析 | 部分实现 | 类型、必填项、单位和派生变量已有；CLI 校验补齐默认执行参数并检查案例映射，零工况明确报错；通用取值范围约束未实现 |
| 标签检索、案例依赖、通用取值范围约束 | 未实现 | 标签仅作为元数据保存 |
| 求解器注册与版本选择 | 部分实现 | 注册机制已有；通用部署校验仍依赖 icoFoam/Foundation |
| OpenFOAM Foundation 12 接入 | 已实现 | 当前案例的串行及两进程 MPI；其他版本未完成真实验证 |
| Fluent、StarCCM、AICFD 和结构求解器 | 未实现 | 尚未接入 |
| 模板选择、继承与输入生成 | 部分实现 | 当前 OpenFOAM 路径可用；仍限定 0/constant/system |
| 唯一源网格、复制哈希和 checkMesh | 已实现 | 当前 polyMesh 网格 |
| AICFD-NewPre 转换及多域核验 | 未实现 | 跨格式和完整多域链路未接入 |
| Linux/WSL 本地执行 | 已实现 | 进入 Linux/WSL 后直接使用 python3 -m simtest，安装后也可用 simtest；保留日志、超时、取消和资源统计 |
| 容器、集群调度及集成多作业调度 | 未实现 | 当前 CLI 按顺序组织多工况/多求解器作业 |
| OpenMP/CUDA 求解后端 | 未实现 | 当前 Adapter 在启动前返回 UNSUPPORTED；MPI 已支持 |
| 监控和残差 CSV 标准化 | 部分实现 | 当前 OpenFOAM 读取器保留采样边界和无效值；其他求解器读取器未接入 |
| 场结果标准化 | 部分实现 | 当前单域、reference 所需场的全部输出时刻；多域同字段及张量未覆盖 |
| 标量监控及解析场参考比较 | 已实现 | 当前案例仅配置速度场参考；输出误差，不作数值 PASS/FAIL 判定 |
| 基线、性能及跨网格离散场比较 | 未实现 | 现有资源记录和曲线叠加不等于自动比较 |
| HTML 交互与 JSON/CSV、静态图报告 | 部分实现 | 交互和各格式输出已有；当前从 manifest 取数，尚未满足文档的 CSV/VTU 读取要求 |
| 报告直接读取归档 CSV/VTU | 未实现 | 当前使用已保存的监控与比较记录，不重算误差 |
| 输入、日志、标准结果及元数据归档 | 已实现 | 校验哈希；成功后默认清理 work，失败保留现场 |
| 运行副本清理与去重 | 部分实现 | runs 中的 input/logs/normalized 仍与归档重复 |
| 硬件和资源信息 | 部分实现 | CPU、OS、MPI、进程/线程数、耗时和峰值内存已有；完整内存配置、GPU、配额及多节点信息待补 |
| 案例网格制备与报告测试归位 | 已实现 | 网格制备位于案例 mesh-preparation/；浏览器测试位于 tests/report/；空 tools/ 已移除 |
| 平台代码按职责拆分 | 已实现 | 根目录 simtest.py 作为入口；案例、执行、后处理、报告、存储和公共工具分别位于同级目录；保持原 CLI 协议 |
| 项目代码风格与可读性约定 | 已实现 | AGENTS.md 已记录用户最终入口样式；受维护的 Python、JavaScript/CJS、CSS 及测试已统一，复杂条件式展开，保留简单值选择及用户最终入口排版 |
| 项目 AGENTS.md 工作规则 | 已实现 | 根目录文档维护目录、测试和 Linux/WSL 入口规则；solvers/ 位置保持不变 |

## 变更记录

每条记录只使用以下字段：**日期/目的、操作、验证**，不记录功能状态。代码修改与当次 STATUS.md 更新都列入文件操作；失败、跳过或未执行的验证如实注明。

### 001｜2026-10-15｜建立状态文档

- 操作：新增 `STATUS.md`；修改、删除、移动/重命名其他文件：无。
- 验证：读取需求、代码和已有元数据，检查文档链接；未运行测试或模拟。

### 002｜2026-10-15｜简化文档并规定追加记录

- 操作：修改 `STATUS.md`，精简为功能状态表和变更记录，删除文档中的详细方案、目录草图及重复说明；新增、删除、移动/重命名文件：无。
- 验证：检查文本、需求链接和文件变更范围；未运行测试或模拟。

### 003｜2026-10-15｜明确状态定义及更新方式

- 操作：修改 `STATUS.md` 的记录规则和功能表说明；新增、删除、移动/重命名文件：无。
- 验证：检查状态用词、表格更新与记录追加规则及文件变更范围；未运行测试或模拟。

### 004｜2026-10-15｜按职责迁移 tools 文件

- 操作：移动 `tools/create_example_mesh.py → cases/shear-decay-2d/mesh-preparation/create_example_mesh.py`，修正工程根目录及相邻 blockMeshDict 的定位，保持原有命令、生成内容和防覆盖行为。
- 操作：移动 `tools/blockMeshDict → cases/shear-decay-2d/mesh-preparation/blockMeshDict`；移动 `tools/check_html_report.cjs → tests/report/check_html_report.cjs`，两文件内容不变。
- 操作：新增目录 `cases/shear-decay-2d/mesh-preparation/`、`tests/report/`，移除迁空的 `tools/`；修改 `README.md`、`cases/shear-decay-2d/README.md`、`AGENTS.md` 的路径与职责说明，更新 `STATUS.md` 并追加本记录。
- 操作：浏览器回归生成/更新临时截图 `.inspection/report-chart.png`、`.inspection/report-desktop.png`；没有改动现有源网格、追溯、测试夹具、runs 或 artifacts 文件。
- 验证：WSL Ubuntu / Python 3.8.10 下现有 20 项 unittest 全部通过，无跳过；CLI 仍发现 shear-decay-2d/default。迁移后的网格脚本在隔离临时工作区、非工程当前目录下成功生成 128 单元、330 节点网格，检查 Mesh OK、追溯哈希和再次运行拒绝覆盖均通过。
- 验证：Node 24.21.0 / 已安装 Edge 从新路径完成固定报告的 14 项浏览器检查，JavaScript 异常为 0；浏览器脚本和网格定义文件迁移前后哈希一致。源网格、mesh-provenance、tests/fixtures、runs、artifacts 的文件数量及目录哈希摘要前后一致；本次未执行正式求解作业或重写历史归档。

### 005｜2026-10-15｜移除 PowerShell 包装入口

- 操作：删除根目录 `simtest.ps1`；修改 `README.md`，补充先进入 WSL 再切换工程目录的步骤，将平台命令和最新报告查找改为 Linux 用法，移除过时的脚本执行策略及包装器提示。浏览器回归仍明确在 Windows PowerShell 单独执行。
- 操作：修改 `AGENTS.md` 的入口说明；更新 `STATUS.md` 功能表并追加本记录。新增文件、移动/重命名：无；Python 核心、案例、测试及历史数据未修改。
- 验证：WSL Ubuntu 下 `test_report.py` 的 5 项 CLI/报告测试全部通过，无跳过；实际执行 list cases、list solvers、validate shear-decay-2d、list runs --case shear-decay-2d 均成功。
- 验证：README 的 9 个 Bash 代码块语法和 12 条 CLI 示例参数解析通过，最新报告查找命令返回现有 HTML；活动文档已无旧包装入口及执行策略引用，差异格式检查通过。simtest、solvers、cases、tests、runs、artifacts 的文件数量及目录哈希摘要前后一致；未运行正式求解、生成新报告或重跑浏览器回归。

### 006｜2026-10-16｜按职责拆分平台代码

- 操作：移动 `simtest/cli.py → simtest.py`；`simtest/{cases.py,templates.py} → case_management/`；`simtest/{runner.py,environment.py} → execution/`；`simtest/{analysis.py,vtk_bridge.py} → postprocessing/`；`simtest/{report.py,report_html.py,report_assets/} → reporting/`；`simtest/archive.py → storage/archive.py`；`simtest/{io.py,units.py,expression.py} → common/`；`simtest/__init__.py → common/version.py`。新增六个职责目录的 `__init__.py`；删除旧 `simtest/__main__.py` 及迁空目录中的字节码缓存。
- 操作：修改 `simtest.py`、`execution/runner.py`、迁移文件的导入，以及 `solvers/OpenFOAM/{adapter.py,fields.py,monitors.py}`、`cases/shear-decay-2d/mesh-preparation/create_example_mesh.py`、`pyproject.toml`；调整默认入口路径、实际源码哈希范围、桥接脚本及包资源位置。
- 操作：修改 `tests/{test_core.py,test_integration.py,test_reader.py,test_report.py}` 的导入、mock 和桥接路径；修改 `README.md`、`AGENTS.md` 的模块职责及布局说明，更新 `STATUS.md` 功能表并追加本记录。源网格、固定样本及历史运行和归档未迁移。
- 验证：WSL Ubuntu / Python 3.8.10 下现有 20 项 unittest 全部通过，无跳过；实际执行 list cases、list solvers、validate shear-decay-2d、list runs --case shear-decay-2d 均成功。迁移前后报告 JS/CSS 文件哈希一致。
- 验证：在独立临时工作区完成串行、两进程 MPI 和 prepare-only；两个求解作业均为 SUCCEEDED，原生读取各覆盖 11 个场时刻，生成 HTML 并按原策略清理 work。检查新入口、七个包及报告资源的源码哈希覆盖；准备模式停在 QUEUED，不产生归档。
- 验证：使用临时打包工具在 Linux 离线构建 wheel，检查入口、新包、VTK 桥接和 JS/CSS 均已包含；临时非 editable 安装后，从源码目录外通过模块和控制台入口显式指定 --root，查询正常，普通 Python 未提前导入 VTK。安装版串行求解、原生读取及 HTML 生成通过。
- 验证：Node 24.21.0 / Edge 对安装版新生成的报告完成 14 项浏览器交互检查，JavaScript 异常为 0。临时工具、安装环境、求解工作区、报告及浏览器截图已清理；未新增项目依赖或修改全局 Python 环境。本次仅验证现有 OpenFOAM Foundation 12 示例，不代表其他内核或版本已接入。
- 验证：最终检查未发现活动代码中的旧模块路径，差异格式检查通过。源网格、mesh-provenance、tests/fixtures、runs、artifacts 的文件数量和 SHA-256 目录摘要与迁移前一致；原有用户改动保留。

### 007｜2026-10-16｜整理 CLI 格式并修复校验缺陷

- 操作：修改 `simtest.py`，统一缩进和空格、按子命令分组、展开多语句行及条件表达式，移除未使用的导入；保持参数名称、默认值和输出结构。validate 复用 execution_config 补齐默认值并向 Adapter 传入案例，修复默认参数 KeyError 和映射冲突漏检；run 优先识别零工况；根目录解析放入统一错误处理。
- 操作：新增 `tests/test_cli.py`，覆盖默认/部分执行参数、映射冲突、零工况、失败作业入报告及准备模式；修改 `README.md` 的测试数量与覆盖说明；更新 `STATUS.md` 功能表并追加本记录。删除、移动/重命名文件：无。
- 验证：修改前新测试复现两处参数 KeyError、映射冲突漏检及零工况误报；修复后 5 项 CLI 测试通过，WSL Ubuntu / Python 3.8.10 下完整 25 项 unittest 全部通过，无跳过。
- 验证：比对各子命令的参数定义、选项及默认值，保持一致；AST 检查 simtest.py 无三元表达式。实际执行 list cases、list solvers、validate shear-decay-2d、list runs --case shear-decay-2d 均成功；零、负数、nan、inf 和非数字超时参数均被拒绝。未执行完整求解、浏览器回归或重新打包；现有读取器及归档测试已执行。

### 008｜2026-10-16｜按用户最终入口样式统一代码

- 操作：修改 `AGENTS.md` 第五部分，记录缩进、单行语句、短调用、数据结构、逻辑分段、条件表达式及前端规则；保持用户最终修改的 `simtest.py` 原样。
- 操作：统一 `case_management/{cases.py,templates.py}`、`common/{expression.py,io.py,units.py,version.py}`、`execution/{environment.py,runner.py}`、`storage/archive.py` 的格式；展开复杂路径/读取和异常状态条件式，保留原求值顺序及调用次数。
- 操作：统一 `solvers/{base.py,exceptions.py,models.py,registry.py}`、`solvers/OpenFOAM/{adapter.py,fields.py,monitors.py}`、`postprocessing/{analysis.py,vtk_bridge.py}`、`cases/shear-decay-2d/mesh-preparation/create_example_mesh.py` 的格式，等价展开复杂条件式。
- 操作：统一 `reporting/{report.py,report_html.py}`、`reporting/report_assets/{report.js,report.css}`、`tests/report/check_html_report.cjs` 和 `tests/{test_cli.py,test_core.py,test_integration.py,test_reader.py,test_report.py}`；JavaScript 独立语句及控制块分行、CSS 声明逐行，展开嵌套条件式；更新 `STATUS.md` 功能表并追加本记录。本次共调整 29 个代码文件和 2 个文档；新增、删除、移动/重命名文件：无。
- 验证：36 个受维护 Python 文件均通过语法和格式检查，其中 25 个 AST 与修改前一致，11 个为明确分支展开；未发现嵌套三元表达式、分号串联或单行复合语句，保留 20 个简单条件表达式。simtest.py 逐字节相同；案例输入、网格、追溯、固定样本及历史 runs/artifacts 共 1,426 个文件的哈希与修改前一致。
- 验证：WSL Ubuntu / Python 3.8.10 下 25 项 unittest 全部通过，无跳过；六份现有归档的前后图表、汇总表、内嵌数据及 HTML 正文一致；五类异常分别覆盖归档成功/失败共 10 种情形，状态、历史及诊断一致。
- 验证：JavaScript/CJS 语法通过，前端等价抽样 1,257 组通过；独立临时工作区的串行和两进程 MPI 均为 SUCCEEDED，原生读取各覆盖 11 个时刻并生成 HTML，清理策略保持一致。Node 24.21.0 / Edge 对新生成合并报告的 14 项交互检查通过，JavaScript 异常为 0。
- 验证：最终差异格式检查通过；未重新打包或验证其他求解器/版本。临时格式工具、备份、求解目录、报告和截图在交付前清理，不向项目新增依赖或改动全局环境。
