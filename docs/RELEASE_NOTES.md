# Codex Fleet Configurator 1.0.0

首个 Windows / macOS 开源版本。

- 舰队模式总开关；关闭时保留参数，由主控独立完成任务。
- 三个可复用子 Agent 模板，独立选择模型、推理等级和提供方。
- 默认并发 8，支持填写其他正整数；主控模型由 Codex 界面选择。
- 全局 / 项目配置、变更预览、自动备份和冲突保护。
- 原生 Windows x64、macOS Apple Silicon 和 Intel 程序包，无需安装 Python。

下载对应 ZIP，解压后打开 `.exe` 或 `.app`。macOS Apple Silicon 需要 macOS 14+；Intel 需要 macOS 15+。Windows 需要 Windows 10/11 x64。

初版没有 Windows Authenticode 签名或 Apple Developer ID 公证，系统可能提示无法验证开发者。Mac 包仅做 ad-hoc 签名。请按需核对 `SHA256SUMS.txt` 并自行决定是否运行；不要关闭系统安全保护。

保存后由 Codex 新任务加载配置，必要时重启 Codex。程序不会中断已有任务，也不验证模型账户权限或额度。
