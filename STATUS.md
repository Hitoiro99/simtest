# 项目功能状态与变更记录

需求依据：[流体结构数值模拟软件自动测试系统方案.md](ARCHITECTURE.md)。

## 记录规则

- 本文件只用于保存功能状态和文件操作记录，用户没有明确要求则不需要整体阅读该文档，仅追加记录即可。
- 状态使用：已实现、部分实现、未实现；已实现但示例未使用不算未实现。
- 每次完成一批代码修改后，在文档尾部追加一条记录，新交接记录只写当前基线、未解决问题、下一步和验证状态，不重复较长历史。
- 历史记录不覆盖、不删除；未执行的修改和测试不能写成已完成。
- 此后按上述规则追加。

## 功能状态


| 功能 | 状态 | 当前范围或缺口 |
|---|---|---|
| 案例、工况发现和参数解析 | 部分实现 | 类型、必填项、单位和派生变量已有；CLI 校验补齐默认执行参数并检查案例映射，零工况明确报错；通用取值范围约束未实现 |
| 案例多执行配置与单命令多作业 | 已实现 | `case.yaml` 的 `execution` 支持单个映射或映射列表，`run` 按声明顺序运行全部配置并合并为一份报告；相同组合仍复用归档 |
| 标签检索、案例依赖、通用取值范围约束 | 未实现 | 标签仅作为元数据保存 |
| 求解器注册与版本选择 | 部分实现 | 注册、安装绑定和版本排序已集中于 solvers/registry.py，主程序与版本规则由 Adapter 提供；真实接入仍仅 OpenFOAM 12 |
| OpenFOAM Foundation 12 接入 | 已实现 | 当前案例的串行及两进程 MPI；其他版本未完成真实验证 |
| Fluent、StarCCM、AICFD 和结构求解器 | 未实现 | 尚未接入 |
| 模板选择、继承与输入生成 | 部分实现 | 公共层已支持内核自有文件布局，继承叠加后一次渲染；原生目录由 Adapter 检查；真实接入仍仅 OpenFOAM 12，其他内核模板未完成真实验证 |
| 唯一源网格、复制哈希和 checkMesh | 已实现 | 公共层发现唯一源资产；OpenFOAM Adapter 检查 polyMesh 必需文件，当前网格的复制哈希和 checkMesh 已验证 |
| AICFD-NewPre 转换及多域核验 | 未实现 | 跨格式和完整多域链路未接入 |
| Linux/WSL 本地执行 | 已实现 | 进入 Linux/WSL 后直接使用 python3 -m simtest，安装后也可用 simtest；保留日志、超时、取消和资源统计 |
| 容器、集群调度及集成多作业调度 | 未实现 | 当前 CLI 按 case.yaml 声明的多执行配置、多工况、多求解器顺序组织作业；容器和集群调度未实现 |
| OpenMP/CUDA 求解后端 | 未实现 | 当前 Adapter 在启动前返回 UNSUPPORTED；MPI 已支持 |
| 监控和残差 CSV 标准化 | 部分实现 | OpenFOAM Adapter 内的方法负责解析与标准化，保留采样边界和无效值；版本类可重载，其他求解器读取器未接入 |
| 场结果标准化 | 部分实现 | 当前单域、reference 所需场的全部输出时刻；多域同字段及张量未覆盖 |
| 标量监控及解析场参考比较 | 已实现 | 当前案例仅配置速度场参考；输出误差，不作数值 PASS/FAIL 判定 |
| 基线、性能及跨网格离散场比较 | 未实现 | 现有资源记录和曲线叠加不等于自动比较 |
| HTML 交互与 JSON/CSV、静态图报告 | 已实现 | 离线交互及各格式输出；成功归档 CSV/VTU 独立回读，失败状态与日志摘要入报，同一选集复用 |
| 报告直接读取归档 CSV/VTU | 已实现 | 独立回读标准监控与全部验证场，使用归档参考定义重算报告偏差；串行/MPI 各 11 时刻通过，原归档不变 |
| 输入、日志、标准结果及元数据归档 | 已实现 | 只发布成功且完整的不可变归档，校验标准文件可读性与清单哈希；失败现场保留在 runs |
| 运行副本清理与去重 | 已实现 | 标准数据与归档双校验后移除整个工作区；同身份成功复用、准备校验接续、失败保留且不自动重试，损坏拒绝覆盖 |
| 硬件和资源信息 | 部分实现 | 已记录主机指纹、CPU、OS、总内存、GPU 探测、MPI、亲和性、cgroup 与进程限制及实际耗时/峰值内存；多节点及容器真实验证未覆盖 |
| 案例网格制备与报告测试归位 | 已实现 | 网格制备位于案例 mesh-preparation/，成功后自动清理 `.build/mesh`；浏览器测试位于 tests/report/；空 tools/ 已移除 |
| 平台代码按职责拆分 | 已实现 | 按确认方案保留 case_management/common；求解器相关逻辑集中于 solvers，jobs/analysis/archive/report 位于根目录；旧目录已移除，安装版完整链路通过 |
| 项目代码风格与可读性约定 | 已实现 | AGENTS.md 已记录用户最终入口样式；受维护的 Python、JavaScript/CJS、CSS 及测试已统一，复杂条件式展开，保留简单值选择及用户最终入口排版 |
| 项目 AGENTS.md 工作规则 | 已实现 | 根目录文档维护目录、测试和 Linux/WSL 入口规则；solvers/ 位置保持不变 |
| 稳定身份哈希与重复请求复用 | 已实现 | 完整规范身份 SHA-256，物理时间和输出设置参与；创建/耗时/生成路径等不参与；完整身份比对、同作业进程锁与归档/报告去重均通过回归 |

| 固定报告模板与离线 ECharts | 部分实现 | 固定模板、离线图表、工况名称取 YAML 文件名、分量/误差类型分图及完整数据展示已写入，正在进行报告和安装回归 |

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

### 012｜2026-10-19｜划清案例管理与求解器原生检查职责

- 操作：修改 `case_management/cases.py`，唯一源网格发现保留资产数量和类型检查，将 polyMesh 内部文件校验移入 `solvers/OpenFOAM/adapter.py` 的 validate_mesh()，由 validate() 调用。
- 操作：修改 `case_management/templates.py`，提取 template_files() 共用继承文件清单及校验；保留符号链接、路径边界、禁止附带源网格和一次渲染约束，取消公共代码中的 OpenFOAM 目录硬编码。修改 `solvers/base.py`，增加可重载的 validate_template()；OpenFOAM Adapter 实现原生布局限制。修改 `simtest.py`，validate 共用模板文件检查，不渲染、不启动原生工具。
- 操作：修改 `tests/test_core.py`、`tests/test_cli.py`，增加 8 项职责边界、其他内核模板布局、过滤器隔离、版本重载、继承一次渲染及安全回归；修改 `README.md`、`AGENTS.md` 的职责说明，更新本文件功能表并追加记录。新增、删除、移动/重命名受维护文件：无；未实施其他目录迁移。
- 操作：修改代码前已执行 git add -A，将已有 AGENTS.md、README.md 改动及工作区状态保存到暂存区；本批修改留在工作区，未创建提交，保留用户已有文档改动。
- 验证：WSL Ubuntu / Python 3.8.10 下修改前 25 项测试全部通过；修改后相关核心 18 项和完整 33 项 unittest 全部通过，无跳过。真实 OpenFOAM Foundation 12 的隔离工作区 validate、checkMesh 和 prepare-only 通过，准备状态停在 QUEUED，未启动求解或产生归档；现有案例的新旧模板物化文件及 SHA-256 一致。
- 验证：未执行完整串行/MPI 求解、浏览器交互或重新打包；本次测试中的其他内核 Adapter 只用于公共模板边界验证，不代表接入了新求解器。
- 验证：受影响的 7 个 Python 文件语法与风格检查、最终差异格式检查通过；需求文档、本机配置、案例源输入、固定样本及历史 runs/artifacts 共 1,530 个文件的 SHA-256 未变。历史操作记录完整保留；临时验证文件在交付前清理。

