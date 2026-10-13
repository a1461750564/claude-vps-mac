# 云端 Claude 操作 Mac 项目

Claude CLI、订阅登录和模型请求在 VPS；项目源码、依赖、构建和测试在 Mac。

- `MAC_PROJECT_DIR` 是已选 Mac 项目；`MAC_PROJECT_MOUNT` 是其 VPS SSHFS 投影。不要创建 VPS 项目副本。
- 原生 Read/Edit/Write/NotebookEdit 在挂载目录操作；Bash 由 hook 在 Mac 对应目录执行。计划、任务、技能和子 agent 保留原生机制；明确给子 agent 当前挂载及 Bash 执行主机。
- 命令在 macOS `/bin/bash` 3.2 执行，使用 BSD 工具。确需在 VPS 执行时，命令首行或末行末尾加 `#vps`；已有 `mac-project` 调用原样执行。单独 `cd` 在 VPS 持续保存 cwd，`export` 不跨工具调用保存。
- 大范围搜索、Git、构建和测试优先合并为一条 Mac Bash。原生 Edit 前仍需按工具要求 Read；减少重复读写，不跳过必要验证。
- 首次接手核对实际项目规范、Git 状态和执行主机。修改后在 Mac 跑项目要求的相关测试并读回 diff。
- Mac 离线时停止依赖步骤，不在 VPS 执行项目测试。断连后的文件修改可能已发生，先读回核对再决定是否重试。
- hooks、MCP、语言服务器和插件不会因 SSHFS 自动迁移到 Mac，启用前核对实际执行主机。
- 使用 Mac 登录账号的正常权限，挂载和提示词不是目录隔离。只处理用户选择的项目，不读取无关个人文件或凭据，不使用 sudo。
- 运行环境遵循项目规范及已有管理器；不因 shell PATH 指向旧全局运行时就直接采用。
- 工具审批模式与模型安全规则独立；不要把跳过审批当作额外系统权限。
