# Codex 舰队配置器 / Codex Fleet Configurator

Windows / macOS 中文桌面工具，提供舰队模式总开关，可独立选择三个子 Agent 职责模板的模型、推理等级及服务来源。主控完全由 Codex 当前任务界面选择；工具不设置主控默认值。

独立社区项目，采用 [MIT 许可](LICENSE)，与 OpenAI 无隶属关系。程序只操作本地配置，不调用模型 API、不上传用户数据。

## 下载

前往 [GitHub Releases](https://github.com/mahanyu0322/codex-fleet-configurator/releases/latest) 下载，程序包已包含 Python 运行时。

| 系统 | 下载 | 使用方式 |
| --- | --- | --- |
| Windows 10/11 x64 | [Windows ZIP](https://github.com/mahanyu0322/codex-fleet-configurator/releases/latest/download/Codex-Fleet-Configurator-windows-x64.zip) | 解压后双击 `Codex Fleet Configurator.exe` |
| macOS 14+ / Apple Silicon | [Mac arm64 ZIP](https://github.com/mahanyu0322/codex-fleet-configurator/releases/latest/download/Codex-Fleet-Configurator-macos-arm64.zip) | 解压后将 `.app` 拖入“应用程序”并打开 |
| macOS 15+ / Intel | [Mac x64 ZIP](https://github.com/mahanyu0322/codex-fleet-configurator/releases/latest/download/Codex-Fleet-Configurator-macos-x64.zip) | 解压后将 `.app` 拖入“应用程序”并打开 |

可使用 Release 中的 `SHA256SUMS.txt` 核对下载文件。初版没有 Windows Authenticode 签名或 Apple Developer ID 公证，系统可能提示无法验证开发者；Mac 包使用 ad-hoc 签名。无需、也不应关闭系统安全保护。平台构建与验证方式见 [构建说明](docs/BUILDING.md)。

## 使用
1. 打开解压后的 EXE 或 APP。程序启动时仅读取，不自动写入设置。
2. 选择全局配置，或选中项目目录。项目配置位于项目的 `.codex` 中，需由 Codex 信任该项目。
3. 使用“启用舰队模式”总开关：勾选为舰队模式，取消为非舰队模式。关闭后由主控独立完成任务，多 Agent 工具关闭；子 Agent 的模型、等级、提供方和并发数保留供下次开启使用，关闭时也可以预先调整这些参数。
4. 分别选择代码与调用链、测试与回归、日志与兼容性三个模板的模型和推理等级。可使用“全部设为 Luna / 极高”预设后逐行调整，也可手动输入模型 ID；服务来源应选择已配置且支持该模型的来源。并发上限可直接输入正整数；没有已有并发配置时初始值为 8，模型预设不改变并发数或总开关。
5. 检查预览中的目标模式和配置，再点击“保存并应用”。切换开关本身不立即写入；保存会自动备份原文件。
6. 开启目标项目的新任务，必要时重启 Codex。已有任务可能保留旧状态，正在运行的子 Agent 不会被此工具停止。当前任务的模型选择、显式启动参数、已选 profile、管理员配置可能优先于配置文件；程序不强制切换正在运行的任务。
7. 恢复时选中对应备份并恢复。配置文件只恢复本工具管理的子 Agent 字段及总开关，保留当前主控及其他字段；子 Agent 字段冲突或角色/规则文件被后续修改时拒绝覆盖。恢复本身也会生成备份，允许撤销恢复。

## 能力与限制
- 总开关同时写入 `agents.enabled` 和 `features.multi_agent`；关闭时另写 `features.multi_agent_v2=false`，避免 V2 路径绕过关闭。关闭时只将本工具管理的 AGENTS.md 规则块替换为“非舰队模式”，不删除角色文件；开启时恢复由已保存参数生成的分工规则。
- 开关按所选文件读取：`features.multi_agent_v2=true` 优先显示开启；否则优先 `agents.enabled`，缺失时兼容读取 `features.multi_agent`，均缺失时按 Codex 默认启用状态显示。两个字段不是同义别名，兼容回退仅用于界面显示。此处展示目标文件的配置，不是 Codex 运行时合并结果；项目设置、模型元数据、选定配置方案或管理员约束可能影响实际生效状态，启动不会自动写入。
- 若原来显式启用 V2，关闭总开关会禁用 V2；再次开启使用常规舰队模式，不自动重新开启实验性的 V2。备份恢复可还原本次关闭前的 V2 状态；旧版或未改动 V2 的备份不会回退当前 V2 选择。
- 三个专用角色可分别选择模型、推理等级和已配置来源。`xhigh` 显示为极高，`max` 显示为超高，`ultra` 显示为 Ultra。主控模型、推理等级和服务来源在保存及备份恢复时均保持原值，包括恢复旧版备份时。
- 模型列表来自当前 Codex 主目录的 `models_cache.json`，并合并现有配置中的模型；缓存缺失时使用内置模型目录。内置列表包含 Astra、Sol、Terra、Luna、GPT-5.5、Codex Spark。
- 选择器按模型目录限制推理等级；自定义模型允许输入，实际支持情况以服务端为准。本工具不发送模型 API 请求，不验证账户订阅、额度或第三方服务可用性。
- 通用子 Agent 默认模型和等级采用第一个子 Agent 的选择。Codex 没有同等的通用子 Agent 服务来源配置项，因此通用子 Agent 的来源继承主控；三个专用角色明确保存各自来源。
- 原有其他自定义角色不批量修改，其中显式设置的模型、等级仍然有效。工具通过 AGENTS.md 的专用分工规则引导使用 `fleet_code`、`fleet_tests`、`fleet_integration`。
- 默认子 Agent 并发值为 8，取自官方文档示例，不是官方固定上限。工具不再设置 3 或 8 这样的额外硬上限，可直接输入 4、16 等其他正整数；仅校验正整数和 TOML 整数表示范围。已有配置按原值读取，不因加载或使用模型预设而被改成默认值。
- 并发不含主控。三个配置行是职责模板，不是固定的三个运行实例；同一模板可用于多个独立子任务。比如两个代码分析实例分别检查前端和后端。并发数不会增加模板行，也不会自动创建子 Agent，实际调度仍受 Codex 运行环境限制。正在运行的任务可能保留启动时的并发设置；新建任务，必要时重启 Codex 后加载新配置。只读是角色行为约束，不是独立操作系统沙箱。
- 不修改认证文件、依赖、服务端数据、运行中会话或 Codex 进程。

## 保存范围
全局目标：Codex 主目录（Windows 默认 `%USERPROFILE%\.codex`，macOS 默认 `~/.codex`，尊重进程中的 `CODEX_HOME`）下的 `config.toml`、`agents/fleet_code.toml`、`agents/fleet_tests.toml`、`agents/fleet_integration.toml` 和 `AGENTS.md`。从 Finder 打开时通常不会继承只在终端中设置的环境变量。

项目目标：项目 `.codex` 下的配置与三个角色文件，以及项目根目录的 `AGENTS.md`。

只编辑 `agents.enabled`、`agents.max_concurrent_threads_per_session`、`agents.default_subagent_model`、`agents.default_subagent_reasoning_effort` 和 `features.multi_agent`，关闭时同步禁用 `features.multi_agent_v2`；删除已被新并发配置取代的 `agents.max_threads` 旧别名。保留根级 `model`、`model_reasoning_effort`、`model_provider` 的现有值或缺省状态，以及原 TOML 注释、MCP、服务来源、profile、权限等其他字段。规则仅替换本工具自己的开始/结束标记之间内容；遇到同名非本工具角色拒绝覆盖。

## 备份与异常处理
每次实际变更前，备份原始字节、应用后字节和校验值到目标配置目录的 `fleet-config-backups/<时间>-<随机号>`。备份可能包含原配置中已有的敏感值，应与 Codex 配置一样仅留在本机。预览与交付物不会复制原始配置内容。

macOS 新建备份目录权限为 `0700`，备份文件为 `0600`；Windows 使用用户目录已有 ACL。程序不会批量更改历史备份权限。

恢复配置文件时逐项检查以上子 Agent 字段是否仍匹配备份应用后的值，再合并原值；当前主控和其他配置可以继续调整。旧版备份曾包含的主控修改不再恢复。角色文件及规则文件继续采用完整字节冲突检测。升级程序本身不重写现有配置，也不会清除旧版留下的主控默认值；实际主控继续在 Codex 界面选择。

保存使用同目录临时文件和原子替换；中途写入失败时尝试撤销已经写入的文件。若外部程序同时改动目标或回滚失败，界面会给出具体错误和备份位置，不覆盖外部改动。突然断电/强制终止不能视为完整事务：保留 preparing/recovery_required 备份与锁文件供诊断；确认没有配置器运行后才能移除 `.fleet-config.lock`。

冲突检测在加载、提交及临时文件写完后进行，但普通文件系统没有跨进程的“内容比较并替换”操作；最后一次检查和替换之间仍存在极短竞态窗口。保存期间请避免同时用其他编辑器修改相同配置文件。

## 开发与验证
- Python 3.11 + Tkinter + tomlkit 0.13.2；发行版已打包运行时。推荐在虚拟环境中安装 `requirements-build.txt`。
- `python main.py` 启动源码 GUI。
- `python -m unittest discover -s tests -v` 运行临时目录验证，禁止把真实用户配置作为测试写入目标。
- `python build.py` 在当前系统原生构建、验证程序包，并输出 ZIP 到 `dist/release`；Windows 也可使用 `pwsh -File build.ps1`。
- `--config-dir` 与 `--instructions` 参数可指定隔离测试目录；`--smoke-test` 仅用于检查图形程序启动。

详细命令及发布流程见 [BUILDING.md](docs/BUILDING.md)。贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全说明见 [SECURITY.md](SECURITY.md)。

## 文档依据
- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/config-basic
- https://developers.openai.com/codex/config-reference
- https://developers.openai.com/codex/models

配置字段和本机模型元数据核对日期：2026-09-14。