### 013｜2026-10-19｜按需求职责归位并简化平台目录

- 操作：将 run_control/install.py 的安装登记与选择、environment.py 的环境加载归入 solvers/registry.py，将工具定位和辅助命令执行归入 solvers/base.py；新增 Adapter 主程序归属检查，主程序标识、版本规则和环境白名单由对应 Adapter 提供。
- 操作：迁移 run_control/jobs.py → jobs.py、postprocessing/analysis.py → analysis.py、storage/archive.py → archive.py；将归档查询归入 archive.py。合并 reporting/report.py 与 reporting/report_html.py → report.py；移动 reporting/report_assets/ → report_assets/，增加资源包初始化文件以支持安装后离线读取，JS/CSS 内容不变。
- 操作：将 solvers/OpenFOAM/monitors.py、fields.py 中的读取逻辑归入 adapter.py 的 read_log/read_tables/read_monitors/output_times/read_fields 方法，删除两个旧辅助文件；移动 postprocessing/vtk_bridge.py → solvers/OpenFOAM/vtk_bridge.py，桥接脚本内容不变，版本类可重载读取方法。
- 操作：同步 simtest.py、pyproject.toml、tests/test_core.py、tests/test_cli.py、tests/test_integration.py、tests/test_reader.py、tests/test_report.py，以及 cases/shear-decay-2d/mesh-preparation/create_example_mesh.py 的导入；新增 tests/test_registry.py，补充安装绑定、版本规则和环境隔离回归。更新本文件功能表并追加记录。修改前已执行 git add 保存上批改动，未创建提交。
- 验证：WSL Ubuntu / Python 3.8.10 下完整 43 项 unittest 全部通过，无跳过；包含实际 pvpython 固定样本、原生导出回退、进程超时、归档损坏、CLI 与报告，以及新增版本方法重载和非 icoFoam 测试。测试内核仅验证公共协议，不代表已接入新求解器。
- 操作：移除迁空的 run_control/、postprocessing/、storage/、reporting/ 及旧初始化文件和缓存；修改 README.md、AGENTS.md 的目录、职责及测试说明。后续代码收尾前再次执行 git add 保存 43 项测试通过的迁移检查点。
- 操作：删除 run_control/{__init__.py,install.py,environment.py,jobs.py}、postprocessing/__init__.py、storage/__init__.py、reporting/__init__.py 等迁空旧文件；移动和合并的业务文件见本记录前述路径。新增文件为 report_assets/__init__.py、tests/test_registry.py；案例网格制备脚本仅更新导入，不重建网格。
- 验证：中断后在最终目录上重新运行完整 43 项 unittest，全部通过且无跳过；旧模块路径在活动代码、测试、README 和 AGENTS 中已清除。18 个搬移函数的 AST 与原实现一致，五项读取算法在方法与路径映射后等价；analysis.py 与 vtk_bridge.py 内容不变。七份现有归档均通过完整性检查，图表、汇总行和 HTML 与迁移前一致。30 个 Python 文件语法和风格检查通过。
- 验证：在临时目录获取构建工具后生成 wheel 并非 editable 安装，未修改全局环境或项目依赖；新根模块、离线资源及 VTK 桥接已入包，旧模块未入包。源码目录外的模块与控制台入口、setup/list/validate/prepare-only 均通过；普通导入不加载 VTK。安装版串行及两进程 MPI 均为 SUCCEEDED，各读取 11 个场时刻、生成 HTML 并按原策略清理 work；两作业合并报告正常。
- 验证：第一次完整链路检查因会话中断停在场读取阶段，未记作通过；恢复辅助脚本初次缺少 shutil 导入，修正后在新的隔离工作区完成全部安装验证。Node 24 / Edge 对安装版合并报告完成 14 项交互检查，JavaScript 异常为 0，覆盖缩放、平移、图例、悬停、指标切换、全屏、SVG 导出及移动宽度。
- 验证：恢复工作后记录的 1,530 个需求、配置、案例、样本及历史运行/归档文件哈希均保持不变；需求文档和原有归档无 Git 差异，案例目录仅网格制备脚本有已说明的导入调整。安装验证所用源码与最终工作区一致；暂存和工作区差异格式检查通过。临时工具、安装环境、求解目录、报告和截图在交付前清理。

### 014｜2026-10-19｜稳定作业身份、去重与归档后清理

- 操作：修改前执行 git add 保存上一批结构调整；修改 jobs.py，移除随机 nonce，使用完整规范化身份的 SHA-256，包含案例源文件、执行配置、实际求解器、代码、载体与环境指纹；创建时间、生成路径及运行后统计不参与身份。通过分配锁和每作业进程锁实现同身份单写，准备完成后可校验接续；相同失败状态不自动重试。
- 操作：修改 simtest.py，按已确认方案移除 --keep-raw；完整运行调用新的作业接口。更新本文件功能表并追加本记录；归档、标准结果读取和报告部分正在同批整合。

- 操作：补充实际主程序约束、等价超时数值规范化及 cgroup/进程资源限制指纹；MPI 分区产生的内部链接经边界检查后展开，保持严格输入/归档检查。
- 验证：首轮完整 71 项通过；真实串行接续及工作区清理通过；首轮 MPI 被内部链接快照检查拒绝并保留现场，修正后将重新执行验证，不把该次记为通过。

- 操作：将硬件身份中的内存改为内核 online 内存块容量，排除 WSL MemTotal 的运行期微小波动；补充准备模式篡改拒绝、清理拒绝不改变成功状态与等价超时参数回归。

