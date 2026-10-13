# 部署经验与测量

记录范围为 2026-10-10 至 2026-10-13 的原部署。真实地址、用户名、密钥、凭据、业务路径和账户工单已移除；数值属于当时的样本，不代表其他服务器或时段。

## 如何收敛到当前链路

最初使用 终端工具 的 SSH 主机终端，在 VPS 登录官方 CLI，再通过 Tailscale SSH 操作 Mac。终端工具 对话连接并不能自动把远端 CLI 的原生文件工具指向 Mac；允许远端 终端工具 CLI 控制本机也不是文件系统映射。

因此做了独立 Mac 启动器，输入 claude 自动带上当前项目路径。先靠 Bash 的 mac-project 前缀实现 Mac 操作，随后用 SSHFS 给完整原生文件工具提供真实投影，再用 Bash hook 自动路由，减少手动前缀和跨网逐文件扫描。

终端连接最初走 VPS 公网地址，却被本机代理接管、绕经另一节点。把入口明确改为 Tailscale 后少了一段绕路；Mosh 再改善终端预测回显。它们都没有把模型和订阅移到 Mac。

最后清理不再使用的 终端工具 运行时、反向隧道账号和 root Claude 副本。没有改变正在使用的普通用户登录，不调用 logout；遗留状态目录和访问密钥的名称继续保留，避免破坏会话与连接。

## 原部署测量

| 指标 | 改造前 | 改造后 / 对照 |
| --- | --- | --- |
| 单连接按键级 RTT | 经代理绕行约 308 ms 中位 | Tailscale 直连约 181 ms 中位，n=60 |
| 完整入口版本查询 | 8–11 s | 复用连接约 1.5 s，新项目首次约 3.5 s |
| 全项目文本搜索 | VPS grep 经 SSHFS 约 179 s | Mac rg 经工具桥约 0.5–1.1 s |
| Bash 调用 | 手写桥约 0.46 s | 自动 hook 约 0.5–1.05 s |
| Read / Edit | VPS 本地磁盘约 0.02–0.03 s | SSHFS 约 3.05 s / 3.1–4.1 s；真实会话 Edit 中位约 7.5 s |
| 超时后的进程 | 非 PTY SSH 可能留有 Mac 子进程 | 进程组守护实测清理无残留 |
| SSHFS 挂载 | 11 个，包含过宽根目录 | 启动时回收空闲挂载，保留忙项目 |
| CLI 内部 git status（30 文件仓库） | VPS git 经 SSHFS 37–42 s | 经 mac-git 在 Mac 执行约 0.5 s |
| 新会话第一个 API 请求 | 启动后 42.4 s | 5.6–7.2 s，n=3 |

搜索测试同时改变了执行位置和工具，体现工作流收益，不能用它计算 SSHFS 单独的性能提升倍数。Bash hook 是功能简化而不是每次执行更快；约 0.5 s 网络等待仍然存在。

## 文件缓存的取舍

一次原生 Edit 测到约 51 个 SFTP 请求、约 20 个串行往返。在约 180 ms RTT 下，单次小文件编辑也会耗费数秒。

原部署验证同大小、同一秒外部编辑、原子替换、新建和删除后，选择保留 direct_io 与同步写入，仅缓存元数据：目录、属性与不存在项约 2 秒，已有目录项约 10 秒。更激进的内容缓存有读到旧内容的风险，不将其当作免费提速。

有效的使用习惯是：大范围浏览/搜索用一次 Mac Bash，原生 Read 只读取即将编辑的文件与图像，合并同一文件的修改，机械批改用 Mac 脚本后检查 diff。不要为了减少调用数而跳过必要验证。

## CLI 内部的 git

Bash hook 只改写模型发起的 Bash 调用；CLI 自己的 git 调用不经过 hook，会在 VPS 的挂载目录执行。2026-10-13 在 30 个文件的本仓库实测：VPS git 经挂载执行 `status --short` 37–42 s，`log -n 5` 13 s，`rev-parse` 也要约 3 s；同样命令在 Mac 本地约 5 ms。Mac 写入的索引记录的是 Mac 的 inode 与时间戳，经 SFTP 看到的不一致，git 只能逐个文件重新读取内容。不带 `--no-optional-locks` 的 `git status` 还会把 VPS 视角的时间戳写回 Mac 的 `.git/index`。

