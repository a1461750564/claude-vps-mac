# 验证记录

日期：2026-10-13。这里区分原部署的实际验收、当前配置只读核对和本仓库整理后的本地验证。

## 原部署已验证的行为

原部署记录覆盖官方 CLI 实际调用文本/图像 Read、Edit、Write、只读子 agent 和 Bash；修改在 Mac 独立读回，测试在 Darwin 上通过。随后实际模型会话验证 Bash hook 默认在 Mac 执行、cd 保持 cwd、#vps 返回 Linux、后台任务及超时清理。Mosh 入口显示原生 CLI 与 Pro 登录，并在真实会话使用。

这些是原环境结果，不代表所有插件、MCP、业务项目或后续 CLI 版本都已验收。原始运行记录包含私有资产信息，未复制到本仓库。

## 整理前的实时只读核对

- Mac 正在使用的启动器与原部署源 SHA256 一致。
- VPS 的 claude-mac、mac-run、mac-project、Bash hook 与原部署源 SHA256 一致。
- VPS 到 Mac 的 mac-project check 返回 Darwin 与正确登录账号。
- CLI 版本为 2.1.296；sing-box、tailscaled、SSH、nftables 与用量同步服务 active。
- 既有节点配置指纹与部署记录一致；普通用户凭据存在，root 当前路径的凭据副本不存在。未打印凭据，也未重新触发模型登录。

## 本仓库与原部署的差异

- Mac 启动器的实际地址和主机别名改为私有 JSON 配置；从 PATH 查找 Mosh。
- Bash hook 的 mac-run 位置由当前用户 home 取得，shell 参数进行引用。
- mac-run 在 Mac 端导出 `MAC_PROJECT_DIR`、`MAC_PROJECT_MOUNT`；该行为与原部署 2026-10-13 的线上版本一致。
- 其余核心操作脚本保留原部署实现，包括历史状态目录名 claude-vps-mac。
- 不复制节点部署、系统安全改造、账号迁移、技能、私有日志或插件原型；人工文档替代绑定旧机器的准备脚本。

便携配置版本未替换当前在线入口，未在全新 VPS 重跑整个安装，也未发送新模型请求。不要把本地检查当作新部署的端到端验收。

## 本地验证结果

v0.1.0 整理时的 20 项一次性行为检查，已在 v0.2.0 固化为 `tests/` 下的 49 项单元测试（Python 标准库，不联网、不调用模型），并由 CI 在 Ubuntu 与 macOS 运行：

- 启动器：交互会话使用 Mosh；help/version/print、子命令、非终端和 claude-ssh 使用 SSH；端口池满、Tailscale 预检失败、未安装 Mosh 时回退；占位、公网地址、以 `-` 开头的别名等配置先拒绝；带中文空格的项目路径与含 shell 元字符的参数经 SSH 引用后恢复原 argv。
- Bash hook：保留 timeout/run_in_background；`#vps`、mac-project 与单独 cd 例外；异常输入返回 deny，非 Mac 会话不输出。
- mac-run：cwd 与命令内挂载路径映射，导出项目变量，挂载外与同名前缀目录拒绝执行。
- claude-mac：过宽目录拒绝，挂载缓存参数是否过时。
- mac-project：两层 shell 引用往返；Mac 端守护的退出码、stdin、遗留后台进程、断开通道（返回 129）与 TERM（返回 143）清理整组，仅在 macOS 运行。
- 仓库：脚本语法、示例 JSON 与占位、私钥头和常见令牌扫描。

## 每次新部署仍需验收

按 [操作手册](operations.md) 完成实际 Mac 读写、真实 CLI 工具调用、测试退出码、图像/插件等需要的能力，以及对现有节点、DNS、订阅登录的独立读回。Mosh 中文输入、回滚、网络切换和睡眠恢复仍需真实界面测试。