- 操作：修改 `archive.py`、`report.py`、`solvers/OpenFOAM/{adapter.py,vtk_bridge.py}`，新增 `tests/test_archive.py`、`tests/test_jobs.py`，修改 `tests/{test_core.py,test_reader.py,test_report.py}`；归档与报告分别增加独立读取、双校验、不可变发布和稳定复用，VTU 补存真实单元中心几何。同步 `README.md`、`AGENTS.md` 及本文件功能表。无目录迁移；移除 CLI --keep-raw。
- 操作：按用户授权清空原 `runs/`、`artifacts/` 的旧作业与关联旧报告，并移除本轮修正前的中间验证数据；仅保留最终串行和两进程 MPI 两份归档、各自报告及一份汇总报告。未修改需求、源网格、物理配置、参考与固定样本。
- 验证：最终 WSL Ubuntu / Python 3.8.10 全量 73 项测试全部通过，无跳过；覆盖同身份双进程单写、失败不重试、准备篡改、清理失败再清理、归档损坏拒绝和报告并发发布。
- 验证：最终真实 OpenFOAM Foundation 12 串行与两进程 MPI 均 SUCCEEDED；MPI 从同一准备 ID 接续，分区、求解、全部时刻重构与归档读取通过。各有 11 个验证场时刻，成功后整个作业目录不存在；重复 CLI 均返回原 ID 和 reused=true，报告也复用原目录。串行 ID `afb280315a90f569b9160089cc6aa6c8f212e9008f0907a137402aaff05723cb`，MPI ID `183ad96059f9c30e6204212cefaff8ec044e429aba74483792f22051b300488b`。
- 验证：35 个需求、配置、案例及固定样本文件 SHA-256 未变，历史操作记录未覆盖。本次不代表新增其他求解器、跨节点/容器或性能基准能力；未重新构建安装包。

- 验证：首轮浏览器前 13 项交互正常，390px 宽度检查发现 64 位作业 ID 导致文本溢出；修改 `report_assets/report.css` 允许长文本换行，随后重检。

- 验证：长 ID 换行修复后，最终串行/MPI 又各执行一次并保留，重复 CLI 再次均 reused=true；最终串行 ID `e8704a74c7652fa10652f77112ca01b03f3fe817e371f1545b49ed2ca69966ac`，MPI ID `3275c1b2748dfbdbbc911c0f70ce0bb7dbe6cce0dc3ac657091f0738605dea4e`。本记录前述两 ID 属于样式修复前验证，相关中间数据已按授权移除。最终保留 2 份成功归档及 3 份不同选集报告，无 runs 作业目录；根 .lock 为并发协调文件。
- 验证：Node 24 / Edge 对最终汇总 HTML 完成全部 14 项交互检查，JavaScript 错误为 0，包含缩放、平移、图例、悬停、指标选择、筛选、全屏、SVG 导出及 390px 宽度；修复前一次窄屏失败已如实记录。最终 diff 格式检查通过，临时快照与浏览器截图交付前清理；按规则 git add 暂存，不创建提交。

### 015｜2026-10-21｜固定报告框架、独立分量图与完整数据

- 操作：按用户确认的方案执行，修改前 git add 保存已有改动；新增 `report_assets/{echarts.min.js,ECHARTS-LICENSE.txt,ECHARTS-NOTICE.txt,echarts-version.json}`，固定官方 ECharts 5.6.0 离线资源与 SHA-256，修改 `pyproject.toml` 将 HTML 模板、许可和版本清单纳入安装包。

- 操作：修改 `report.py`、`report_assets/{report.js,report.css}`，新增固定模板 `report_assets/report.html`，完整数据输出与图表按职责留在现有模块；修改 `tests/test_report.py`、`tests/report/check_html_report.cjs` 覆盖新数据及交互。补充 `report_assets/ECHARTS-D3-LICENSE.txt`；更新 `README.md`、`AGENTS.md` 和本文件功能表。

### 016｜2026-10-21｜case.yaml 多执行配置与单命令合并报告

- 操作：修改 `case_management/cases.py`，新增 `execution_configs()`，接受单个映射或映射列表并逐项校验，列表为空、列表项非映射或名称重复时拒绝；`load_case()` 改用该函数校验案例执行配置。
- 操作：修改 `jobs.py`，`prepare_job()` 从执行配置列表取首项作为基线，保留既有调用方覆盖参数与稳定身份哈希逻辑。
- 操作：修改 `simtest.py`，移除 `run` 的 `--processes`、`--backend`、`--openmp-threads` 覆盖参数；`validate` 逐项校验全部执行配置，`run` 按 `case.yaml` 声明顺序执行全部配置，并将全部作业合并为一份报告。
- 操作：修改 `report.py`，新增 `execution_label()`，图例优先显示执行配置的 `name`，未命名时回退为进程数和后端。
- 操作：修改 `cases/shear-decay-2d/case.yaml`，声明 `serial-1`（1 进程）与 `mpi-2`（2 进程）两项执行配置。
- 操作：修改 `tests/test_core.py` 增补执行配置解析测试；修改 `tests/test_cli.py` 适配多配置运行次数与合并报告断言；修改 `tests/test_jobs.py`、`tests/test_report.py` 将工况标识同步为 `Re=10`。
- 操作：修改 `README.md` 的运行命令、执行配置示例和工况显示说明；更新本文件功能表并追加本记录。修改前已执行 `git add` 保存检查点，未创建提交。
- 验证：WSL Ubuntu / Python 3.8.10 下 `python3 -m unittest discover -s tests -v` 共 76 项全部通过，无失败、无跳过。
- 验证：`python3 -m simtest validate shear-decay-2d` 返回 `valid: true`，`serial-1` 与 `mpi-2` 两项配置均通过 OpenFOAM Foundation 12 校验。
- 验证：在隔离根目录 `/tmp/simtest-profiles` 执行一次完整 `run shear-decay-2d`，两项配置各产生 1 个 SUCCEEDED 归档（job ID `be2e10fe2ee803046f0cbf6537d42e85ca1fa3295026f5895ffd7865f664fd26`、`10ca3d9d3f0c6500a18eff977e503785d8c56fa7921c1105d4e31bd1632c35f4`），只生成 1 份报告（`runs: 2`），报告 HTML 同时包含 `serial-1` 与 `mpi-2` 图例，静态图 PNG/SVG/PDF 均已生成；验证后已删除该临时目录。
- 验证：PDF 生成期间出现 matplotlib `Font 'default' ... U+2212` 既有字体告警，未导致作业或报告失败。本次未重跑浏览器交互回归；未验证 OpenMP/CUDA 后端（适配器仍返回 UNSUPPORTED）；未修改历史归档、源网格或固定样本。

### 017｜2026-10-21｜修正执行配置名称未写入作业身份

- 操作：更正记录 016 的验证结论：该次报告图例实际两条均为 `serial-1`，`mpi-2` 只出现在内嵌案例数据中；原因是 `prepare_job()` 固定取配置列表首项作为基线，只覆盖 `backend`/`processes`/`openmp_threads`，未覆盖 `name`。
- 操作：修改 `jobs.py`，`prepare_job()` 增加可选 `execution` 参数；传入时直接使用该配置（含 `name`），未传入时仍取案例首个配置并保留既有覆盖逻辑。
- 操作：修改 `simtest.py`，`run` 将当前配置整体传入 `prepare_job(..., execution=profile)`，不再逐项覆盖 options；移除不再使用的 `copy` 导入。
- 操作：修改 `tests/test_jobs.py` 新增名称写入身份的回归；修改 `tests/test_cli.py` 断言 `run` 依次把 `serial-1`、`mpi-2` 整体传给 `prepare_job`。
- 操作：更新本文件并追加本记录。修改前已执行 `git add` 保存 016 对应检查点，未创建提交。
- 验证：WSL Ubuntu / Python 3.8.10 下完整 77 项 unittest 全部通过，无失败、无跳过。
- 验证：在隔离根目录 `/tmp/simtest-profiles` 重新运行 `run shear-decay-2d`，两个作业均 SUCCEEDED（job ID `62ded66dc82aa6c959fdea483a54de28186eb5c80698685eb12d341a1ef6d60c`、`199b14ed15873c6ac458f570473fb05bc92d117442df249d93ce35e04519485f`），生成 1 份报告（`runs: 2`），图例为 `serial-1` 与 `mpi-2`；验证后已删除该临时目录。
- 验证：仓库内 `1c17072e…`、`1e9d89f6…` 两份归档由修复前代码生成，`execution.name` 均为 `serial-1`，未删除，作为历史产物保留。本次未重跑浏览器回归，未验证 OpenMP/CUDA 后端。

