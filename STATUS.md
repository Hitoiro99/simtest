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
| 平台代码按职责拆分 | 已实现 | 根目录 simtest.py 作为入口；run_control 的 install/environment/jobs 分别负责安装、环境和作业；其余职责目录同级，保持原 CLI 协议 |
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

### 009｜2026-10-16｜分离求解器部署与作业管理

- 操作：拆分 `execution/runner.py → solver_deployment/installations.py、job_management/preparation.py、job_management/metadata.py、job_management/workflow.py、job_management/status.py`；移动 `execution/environment.py → solver_deployment/environment.py`。新增两个新包的 `__init__.py`，删除旧 `execution/__init__.py` 及迁空目录中的字节码缓存。
- 操作：安装登记、选择及环境辅助函数使用明确名称；作业准备与追溯分开，原内嵌 transition 移为显式接收 context/status 的状态记录函数，异常分类独立维护。修改 `pyproject.toml` 打包范围、`README.md` 与 `AGENTS.md` 的职责说明；更新 `STATUS.md` 功能表并追加本记录。
- 操作：同步 `simtest.py`、`solvers/OpenFOAM/adapter.py`、`tests/{test_cli.py,test_integration.py}` 和 `cases/shear-decay-2d/mesh-preparation/create_example_mesh.py` 的导入、调用及 mock 名称；保留入口原有排版，状态模块分别使用 create_job_status、record_job_state、classify_job_failure。
- 验证：WSL Ubuntu / Python 3.8.10 下完整 25 项 unittest 全部通过，无跳过；五个安装/环境函数的语法树在名称映射后与原实现一致，十种异常及归档失败情形的状态、历史和诊断一致。固定随机因子时，新旧作业 ID、身份及元数据一致，仅创建时间和对应实际源码的哈希按运行变化。
- 验证：临时离线构建 wheel 并进行非 editable 安装，从源码目录外验证模块和控制台入口；新包、报告资源及桥接脚本均包含，旧 execution 不再打包，普通导入不加载 VTK。安装版 setup、validate、prepare-only、串行和两进程 MPI 全部通过；求解各保留 11 个场时刻，新包源码哈希、HTML 生成和清理策略正常。
- 验证：Node 24.21.0 / Edge 对安装版新生成合并报告的 14 项浏览器交互检查通过，JavaScript 异常为 0；旧包导入与 mock 路径已清除，格式检查通过。案例输入、网格、固定样本、追溯及历史 runs/artifacts 共 1,426 个受保护文件的哈希保持一致。
- 验证：临时工具、安装环境、备份、求解目录及报告截图在交付前清理；未改动全局环境、本机 config.yaml、数值算法或历史归档。未接入或验证其他求解器/版本，原有通用部署能力缺口保持原状态。

### 010｜2026-10-16｜回退 execution 职责拆分

- 操作：按用户指定撤销记录 009 对应的结构与命名修改，恢复 `execution/{__init__.py,runner.py,environment.py}`，移除拆分产生的 `solver_deployment/`、`job_management/` 八个 Python 文件及缓存；恢复原函数名和内嵌 transition。
- 操作：还原 `simtest.py`、`solvers/OpenFOAM/adapter.py`、`tests/{test_cli.py,test_integration.py}`、`cases/shear-decay-2d/mesh-preparation/create_example_mesh.py` 的相关导入、调用和 mock，以及 `pyproject.toml`、`README.md`、`AGENTS.md` 的目录说明。保留后来新增的审批、讨论和用户最新修改前暂存规则，以及 README 备注等其他改动。更新功能表并追加本记录，历史 001—009 保留。
- 操作：依据用户在回退过程中更新的规则，使用回退前快照执行 git add，暂存上次拆分涉及的版本作为检查点；排除后续规则和无关备注，工作区保留本次恢复结果。
- 验证：恢复后的 runner.py 为原 346 行，五个顶层函数及内嵌 transition 回到原位置；WSL Ubuntu / Python 3.8.10 下完整 25 项 unittest 全部通过，无跳过。实际 list cases、list solvers、validate 和 list runs 均成功。
- 验证：临时离线构建并安装 wheel，确认 execution 入包、两个拆分包不再入包，模块与控制台入口从源码目录外运行正常；安装版 prepare-only 停在 QUEUED，保留原状态历史，源码哈希恢复 execution 路径，无新增归档或报告。
- 验证：1,426 个受保护输入、网格、样本、追溯及历史 runs/artifacts 文件哈希不变；暂存区与选定的回退前快照一致，其他原有暂存内容未被覆盖。工作区与暂存检查点的差异格式检查通过。临时工具、备份及验证目录在交付前清理；本次未重新执行完整串行/MPI 求解或浏览器回归。

### 011｜2026-10-16｜以三个文件整理运行控制

- 操作：按确认方案拆分 `execution/runner.py → run_control/install.py、run_control/jobs.py`，移动 `execution/environment.py → run_control/environment.py`；以 `run_control/__init__.py` 替换旧包初始化文件，删除迁空的 `execution/`。安装登记、安装选择、环境加载、工具定位及作业准备分别改名为 register_install、select_install、load_env、find_tool、prepare_job；保留 run_capture、run_job，Git 辅助函数使用 _git_revision。
- 操作：在 `run_control/jobs.py` 内提取 _build_manifest；状态记录改名为 _record_state，继续作为 run_job 的内嵌函数，不另建状态模块。修改 `simtest.py`、`solvers/OpenFOAM/adapter.py`、`tests/{test_cli.py,test_integration.py}`、`cases/shear-decay-2d/mesh-preparation/create_example_mesh.py` 的导入、调用和 mock；修改 `pyproject.toml` 包发现及新作业源码哈希扫描路径。
- 操作：修改 `README.md`、`AGENTS.md` 的目录职责，直接更新 `STATUS.md` 功能表并追加本记录；历史记录保留。修改前已执行 git add，将上次回退涉及的版本及关联文档加入暂存区作为检查点，本次改动留在工作区；未执行提交。
- 验证：WSL Ubuntu / Python 3.8.10 下 CLI 的 5 项相关测试和完整 25 项 unittest 全部通过，无跳过。七个搬移/重命名函数、作业准备及清单构建逻辑的 AST 对比通过；固定随机因子的作业 ID、身份和除创建时间/源码哈希外的元数据相同；五类异常各覆盖归档成功/失败，共十种状态、历史及诊断对比一致。
- 验证：在隔离临时目录离线构建 wheel 并完成非 editable 安装，确认新模块、报告 JS/CSS、VTK 桥接均入包，旧 execution 及此前拆分包不入包；从源码目录外验证安装登记、模块及控制台入口、查询和校验。准备模式的 QUEUED、状态历史、无归档/报告及新目录源码哈希均通过；安装版串行和两进程 MPI 均为 SUCCEEDED，各有 11 个 VTU 时刻、参考比较和 HTML 报告，work 按原策略清理。
- 验证：初次临时构建因系统旧 importlib_metadata 与打包工具冲突失败，改用临时 setuptools 自带依赖后构建及安装通过；未修改全局环境或项目依赖。Python 语法、新模块格式及最终差异检查通过；源输入、网格、追溯、固定样本、历史 runs/artifacts 及本机 config.yaml 共 1,427 个受保护文件哈希不变。本次未重跑浏览器交互，也未验证其他求解器或版本；临时工具、备份和验证工作区交付前清理。
