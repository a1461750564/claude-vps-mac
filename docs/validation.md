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
- mac-project 的进程组清理会在原有时限内重试短暂 `EPERM`，持续权限错误仍报失败。
- 新增 mac-git 与 mac-rg，CLI 自身的 git 调用及 rg 搜索可在 Mac 执行。
- 整理时线上仍为旧部署；2026-10-13 已用 cvm 切换到仓库安装源，具体边界见下节的线上切换记录。
- 其余核心操作脚本保留原部署实现，包括历史状态目录名 claude-vps-mac。
- 不复制节点部署、系统安全改造、账号迁移、技能、私有日志或插件原型；人工文档替代绑定旧机器的准备脚本。

便携配置版本已在原部署切换，未在全新 VPS 重跑整个安装。模型工具调用的验证状态单独记录，不把本地检查当作新部署的端到端验收。

## 本地验证结果

v0.1.0 整理时的 20 项一次性行为检查，已在 v0.2.0 固化为 `tests/` 下的单元测试，v0.3.0 共 93 项（Python 标准库，不联网、不调用模型），CI 配置覆盖 Ubuntu 与 macOS：

- 启动器：交互会话使用 Mosh；help/version/print、子命令、非终端和 claude-ssh 使用 SSH；端口池满、Tailscale 预检失败、未安装 Mosh 时回退；占位、公网地址、以 `-` 开头的别名等配置先拒绝；带中文空格的项目路径与含 shell 元字符的参数经 SSH 引用后恢复原 argv。
- Bash hook：保留 timeout/run_in_background；`#vps`、mac-project 与单独 cd 例外；异常输入返回 deny，非 Mac 会话不输出。
- mac-run：cwd 与命令内挂载路径映射，导出项目变量，挂载外与同名前缀目录拒绝执行。
- claude-mac：过宽目录拒绝，挂载缓存参数是否过时，项目会话的 PATH 与项目变量。
- mac-git：CLI 上下文调用路由到 Mac，子目录与 `-C` 映射；挂载外、VPS 路径、无需仓库的命令留在 VPS；环境变量的转发与丢弃；参数经真实 bash 原样到达 git；真实 git 下仓库查找止于项目目录；`rev-parse` 输出路径映射（含两种 Unicode 形式）；终端 stdin 不交给 SSH 通道。
- mac-project：两层 shell 引用往返；Mac 端守护的退出码、stdin、遗留后台进程、断开通道（返回 129）与 TERM（返回 143）清理整组，以及短暂权限错误重试和持续权限错误报告，仅在 macOS 运行。
- cvm：新装、重复安装不改动、仓库更新先备份、服务器上改过或非 cvm 安装的文件需 `--adopt`、仅权限不同直接修正、链接、dry run 不写入、以 `python3 -c` 运行（远端方式）；doctor 对健康与异常报告的判定。
- mac-rg：正则及 glob 不参与路径替换，文件参数与文件名/JSON 路径映射，保留命中文本与偏移，真实 rg 下的匹配/无匹配/语法错误退出码，CLI Grep 的 `--max-columns 500` 参数，以及连接失败不在 VPS 重放。
- 仓库：脚本语法与可执行位、示例 JSON 与占位、私钥头和常见令牌扫描。

断连清理修复后，本机系统 Python 的 51 项测试通过；额外连续运行断连用例 100 次，均返回 129 并确认子进程消失。忽略 TERM 的独立用例也在 KILL 升级后完成清理，返回 129。

## v0.3.0 在原部署上的实测

使用当前 VPS、Mac 与 CLI 2.1.296，mac-git 复制到 VPS 临时目录并放在 PATH 最前，不改动线上文件。按[部署经验](deployment-experience.md#cli-内部的-git)的方法启动 CLI，不消耗模型额度：第一个 API 请求从启动后 42.4 s 提前到 5.6–7.2 s；10 组 git 命令与 VPS git 经挂载的输出和退出码一致。直接从 SSHFS 挂载运行包装脚本时，Python 会在挂载上的脚本目录查找模块，每次多约 2.7 s，所以必须安装到 VPS 本地磁盘。

### 仓库版本切换

2026-10-13 用 `cvm install vps --adopt`、`cvm install mac --adopt` 安装提交 `1b0c468` 的部署源（包括 v0.2 进程清理、git 路由及 Mac 便携启动器）。替换前逐文件备份，安装后 doctor 全部 OK，线上 SHA256、属主与权限符合仓库清单。CLI 保持 2.1.296、官方 claude.ai Pro；凭据、settings、节点配置、DNS、防火墙、SSH 配置与登记文件指纹未变，ssh/tailscaled/sing-box 的 MainPID 未变。

在线 mac-project 还通过 Darwin/cwd/stdin/退出码 37 的实际通道检查；在 VPS 取消该工具桥接进程后，Mac 测试子进程消失。SSHFS 写入在 Mac 独立读回，同大小原子替换后 VPS 读取到新内容。取消工具通道与关闭外层管理 SSH、Mosh 窗口是不同动作，后者不能用作工具取消的证明。

随后用 `cvm install vps` 安装提交 `1db91c7` 的搜索路由：更新项目启动脚本并新增 rg 包装，其他 5 个 VPS 文件未变；备份位于 `/var/lib/claude-vps-mac/backups/20261013T113313223025Z/`。安装后 doctor 全部 OK，上述 7 个保护文件指纹与 3 个服务 MainPID 再次核对未变，CLI 和 Pro 登录保持有效。

### 搜索路由测量

同一仓库、同一 rg 参数交替执行 VPS `/usr/bin/rg` 经 SSHFS 和临时 mac-rg 经 Mac 桥接，每组 3 次。本仓库的 16 个 Python 文件及 147 行匹配结果，排序后 SHA256 与退出码每次一致。VPS rg 13.0.0，Mac rg 15.2.0，均保持当前 SSHFS 缓存策略。

| 操作 | SSHFS 中位数 | Mac 路由中位数 |
| --- | --- | --- |
| `rg --files --hidden --glob '*.py' <项目挂载>` | 73.929 s | 0.795 s |
| `rg --no-heading -n -H --color never --glob '*.py' 'def ' <项目挂载>` | 13.730 s | 0.747 s |

这是搜索进程耗时，不包括模型响应和 CLI 对结果的后续处理，不代表所有大型项目或时段。

额度恢复后，使用官方 Pro 完成候选及安装后的真实模型验收，均实际调用原生 Glob/Grep；安装后从日常 Mac `claude` 入口启动。独立夹具包含 3 个文件，Glob 返回完整集合，Grep 返回 2 行预期内容，中文空格路径正确；安装后该夹具 Glob 报告 634 ms。PATH 调用记录覆盖 CLI 的实际枚举、排序和 JSON 搜索参数。首次真实验收发现 `--max-columns 500` 被误解析，已补参数处理，并在现有测试中复现修复前的错误空结果；修复后复验通过。

临时候选的实际 VPS → Mac 链路还验证了 NUL 文件名、JSON 路径、命中文本中的 Mac 路径保留，以及退出码 0/1/2。原始记录保存在本机忽略的私有证据目录，未提交账户与连接信息。

## 每次新部署仍需验收

按 [操作手册](operations.md) 完成实际 Mac 读写、真实 CLI 工具调用、测试退出码、图像/插件等需要的能力，以及对现有节点、DNS、订阅登录的独立读回。Mosh 中文输入、回滚、网络切换和睡眠恢复仍需真实界面测试。