### 018｜2026-10-21｜网格制备成功后自动清理 .build

- 操作：修改 `cases/shear-decay-2d/mesh-preparation/create_example_mesh.py`，在网格复制与 provenance 写入成功后删除 `.build/mesh`，`.build` 为空时一并删除；删除失败仅向 stderr 打印警告，不改变已完成的制备结果。
- 操作：新增 `tests/test_mesh.py`，用模拟的 blockMesh/checkMesh 覆盖成功清理与 checkMesh 失败保留现场两种情形。
- 操作：更新本文件功能表并追加本记录。修改前已执行 `git add` 保存 019 检查点，未创建提交。
- 验证：WSL Ubuntu / Python 3.8.10 下 `test_mesh.py` 2 项通过；完整 79 项 unittest 全部通过，无失败、无跳过。
- 验证：未执行真实 blockMesh/checkMesh 重新制备（会覆盖受控源网格，当前 `cases/shear-decay-2d/polyMesh` 已存在，脚本按设计拒绝）；清理逻辑仅由模拟测试覆盖。未重跑浏览器回归，未验证 OpenMP/CUDA 后端。

### 019｜2026-10-21｜对数刻度改用纯文本标签

- 操作：修改 `report.py`，新增 `log_tick_label()`，静态图的对数轴改用 `FuncFormatter` 输出 `10^-3` 形式的纯文本标签，并关闭次刻度标签，避免 mathtext 使用 SimHei 缺失的 U+2212 而被替换成占位符。
- 操作：修改 `tests/test_report.py`，新增标签格式回归。
- 操作：更新本文件并追加本记录。修改前已执行 `git add` 保存 020 检查点，未创建提交。
- 验证：WSL Ubuntu / Python 3.8.10 下完整 80 项 unittest 全部通过，无失败、无跳过。
- 验证：隔离根目录 `/tmp/simtest-profiles` 运行 `run shear-decay-2d`，两个作业 SUCCEEDED、1 份报告，生成 33 个静态图文件（11 张 × PNG/SVG/PDF）；stderr 中 `does not have a glyph for '\u2212'` 计数为 0（改动前每次报告约 36 条）；验证后已删除临时目录。
- 验证：本次残差数据近似恒定，log 轴自动缩放范围过窄，该图没有可见的十进制刻度标签；该现象由 Locator/自动缩放决定，与本次 formatter 改动无关，未在本次处理。未重跑浏览器交互回归，未验证 OpenMP/CUDA 后端。

### 020｜2026-10-21｜修正极小误差时 ECharts 纵轴刻度重叠

- 操作：修改 `report_assets/report.js`，`render()` 统计全部绘制点的 `dataMin` / `dataMax`；线性 y 轴改用显式 `min` / `max`（5% 留白，非负数据下限不小于 0，全等数据按 10% 或 0.5 展开），避免 ECharts 对约 `1e-13` 量级数据把自动范围算成 `[0, 0]` 导致刻度标签重叠；对数轴保持原有显式范围。
- 操作：更新本文件并追加本记录。修改前已执行 `git add` 保存 021 检查点，未创建提交。
- 验证：`node --check report_assets/report.js` 通过。
- 验证：用归档 `2839e8a1…`、`85348775…` 重新生成报告 `artifacts/shear-decay-2d/reports/407543b942e5777bcef8846fa672a94a5eeff057df27d97cc5e99bc9abcd6ce6/report.html`；Edge headless 打开后读取目标图（velocity / y / 归一化误差）：y 轴 extent 为 `0, 1.5129551467293905e-12`（改动前为 `0, 0`），刻度标签分别位于 y=356、291.36、226.72、162.07、97.43、32.79，互不重叠。
- 验证：完整 80 项 unittest 全部通过，无失败、无跳过。
- 验证：`tests/report/check_html_report.cjs` 在改动后的报告和改动前的 `9b14b260…` 报告上都于 `/步/` 断言处失败（实际 x 轴标题为 `Step`），属于本次改动前已存在的测试与实现不一致，未在本次修改；因此该浏览器交互回归未通过，不能作为本次修复的验证。未验证 OpenMP/CUDA 后端。

### 021｜2026-10-21｜修正浏览器回归的 x 轴标题断言

- 操作：修改 `tests/report/check_html_report.cjs`，残差图 x 轴标题断言由 `/步/` 改为 `/Step|步/`，与当前 `report.py` 输出的 `Step` 一致，同时兼容中文标题。
- 操作：更新本文件并追加本记录。修改前已执行 `git add` 保存 022 检查点，未创建提交。
- 验证：对新报告 `407543b9…` 运行 `check_html_report.cjs`，x 轴标题断言通过，随后在 `Box zoom did not change range`（第 188 行）失败。
- 验证：对改动前的旧报告 `9b14b260…` 运行同一脚本，同样在 box zoom 断言失败；该失败为本次修改前已存在的问题，与本次断言修改无关。浏览器交互回归仍未通过。
- 验证：完整 80 项 unittest 全部通过，无失败、无跳过（该 JS 脚本不参与 unittest）。未验证 OpenMP/CUDA 后端。

### 022｜2026-10-22｜规定状态记录与本地功能提交

- 操作：修改 `AGENTS.md`，规定代码功能修改只读取 `STATUS.md` 的记录规则和功能状态，并仅在文件末尾追加记录；规定每实现一个可独立验证的功能即创建一次本地 Git 提交，不自动推送远端。
- 操作：修改 `STATUS.md`，仅在文件末尾追加本记录；新增、删除、移动/重命名文件：无。
- 验证：检查 `AGENTS.md` 差异和 `STATUS.md` 末尾内容；本次仅修改工作规则和记录，未运行测试或求解。

### 023｜2026-10-22｜将首个示例替换为二维启动 Couette 流

