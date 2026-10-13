# 链路与边界

## 不变目标

CLI、官方订阅登录和模型请求在 VPS；源码、依赖、构建、测试在 Mac。Mac 终端只负责显示对话、输入任务和选择项目。住宅出口是原部署的网络条件，并不是本项目生成或验证的能力。

## 三条通道

| 通道 | 路径 | 作用 |
| --- | --- | --- |
| 对话 | Mac → Mosh 或 SSH → VPS CLI | 按键和终端画面 |
| 操作 | VPS → SSH/Tailscale → Mac | Bash 命令与 SSHFS 文件操作 |
| 模型 | VPS CLI → 官方服务 | 使用 VPS 原有出站网络 |

Tailscale 不设出口节点、不接受子网路由、不接管 DNS。Mosh 仅监听 VPS 的 Tailscale IPv4；其私网 UDP 端口与 Tailscale 公网直连的 41641/UDP 是两层不同用途的端口。

## 一次启动

1. Mac 启动器读取本机私有 JSON，传入当前项目路径和 CLI 参数。
2. 预检 Tailscale SSH；同时统计 Mosh 端口池占用，复用 SSH 主连接。
3. root 分发器只通过 runuser 切换到普通用户 claude，不执行模型或项目工具。
4. VPS 启动器核对 Mac 返回 Darwin、项目可访问；拒绝用户目录和整盘根目录。
5. 按 Mac 项目路径 SHA256 选择稳定挂载点，普通卸载其他空闲挂载，保留忙挂载。
6. 挂载或复用 SSHFS，设置 `MAC_PROJECT_DIR`、`MAC_PROJECT_MOUNT`，把 git/rg 包装目录放到 PATH 最前，以 `USE_BUILTIN_RIPGREP=0` 启动官方 CLI。

状态目录仍叫 `~/orca-control`，只是继承原项目的路径身份，不依赖 Orca。改变挂载点会改变 Claude 的会话索引，不应随意改名。

## 工具如何运行

- Read/Edit/Write/NotebookEdit 使用原生工具，在 VPS 挂载路径读写 Mac 文件。
- Bash 的 PreToolUse hook 保留 timeout、run_in_background 等输入字段，将命令包装为 mac-run。
- mac-run 根据 VPS cwd 映射 Mac cwd，并将命令内的挂载路径替换成 Mac 路径；在挂载外时拒绝执行。
- mac-project 通过固定 SSH 别名调用 Mac 系统 Python 守护，在 `/bin/bash` 独立进程组中执行命令，转发 stdin/stdout/stderr 和退出码。
- CLI 自身的 git 调用（会话开头的 status/log、diff、worktree）经 PATH 上的 mac-git 包装，用同一通道在 Mac 执行。挂载外的目录、参数或环境变量含 VPS 路径、`--version`/`help` 时仍用 VPS git。`rev-parse`、`worktree` 输出中的 Mac 项目路径换回挂载路径；Mac 上设置 `GIT_CEILING_DIRECTORIES`，仓库查找止于项目目录，与挂载上的结果一致。
- Glob/Grep 使用 PATH 上的 mac-rg，在 Mac 本地运行 rg；只映射文件参数与结果中的路径，保留正则、glob、命中文本、JSON 偏移和退出码。VPS 路径、版本/帮助、主机专用处理器或非标准输出格式仍使用 `/usr/bin/rg`。已选择 Mac 路由的调用若 SSH 失败，不会在 VPS 重新搜索。两端都需要 rg；切换设置只属于 Mac 项目会话。[官方环境变量说明](https://code.claude.com/docs/en/env-vars)
- 命令结束、超时或通道关闭时清理整个进程组；持续服务需让主进程保持前台，并使用工具的 run_in_background。
- 命令首行或末行末尾的 `#vps`、已有 mac-project 调用、单独 cd 不走 Mac 包装。单独 cd 用来保存原生 Bash 的 cwd；export 不跨调用保存。

这些路由是工作流，不是安全沙箱。Bash 命令中的挂载路径替换是文本替换，包含该路径的数据文本也会改变；rg 的命中文本不参与路径替换。项目 hooks、MCP、插件、语言服务器仍按它们自己的执行主机运行，不能从“工具全保留”推导为“全部在 Mac 执行”。

## 一致性和权限

SSHFS 用 direct_io 避免文件内容缓存；同步写入等待 Mac 返回，元数据缓存仍可能短暂滞后。它避免双向副本同步，却没有解决本地编辑器、多个 Claude 会话同时写同一文件的竞争。

Mac 公钥限制来源地址、禁用转发和 PTY，但普通 SSH 仍继承登录账号的文件权限；只挂载项目不能阻止 Bash 访问该账号可读的其他目录。独立账号和真实文件权限是另一项工程，本项目没有声称完成目录隔离。

CLI 的 bypassPermissions 不授予 Linux root，也不关闭模型安全规则。VPS 保存订阅令牌、会话记录和读过的代码上下文，项目“不建副本”不等于“内容从不离开 Mac”。

## 失败与回退

没有 Mosh、非交互调用、help/version/print、端口池已满时使用 SSH。Tailscale 入口预检失败时尝试公网 SSH，但 Mac 操作仍依赖 Tailscale；整个 tailnet 中断时不能保证启动成功。

Mosh 启动后 UDP 握手失败不会自动再启动一个 SSH 会话，避免未知状态下产生重复进程。手动用 claude-ssh 重新进入前，核对遗留会话。Mosh 终端恢复也不代表离线期间的文件操作成功。[Mosh 官方说明](https://mosh.org/)
