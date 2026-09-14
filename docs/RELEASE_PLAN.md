# Windows / macOS 开源发布计划

目标：同一份 Python/Tkinter 代码支持 Windows 和 macOS；以 MIT 协议发布源码，并提供可直接运行的程序包。既有舰队开关、角色设置、备份恢复和主控由 Codex 选择的规则保持一致。

## 设计

- 界面使用当前系统可用字体，窗口适配屏幕高度；配置默认目录统一使用 `Path.home() / '.codex'`，继续尊重 `CODEX_HOME`。
- Windows x64 原生打包单文件 EXE；macOS arm64 / x64 分别原生构建 `.app`，使用 `ditto` 压缩保留符号链接及执行权限。
- 构建脚本先完成程序包启动探针，再生成 ZIP 与 SHA-256 校验文件。运行和测试都使用隔离配置目录，不包含开发者配置、备份或历史截图。
- GitHub Actions 在 Windows、Apple Silicon Mac 和 Intel Mac 上执行测试及构建。只有全部平台成功后才允许发布对应版本。工作流默认只读，发布步骤单独授予仓库内容写权限。
- 初版 Mac 包使用 ad-hoc 签名，Windows 包不做代码签名；不提供 Apple Developer ID 公证。发布页明确说明系统验证提示及平台要求。

## 检查清单

- [x] 跨平台字体、窗口与文件行为检查，补齐相关回归。
- [x] 构建与程序包探针脚本、三平台工作流。
- [x] README、MIT LICENSE、贡献和安全说明、第三方许可资料。
- [ ] 本地测试、Windows 程序包验证、独立代码和开源内容审查。
- [ ] 新建 GitHub 公共仓库，推送已审查的源码。
- [ ] 三平台 CI 成功，正式 Release 上传程序包和校验文件。
- [ ] 下载并核对 Release 资产，交付仓库与下载链接。

不纳入 Git 的本地材料由 `.gitignore` 排除，首次提交使用显式文件清单；构建不会读取认证文件或上传用户配置。