- 操作：删除 `cases/shear-decay-2d/` 源案例；新增 `cases/couette-2d/`，包含 `Re=10` 工况、启动 Couette 速度和零运动压力参考、OpenFOAM Foundation 12 模板、案例说明、网格制备脚本、参考说明、16×32×1 唯一 `polyMesh/` 及制备追溯。旧 `artifacts/shear-decay-2d/` 历史归档未修改。
- 操作：修改 `tests/test_cli.py`、`tests/test_core.py`、`tests/test_mesh.py`，将示例引用切换为 `couette-2d`；新增 `tests/test_couette_case.py`，覆盖参数、解析表达式、边界、时间控制、唯一源网格和 patch。修改 `README.md`，更新命令、案例物理定义、解析解、网格和结果说明；平台代码未修改。
- 操作：使用新案例生成两份不可变归档及一份派生报告；成功归档后两个 `runs/<job-id>/` 工作区均已整体移除。修改 `STATUS.md` 时只在文件末尾追加本记录。
- 验证：真实 OpenFOAM Foundation 12 `blockMesh`、`checkMesh` 通过，网格为 512 个六面体单元、范围 `(0 0 0)`—`(1 1 0.01)`，结果为 `Mesh OK`；WSL 下完整 84 项 unittest 全部通过。
- 验证：`list cases` 仅发现 `couette-2d/Re=10`，`validate couette-2d` 返回 `valid: true`；`prepare-only` 生成串行和 MPI 两个稳定作业，随后完整运行均为 `SUCCEEDED`。每份归档包含 1001 条各监控记录、11 个实际时刻的速度和压力共 22 个 VTU、55 条可用比较且无 `UNAVAILABLE`；速度最大绝对误差为 `0.00173914959470683 m/s`。
- 验证：重复运行返回相同作业 ID，两个作业及同一报告均为 `reused: true`，未新增重复数据。报告位于 `artifacts/couette-2d/reports/bae3642008bfa587694a88da00db089487b54971b1200914c99ed290027cd969/report.html`。
- 验证：浏览器回归通过加载和前置检查，但仍在既有 `Box zoom did not change range` 断言失败；该问题在案例替换前已有记录，本次未修改报告交互代码，不能将浏览器全量回归记为通过。未验证 OpenMP/CUDA 后端及 OpenFOAM v2506。

### 024｜2026-10-22｜精简报告展示并统一迭代步横轴

- 目的：报告页面仅展示解析解对比、监控量和残差三类图像，所有图像使用迭代步横轴；页面只列最后一步数值，不展示绝对误差或逐点数值明细，同时保持归档数据不变。
- 操作：修改 `report.py`，使用已验证的场时间元数据将解析场输出映射到迭代步；有解析场参考时隐藏普通监控图，残差独立保留；解析解对比仅构造归一化误差图，并生成最后一步监控量和解析偏差摘要。修改 `report_assets/{report.html,report.js,report.css}`，移除逐点明细、绝对误差和完整元数据展示，保留诊断摘要、归档文件链接及离线交互；报告目录中的既有 CSV/JSON 输出和归档协议未改变。
- 操作：修改 `tests/test_report.py`、`tests/report/check_html_report.cjs`，覆盖三类图像、解析/监控互斥、统一步数轴、最终值摘要和页面隐藏绝对误差及逐点明细；修改 `README.md` 同步报告使用说明。新增、删除、移动/重命名受维护源文件：无。
- 验证：WSL Ubuntu / Python 3.8.10 下报告聚焦测试 15 项及完整 85 项 unittest 全部通过，无失败、无跳过；`report.py` 语法检查和两份 JavaScript/CJS 语法检查通过。
- 验证：从现有两份 Couette 归档生成最终报告 `artifacts/couette-2d/reports/31de8c3d8ffaf9843c4dbd1be3e54f33f87148c68dd35c004e10eb8af8ab9a2b/report.html`，包含 5 张解析解归一化偏差图、2 张残差图和 0 张普通监控图；HTML 无绝对误差字段及逐点明细区，保留最后一步结果区。归档文件集合生成前后 SHA-256 摘要均为 `7400e5499812e89a0637fbbaf500b8986be28d42e5120f24107a6dedca63502b`，归档未被修改。
- 验证：Edge 无头浏览器在沙箱外完成页面加载及本次新增的图表类型、迭代步横轴、归一化误差和页面精简前置断言，随后仍在既有 `Box zoom did not change range` 断言失败；该问题在记录 020、021 和 023 中已存在，本次没有修改框选缩放机制，浏览器全量回归不能记为通过。未运行新求解作业，未验证 OpenMP/CUDA 或 OpenFOAM v2506。

### 025｜2026-10-22｜图表横轴标签统一为 Step

- 目的：按用户要求把图表横轴标签由“迭代步”改为英文 `Step`，语义不变。
- 操作：修改 `report.py` 两处 `xlabel` 为 `Step`；修改 `tests/test_report.py` 和 `tests/report/check_html_report.cjs` 的断言；修改 `README.md` 两处横轴说明。新增、删除、移动/重命名受维护源文件：无。
- 验证：WSL Ubuntu / Python 3.8.10 下报告测试 15 项及完整 85 项 unittest 全部通过，无失败、无跳过；未重新生成报告，未运行浏览器回归，未验证 OpenMP/CUDA 或 OpenFOAM v2506。

### 026｜2026-10-22｜按案例选择 icoFoam 或 simpleFoam

- 目的：同一 OpenFOAM Adapter 支持 `icoFoam` 和 `simpleFoam`，由案例模板决定，不使用偏好或回退。
- 操作：修改 `solvers/OpenFOAM/adapter.py`，新增 `supported_applications` 与 `case_application()`；`probe()` 从案例模板的 `controlDict` 读取 `application` 并选择对应可执行文件；`preprocess()` 接受两种主程序并校验与探测结果一致。修改 `solvers/base.py`，安装归属检查使用所选主程序；修改 `solvers/registry.py`，`select_install()` 接受 `case_path` 并传入 probe；修改 `jobs.py`、`simtest.py` 调用点；修改 `solvers/models.py`，`SolverInfo` 增加 `application` 字段。修改 `tests/test_core.py` 增加案例选择测试，`tests/test_jobs.py` 适配新增关键字参数。
- 验证：WSL Ubuntu / Python 3.8.10 下完整 86 项 unittest 全部通过（新增 1 项），无失败、无跳过；未真实运行 `simpleFoam`，未重新生成报告，未运行浏览器回归，未验证 OpenMP/CUDA 或 OpenFOAM v2506。

### 027｜2026-10-22｜以稳态 Couette 案例替换 couette-2d 并跑通 simpleFoam

- 目的：按 `ARCHITECTURE.md` 的案例结构，把用户提供的稳态 Couette 算例落成平台案例；保留现有目录结构，由案例模板选择 `simpleFoam`。
- 操作：修改 `cases/couette-2d/{case.yaml,README.md,conditions/Re=10.yaml,references/startup-couette-solution.md}`；用档案内容更新 `templates/OpenFOAM/{0/U,0/p,constant/physicalProperties,system/controlDict,system/fvSchemes,system/fvSolution}`，新增 `templates/OpenFOAM/constant/momentumTransport`；用档案 `blockMeshDict` 重新制备 `polyMesh/` 和 `mesh-provenance/`；`fvSolution` 增加 SIMPLE 松弛（p 0.3、U 0.7），消除无松弛导致的发散。未删除目录，未修改其他案例或代码。
- 验证：`list cases` 发现 `couette-2d/Re=10`；`validate` 通过；串行与 2 进程 MPI 作业均 `SUCCEEDED`；最后一步体积加权平均流向速度 `0.50000000000003 m/s`（参考 0.5），速度 x 最大绝对误差由初始步 `9.69e-1` 衰减到第 200 步 `2.33e-8 m/s`；报告 `artifacts/couette-2d/reports/a07fecb015b19d80302599d0241893274b570c10fda78fbd33840b8f09bb50e5/report.html` 共 7 张图，横轴全部为 `Step`。
- 验证：WSL Ubuntu / Python 3.8.10；未运行浏览器回归，未验证 OpenMP/CUDA 或 OpenFOAM v2506。