测量方法不消耗模型额度：在挂载目录用 `ANTHROPIC_BASE_URL=http://127.0.0.1:9 claude -p hi --no-session-persistence --debug-file …` 启动，PATH 最前放一个记录调用的 git，请求在本机被拒绝，也不写会话记录。CLI 2.1.296 通过 PATH 查找 git；启动约 0.6–3.8 s 时并行发起 `remote get-url`、`status`、`log`、`config user.name`，第一个 API 请求等 git status 返回后才发出，即启动后 42.4 s。

mac-git 让这些调用经 mac-project 在 Mac 执行，每次约 0.5 s；同一测量下第一个请求在 5.6–7.2 s 发出，其余时间是 git 以外的启动读取。status、log、remote、rev-parse、ls-files、worktree、symbolic-ref、diff-files 共 10 组命令与 VPS git 经挂载的输出和退出码一致。

取舍：只有 `rev-parse`、`worktree` 的输出做路径映射，其余输出原样传回，避免改动文件内容；Mac 上 git 版本与配置以 Mac 为准，VPS 的凭据程序、SSH 命令和跟踪变量不转发。CLI 启动时最多约 5 个 git 并行，与 SSHFS、Bash 共用一条 SSH 主连接；macOS sshd 默认每条连接 10 个会话，多个会话同时启动可能超出，此时该次 git 失败，CLI 缺少 git 上下文但仍可使用。

## CLI 原生搜索

`USE_BUILTIN_RIPGREP=0` 是官方提供的系统 rg 入口；在 Mac 项目会话把 mac-rg 放到 PATH 最前，使 Glob/Grep 的 rg 调用经 mac-project 执行。正则、glob 和命中文本保持原样，只转换文件参数与结果路径；VPS 插件、配置等目录继续用 VPS rg。[官方环境变量说明](https://code.claude.com/docs/en/env-vars)

2026-10-13 在本仓库按相同参数交替测量 3 次：16 个 Python 文件的枚举由中位 73.929 s 降到 0.795 s，147 行匹配的文本搜索由 13.730 s 降到 0.747 s。文件集合、命中文本及退出码一致。它测量的是 rg 进程；模型响应、Glob 的后续结果处理和大型项目需另外验收，当前真实模型工具调用受 Pro 会话额度限制。Read/Edit 仍采用原有 SSHFS，不增加内容缓存。

## 为什么保留原生 CLI 和 SSHFS

曾做过插件拦截 Read/Edit/Write/Bash 的隔离原型，能在 Mac 夹具上执行，但需维护 CLI 版本相关的工具输入输出、图像与会话语义，未替换生产路径。本项目不附带它，不把有限原型验收写成完整替代 harness。

增量同步可让 VPS 本地文件访问快，但会产生第二份源码和冲突处理、依赖存储及同步时机；不符合本次“项目只在 Mac”的决定。当前 SSHFS 路线用性能代价换取更小的集成维护面。

官方 Remote Control 解决对话接入，不会自动把 CLI 执行主机的文件系统换成另一台电脑，不能单独代替本项目的操作通道。

## 资源和待验收项

单会话 CLI RSS 约 389–434 MiB，mosh-server 约 11 MiB，每个 sshfs 约 2–8 MiB，同机节点约 82 MiB；RSS 简单相加不等于实际物理内存需求。

2 GiB + swap 的原环境在轻负载下可用，不保证复杂项目、多个 agent、多会话都不会内存紧张。新建优先 4 GiB；不要把四个 Mosh 端口等同于四个会话的资源保证。

Mosh 在真实会话有主观流畅反馈，但中文输入法、多行粘贴、长对话回滚、晚高峰 UDP、Mac 睡眠后恢复仍缺完整体验验收。Git 启动开销只在 30 个文件的本仓库测量；路由后 git 在 Mac 本地磁盘执行，但 CLAUDE.md、设置等其余启动读取仍经 SSHFS，大型项目未测。

这些缺口应在真实使用中验证，而不是再加没有测量依据的“加速参数”。