### 028｜2026-10-22｜重构报告分区、表格筛选排序与折叠

- 目的：按用户确认的结构重排报告：去掉“交互图表”大标题，拆为残差、解析解归一化误差、监控量三个区块；作业表与最后值两表支持筛选和排序；区块支持折叠及全部展开/收起。
- 操作：修改 `report.py`：作业表改为序号/工况/进程数/求解器（合并版本）/状态/墙钟/CPU/内存/作业 ID；最后值两表改为序号开头、作业 ID 结尾；表格输出 `data-values` 和列元数据；解析解图保持归一化误差；监控图仅保留 `kind: experimental` 的参考。修改 `report_assets/{report.html,report.js,report.css}`：新增分区、筛选面板、表格排序/序号重排、折叠工具栏。修改 `tests/test_report.py` 适配监控图来源规则。
- 验证：WSL Ubuntu / Python 3.8.10 下 `test_report.py` 15 项全部通过；完整 86 项中 4 项 `test_couette_case` 仍按旧瞬态 Couette 期望失败，与本次报告改动无关，未修复。未运行浏览器回归，`README.md` 尚未同步新报告结构。

### 029｜2026-10-22｜修正报告表格绑定与初始序号

- 目的：修复 `data-table-id` 绑定到外层容器导致表格脚本中断的问题，并在初始化时写入序号。
- 操作：修改 `report_assets/report.js`，从容器内查找 `table`，构造表格后立即执行一次默认筛选/排序。
- 验证：`node --check` 通过；重建报告成功。浏览器回归因样本仍按旧瞬态案例断言 1000 步、实际 200 步而中止，未能继续验证筛选和折叠；`test_couette_case` 的 4 项旧期望未修复。

### 030｜2026-10-22｜报告筛选框与折叠 UI 调整

- 目的：按截图调整筛选/排序交互：漏斗图标触发、飞书式面板、每行末尾选择升序/降序且互斥、折叠按钮无边框并与标题合并、追溯条目使用统一箭头。
- 操作：修改 `report_assets/report.js`，移除独立排序行，在条件行“值”和“×”之间加入排序选择，选择排序时清除其他行排序；修改 `report_assets/report.css`，重做筛选面板、图标按钮、无边框折叠和 `details` 箭头；修改 `tests/report/check_html_report.cjs`，按 200 步样本更新断言并新增筛选/折叠检查。
- 验证：`test_report.py` 15 项通过；浏览器回归通过新增的 3 个筛选框、序号、折叠/全部展开断言，随后仍在既有 `Box zoom did not change range` 失败。`test_couette_case` 旧期望仍未修复。

### 031｜2026-10-22｜报告标题吸顶与浮动收起按钮

- 目的：长图/长表滚动时无需回到区块开头即可收起；全局随时可一键收起或展开。
- 操作：修改 `report_assets/report.css`，区块标题栏吸顶、浮动按钮样式；修改 `report_assets/report.html` 增加右下角浮动按钮；修改 `report_assets/report.js`，同步浮动按钮与全部展开/收起状态，并让标题点击更新按钮文案；修改 `tests/report/check_html_report.cjs` 增加浮动按钮断言。
- 验证：浏览器回归通过 3 个筛选框、序号、标题折叠、全部展开、浮动按钮收起/展开断言，随后仍在既有 `Box zoom did not change range` 失败。

### 032｜2026-10-22｜common 包更名为 platform_support

- 目的：`common` 名称过泛，改为能表达“平台支撑层”的 `platform_support`。
- 操作：`git mv common platform_support`；替换 16 个 Python 文件的导入（含案例网格脚本与测试）；更新 `pyproject.toml` 包发现、`jobs.py` 代码清单、`AGENTS.md` 与 `README.md` 的目录说明。历史 STATUS 记录不修改。
- 验证：`list cases` 正常；WSL Ubuntu / Python 3.8.10 下完整 86 项 unittest 通过 82 项，仍为 `test_couette_case` 的 4 项旧瞬态期望失败，与本次改名无关。

### 033｜2026-10-23｜当前会话总结与后续交接

- 目的：为完全没有本会话上下文的后续会话提供独立交接。项目总目标是严格依据 `ARCHITECTURE.md` 建设外部求解器自动测试平台：案例负责物理问题和输入模板，`solvers/` 负责求解器及版本适配，平台层负责任务组织、比较、归档和报告；优先复用需求文档规定的模块，不建立重复、过细或仅为目录对称而存在的模块。
- 目的：当前没有正在编辑但尚未完成的代码，工作区基线为提交 `bb06fc6`。本阶段已经完成稳定作业身份和归档去重、成功归档后删除 `runs/` 工作区、首个案例改为稳态 `couette-2d`、按案例选择 `icoFoam`/`simpleFoam`、报告使用固定离线模板及 `Step` 横轴、报告分区和表格交互，以及 `common/ → platform_support/` 重命名。稳态 Couette 的串行和两进程 MPI 已真实运行成功，OpenFOAM Foundation 12 是目前唯一真实接入并验证的版本。
- 目的：当前卡点有三项。第一，`tests/test_couette_case.py` 仍保留旧瞬态 Couette 期望，最近一次完整测试为 86 项通过 82 项、失败 4 项；这不是当前稳态求解结果失败，但测试基线尚未同步。第二，浏览器回归的加载、筛选、折叠和新增报告断言已通过，但仍在既有 `Box zoom did not change range` 断言失败，不能宣称浏览器回归全部通过。第三，OpenFOAM v2506 尚未接入或真实验证；OpenMP、CUDA、Fluent、StarCCM、AICFD 和结构求解器也未实现。
- 目的：建议下一步先向用户给出方案并确认，再按以下顺序处理：①根据当前稳态 Couette 定义更新 4 项过期测试并恢复全量测试绿色；②决定是否修复框选缩放回归，或明确取消该交互要求；③开始 OpenFOAM v2506 接入，只在 `solvers/OpenFOAM/adapter.py` 和 `versions/` 中补充真实差异，避免新建重复顶层模块；④使用真实 v2506 安装完成 `validate`、串行、MPI、标准化、归档复用和报告验证，并更新 README、STATUS 后创建独立本地提交。
- 目的：后续应避免本会话出现过的做法：未先给方案和等待确认便修改代码；把需求文档中的职责表机械映射为大量目录；在 `case_management/` 与 `solvers/` 重复实现求解器原生规则；为报告展示修改不可变归档；把 `SUCCEEDED` 当作数值满足预期；把已知浏览器失败写成全量通过；案例从瞬态改为稳态后遗漏同步测试；在 PowerShell 中照抄 `<job-id>` 占位符；反复读取完整文件、完整日志或在结论明确后重复验证同一事实。读取和验证应以满足当前改动及需求约束所需的最小范围为准。
- 目的：阅读顺序建议为 `ARCHITECTURE.md`、`AGENTS.md`、本文件的记录规则与功能状态、末尾记录 023—033、`README.md`，再阅读与具体任务直接相关的代码。注意本文件顶部功能表中的“固定报告模板与离线 ECharts”仍写为“部分实现”，其描述早于记录 024—031；受追加式历史规则约束未回写，判断最新状态时以末尾记录和当前代码为准。
- 操作：仅修改 `STATUS.md`，追加本交接记录；新增、删除、移动/重命名文件：无；代码、案例、归档和报告均未修改。
- 验证：修改前确认 Git 工作区无未提交改动，并核对 `ARCHITECTURE.md`、`README.md`、`STATUS.md` 的章节结构、`STATUS.md` 最新记录及最近 8 次提交。本次仅追加文档，未运行单元测试、求解器或浏览器回归；上述测试结果均明确标注为最近一次历史结果，不作为本次验证。

### 034｜2026-10-23｜恢复 Couette 案例测试基线

- 基线：工作区基于 `main`；Foundation 12 仍是唯一真实接入版本；稳态 Couette 串行/MPI 已成功归档。
- 操作：修改 `tests/test_couette_case.py`，把旧瞬态期望更新为稳态 `simpleFoam` 案例：`wall_gap=0.01`、`ν=0.001`、`0–200` 迭代、`write_interval=20`；解析式改为 `u=U*y/H`；模板断言改为 inlet/outlet/movingWall；网格断言改为两段 `120 8 1`。
- 验证：`test_couette_case.py` 4 项通过；WSL Ubuntu / Python 3.8.10 下完整 86 项 unittest 全部通过。未运行浏览器回归，未接入 v2506。
- 未解决：浏览器 `Box zoom` 仍失败；OpenCFD 2506 未接入；下一步按方案把 `adapter.py` 拆为公共层与 `versions/v12.py`。

### 035｜2026-10-23｜拆分 OpenFOAM 公共层与 v12 版本类

- 基线：完整 86 项 unittest 通过；Foundation 12 是唯一真实接入版本。
- 操作：新增 `solvers/OpenFOAM/versions/v12.py`，把 Foundation 12 的 `version`、`version_key`、`probe` 和分支标识移入；`solvers/OpenFOAM/adapter.py` 只保留公共行为，移除注册装饰器与版本/探测实现，新增 `post_process_tool` 供版本类覆盖；测试改为从 `versions.v12` 导入 `V12`。
- 验证：完整 86 项 unittest 通过；`list cases` 与 `validate couette-2d` 通过。本轮只做重构，未重新运行求解器和浏览器回归。
- 未解决：`probe` 仍读取案例模板（下一阶段解耦）；注册器尚无分支维度；v2506 未接入。

### 036｜2026-10-23｜注册器增加求解器分支维度

- 基线：87 项 unittest 通过；v12 已独立为版本类，v2506 尚未注册。
- 操作：`solvers/registry.py` 新增 `_branch`、`_classes`、`_branch_for_version`；`select` 与 `version_key` 支持分支内排序，跨分支需显式分支，否则报歧义；`compatibility` 只匹配同一分支的变更点；`register_install`/`select_install` 记录并使用安装的 `branch`，旧配置缺 branch 时按已注册版本推断，跨分支 `latest` 报错。`tests/test_registry.py` 新增跨分支 `latest` 歧义与显式版本选择测试。
- 验证：完整 87 项 unittest 通过；`validate couette-2d` 通过。未重新运行求解器与浏览器回归。
- 未解决：`probe` 仍读取案例模板；v2506 Adapter/模板/环境尚未接入；报告“最新版本”分组尚未按分支隔离。

### 037｜2026-10-23｜解耦安装探测与案例选择

- 基线：86 项 unittest 通过；注册器已支持分支，但探测仍读取案例模板。
- 操作：删除 `OpenFOAMAdapter.case_application()`；`v12.probe()` 只用 `main_executable` 探测版本并登记基础工具，不再接收 `case_path`；`select_install()` 去掉 `case_path`；`jobs.py`、`simtest.py` 调用点同步；案例 `application` 改由 `preprocess()` 在模板渲染后校验并登记；删除对应测试。
- 验证：完整 86 项 unittest 通过；`validate couette-2d` 通过；`run --prepare-only` 真实执行成功，两个作业进入 `QUEUED`，随后清理。
- 未解决：v2506 Adapter/模板/环境尚未接入；报告“最新版本”分组尚未按分支隔离。

### 038｜2026-10-23｜新增 OpenCFD v2506 版本类并修正环境加载

- 基线：87 项 unittest 通过；Foundation 12 正常；注册器已支持分支。
- 操作：新增 `solvers/OpenFOAM/versions/v2506.py`，使用 OpenCFD 横幅、`postProcess`、四位 `YYMM` 版本键；`solvers/registry.py` 的 `load_env` 改为把 `env -0` 写入临时文件，避免后台子进程持有管道导致超时，并改用 `shlex.quote(script)` 内联脚本路径，避免 v2506 bashrc 对 `$1` 的错误处理；`compatibility` 遇到其它分支已注册版本时返回不匹配而不是报错；`tests/test_core.py` 增加 v2506 probe 测试并修正跨分支 `select` 调用。
- 验证：完整 87 项 unittest 通过；真实 v2506 probe 成功：version `2506`、branch `OpenCFD`、build `_d6aa836d-20260127`、工具含 `postProcess` 与 `pvpython`（pvpython 需额外 PATH）。未运行 v2506 求解。
- 未解决：v2506 配置/模板/全链路未接入；报告“最新版本”分组尚未按分支隔离。

### 039｜2026-10-23｜增加 v2506 模板变体

- 基线：v2506 版本类已注册；Foundation 模板仍为唯一模板。
- 操作：新增 `cases/couette-2d/templates/OpenFOAM-2506/template.yaml`，`compatibility: "2506"` 并继承 `openfoam-foundation-12`；`tests/test_couette_case.py` 增加 v2506 模板选择、继承链和渲染结果断言。
- 验证：完整 88 项 unittest 通过；`choose()` 对 V2506 选中 `openfoam-opencfd-2506`，继承 Foundation 文件并渲染 `simpleFoam`。未运行 v2506 求解。
- 未解决：v2506 未登记到本机 `config.yaml`，未验证真实串行/MPI、直读/回退和报告。

### 040｜2026-10-23｜修正网格制备：去除 cellZones 与真实 provenance

- 基线：v2506 `checkMesh` 读取 Foundation 12 生成的空 `cellZones` 时报 `unexpected class name`；provenance 仍写死旧几何/网格数。
- 操作：修改 `cases/couette-2d/mesh-preparation/create_example_mesh.py`，blockMesh 后删除 `cellZones`（v2506 不生成且不需要），从 `checkMesh.log` 解析总单元数和包围盒，manifest 改为 `cells: 1920`、`geometry_m: {min,max,size}`；重新生成 `polyMesh`（5 个必需文件）和 `mesh-provenance`；修改 `tests/test_mesh.py` 的假 checkMesh 日志。
- 验证：provenance 现记录 `cells=1920`、包围盒 `0.1×0.01×0.001`；Foundation `checkMesh` 仍通过；v2506 后续 `checkMesh` 与求解可正常读取网格。
- 未解决：v2506 尚未正式提交配置/全链路结果；报告跨分支分组待改。

### 041｜2026-10-23｜加载 v2506 环境并组合 ParaView 路径

- 基线：v2506 bashrc 不包含 `pvpython`；`load_env` 通过管道获取 `env -0` 时被后台子进程拖住超时，且 v2506 bashrc 对 `source "$1"` 处理异常。
- 操作：`solvers/registry.py` 的 `load_env` 把 `env -0` 写入临时文件、用 `shlex.quote(script)` 直接内联脚本路径，并新增 `path_prepend`；`simtest.py setup` 新增 `--path-prepend`；`solvers/OpenFOAM/adapter.py` 的 `dictionary()` 把 `PWD` 设为字典目录，消除 v2506 PWD 警告污染 stdout；`tests/test_registry.py` 增加 `path_prepend` 测试。
- 验证：90 项 unittest 通过；真实 v2506 `setup` 成功登记 `branch: OpenCFD` 与 `path_prepend: /opt/paraviewopenfoam510/bin`；`validate couette-2d --solver OpenFOAM@2506` 通过；v2506 串行/MPI 后续真实运行成功。
- 未解决：v2506 ESI 字典和报告跨分支分组尚未提交。

### 042｜2026-10-23｜v2506 使用 ESI 字典

- 基线：v2506 求解 `simpleFoam` 时要求 `constant/transportProperties` 和 `constant/turbulenceProperties`，Foundation 模板提供的是 `physicalProperties`/`momentumTransport`。
- 操作：在 `cases/couette-2d/templates/OpenFOAM-2506/constant/` 新增 `transportProperties`（`transportModel Newtonian`、`nu`）和 `turbulenceProperties`（`simulationType laminar`），继承 Foundation 其余文件；`tests/test_couette_case.py` 增加 ESI 字典断言。
- 验证：90 项 unittest 通过；v2506 串行与 2 进程 MPI 均 `SUCCEEDED`，归档包含 11 个时刻×2 个场共 22 个 VTU，`pvpython` 直读成功；报告均值 `0.5`、末步速度 x 最大误差 `2.33e-8`。
- 未解决：报告仍按旧方式选择“最新版本”，跨分支会被合并。

### 043｜2026-10-23｜报告按分支选择最新版本

- 基线：`build_charts` 以 `(工况, 求解器)` 选择最新版本，Foundation 12 和 OpenCFD 2506 共用 `OpenFOAM` 名称时会把一个分支挤掉。
- 操作：修改 `report.py`，最新版本分组改为 `(工况, 求解器, 分支)`，`version_key` 传入分支；图例 `label()` 在求解器后追加分支名；`tests/test_report.py` 新增两个分支同时保留的测试。
- 验证：90 项 unittest 通过；待用双分支归档重新生成报告确认两个分支同时出现。
- 未解决：Foundation 12 在网格改动后的回归、README 更新尚未完成。

### 044｜2026-10-23｜双分支全链路验证与文档更新

- 基线：Foundation 12 与 OpenCFD 2506 均已注册；90 项 unittest 通过。
- 操作：更新 `README.md`，补充双分支、`OpenFOAM@12`/`OpenFOAM@2506` 选择器、跨分支 `latest` 歧义、v2506 `--path-prepend` 配置、`icoFoam`/`simpleFoam` 能力和验证边界。
- 验证：v2506 串行与 MPI 均 `SUCCEEDED`，归档 22 个 VTU、`pvpython` 直读成功，报告均値 `0.5`、末步速度 x 最大误差 `2.33e-8`；Foundation 12 在网格去除 `cellZones` 后串行与 MPI 也均 `SUCCEEDED`；合并报告同时保留 Foundation 与 OpenCFD 两个分支的序列。未运行浏览器回归，未验证 OpenMP/CUDA 或其他内核。
- 未解决：同版本多次历史归档会同时出现在合并报告中（按作业而非按执行配置去重），后续可再收敛；Ubuntu 20.04 上 v2506 已实测可运行，但非官方预编译目标。

### 045｜2026-10-23｜修正报告筛选面板层叠顺序

- 目的：筛选面板打开时保持在吸顶标题和重叠内容之上，避免输入框被其他报告区块遮挡。
- 操作：修改 `report_assets/report.js`，在筛选面板打开/关闭时同步所属 `.panel-head` 的 `filter-open` 状态；修改 `report_assets/report.css`，提升打开筛选面板及其所属吸顶标题的层级；修改 `tests/report/check_html_report.cjs`，增加打开状态和计算层级断言。
- 验证：`node --check report_assets/report.js`、`node --check tests/report/check_html_report.cjs` 通过；使用当前 CSS/JS 嵌入临时报告运行浏览器回归，新增筛选层级断言通过，随后仍在既有 `Box zoom did not change range` 断言失败；临时报告及目录已清理。
- 未覆盖：未修复既有 Box zoom 交互失败；未运行完整 unittest 或求解器作业。

### 046｜2026-10-27｜收敛有效求解身份与追溯边界

- 目的：使当前工况的作业 ID 不受其他工况、说明文档、解释器缓存、报告代码和无关求解器实现影响，同时保留完整案例与平台代码追溯清单，并只接受无数字后缀的当前身份协议。
- 操作：修改 `jobs.py`，新增案例源追溯清单、当前工况有效输入清单和当前 Adapter 继承链代码清单；作业身份改用当前 `case.yaml`、当前工况、唯一源网格、所选模板链、当前 Adapter/version code 及执行环境，完整案例和平台代码清单仅写入 provenance。修改 `solvers/OpenFOAM/adapter.py`，输入快照只保存当前案例/工况和所选模板链。修改 `archive.py`，仅接受 `simtest-run` 与 `simtest-identity`，并无条件复核规范身份 SHA-256。
- 操作：修改 `tests/test_jobs.py`、`tests/test_archive.py`、`tests/test_report.py` 和 `tests/test_cli.py`，覆盖动态工况隔离、同值异名工况、有效模板和当前 Adapter 变化、运行期输入防篡改、未知/旧协议拒绝、规范报告夹具及多工况 CLI 前置条件。修改 `README.md`、`ARCHITECTURE.md` 和 `STATUS.md`，同步身份与追溯边界。清空 `artifacts/couette-2d/runs/` 与 `artifacts/couette-2d/reports/` 的旧内容，保留目录和根 `runs/.lock`。
- 验证：WSL Ubuntu 下身份/归档专项 32 项、报告 16 项、完整 96 项 unittest 均通过；`git diff --check` 通过。未执行真实 OpenFOAM 求解或浏览器交互回归；旧归档已按授权删除，不能从工程目录恢复。
