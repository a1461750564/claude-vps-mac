# 使用、验收与回退

## 日常使用

| 操作 | 命令 |
| --- | --- |
| 在 Mac 项目目录启动 | claude |
| 继续最近会话 | claude -c |
| 强制 SSH 对话 | claude-ssh |
| 正常退出 | /exit |
| 确认 Bash 执行主机 | 让 Claude 执行 uname -s; pwd |
| 在 VPS 执行某条 Bash | 命令首行或末行末尾加 #vps |

`uname -s` 正常为 Darwin；`uname -s #vps` 为 Linux。macOS 使用 bash 3.2 与 BSD 工具；export 不跨调用持久保存。持续开发服务应以前台进程配合 run_in_background，`command &` 后立即退出会被 Mac 进程守护清理。

关闭 Mosh 窗口可能保留 VPS 会话，失联 4 小时后结束；这不等于杀掉某个后台任务。用 `/exit` 正常退出。四个 UDP 端口是终端容量，不是 2 GiB VPS 能稳定运行四个 Claude 会话的承诺。

## 首次验收

先在 Mac 仓库目录运行 `scripts/cvm doctor`。它核对两端脚本、VPS CLI、双向连接、Hook、git/rg 包装和 Mosh 端口，检查当前 PATH 中的启动入口，并经 `mac-project exec` 验证 Mac 登录环境的 Git/rg。它会通过安装路径执行 `claude --version`，但不运行模型，也不写测试文件。CLI 版本变化时会提示重做验收。

`doctor` 不判断出口 IP 的地理位置，也不检查时区、语言与时钟同步；全部 OK 不能代替下方的 [运行环境验收](#运行环境验收)。安装前的环境准备按 [VPS 配置](setup-vps.md#配置-claude-出口的时区与语言) 完成，不等到 doctor 才处理。

使用独立测试目录，不直接以业务项目试错。以下既是首次安装验收，也是 CLI 更新后的最低回归范围：

1. 在 Mac 项目所在磁盘新建一个空的临时目录，记下绝对路径。VPS 以 `claude` 用户运行 `mac-project check`，核对 Darwin 和 Mac 账号。再将以下命令中的路径换成该临时目录：

   ```bash
   mac-project exec '/absolute/Mac/path/Claude 验收' \
     'git --version && rg --version && printf "%s\n" cvm-write-ok > .cvm-write-check && cat .cvm-write-check'
   ```

   确认输出版本与 `cvm-write-ok`，并在 Mac 独立读回 `.cvm-write-check`。这一步验证回连命令和目录权限。再在 Mac 的临时目录运行 `git init`，供下面的 Git 路由检查使用。
2. 在实际使用的 Mac 终端，用 `type -a claude`、`type -a claude-ssh` 核对入口。进入临时目录运行 `claude-ssh --version`，验证启动器能以 VPS 普通用户建立项目挂载并运行官方 CLI。再运行 `claude-ssh` 核对订阅、权限模式，并完成下方运行环境验收；启用 Mosh 后再验一次。
3. 在对话中调用 Bash 执行 `uname -s; pwd`，检查 Hook 自动路由。执行 `uname -s #vps` 应返回 Linux。`command -v git #vps` 应返回 `~/.local/libexec/claude-mac/git`，`git rev-parse --show-toplevel #vps` 应返回临时项目在 VPS 上的挂载路径。
4. 准备一个文本夹具和独立测试，让 Claude 原生 Read、Edit、Write；Mac 本机独立读回 diff，运行测试并核对退出码和 Darwin，不修改测试断言。
5. 如需图像、子 agent、Notebook、MCP、项目 hooks，逐项验证真实工具调用和执行主机。基本文本验收不能代表这些能力全部可用。
   搜索路由需在独立目录实际调用 Glob 与 Grep，核对文件列表、命中文本、中文空格路径及无匹配结果；直接运行 rg 不能替代模型工具调用的验收。
6. 在无业务影响的 sleep 测试中验证超时和停止后 Mac 子进程结束；对真实编辑中断先读回状态，再决定重试。

全新 VPS、其他 CLI 版本和新增能力都按上列步骤独立验收；历史结果见 [验证记录](validation.md)。

### 运行环境验收

先在 VPS 管理终端检查 `timedatectl show -p Timezone -p NTPSynchronized`：系统时区应符合已确认的实际出口地区，`NTPSynchronized=yes`。然后在 Mac 临时项目中分别使用 `claude-ssh` 和配置好 Mosh 后的 `claude` 新开会话，在各自会话的 Bash 工具中执行：

```bash
id -un; uname -s; date '+%F %T %Z %z'; locale; locale charmap #vps
```

`#vps` 必须保留，否则默认测到的是 Mac。两次都应返回 `claude`、`Linux`、符合出口地区的时间与偏移，以及预期的语言和 `UTF-8` 字符集。例如洛杉矶示例应使用 `en_US.UTF-8`，时间偏移随夏令时变化。Mosh 可能因未安装或端口占满回退 SSH；只有实际进入 Mosh 并确认 `mosh-server` 监听对应 Tailscale 地址时，才记录为 Mosh 验收通过。

核对实际 CLI 访问 Anthropic 的代理/路由日志与准备阶段一致；不以 Mac 出口、root shell 或普通 IP 查询站的出口代替。若语言或时区不一致，检查 VPS 用户 `settings.json` 中的 `env.TZ/LANG/LC_ALL/LANGUAGE`，以及项目、项目本地、受管设置和 `--settings` 的覆盖。按 [固定 Claude 会话环境](setup-vps.md#固定-claude-会话环境) 修正后新开会话复验；不要求把整台 Mac 改成服务器语言。

## 中文状态栏

按 [启用步骤](setup-vps.md#7-可选中文状态栏) 合并 `statusLine` 后，在 VPS 的 `claude` 用户 shell 中回放一份最小数据：

```bash
printf '%s\n' '{"model":{"display_name":"示例模型"}}' |
    COLUMNS=56 /usr/bin/python3 -I "$HOME/.claude/statusline-zh.py"
```

确认能看到模型名和上下文、输出速度、缓存、5 小时额度、本周额度及费用估算的占位。用已有会话核对实际字段，缩窄终端时先缩进度条，再按字段换行。若会话提供暖缓存的到期时间，保持窗口空闲，检查倒计时随刷新递减。可恢复已有会话完成检查，无需发送测试消息。

上下文采用最近一轮普通输入与缓存读写的总和。进程环境或用户设置提供有效压缩窗口时显示“窗”，否则使用 CLI 提供的模型窗口。输出速度根据会话日志尾部的请求与响应统计，扫描上限为 512 KiB，缺少对应记录时显示占位。派生缓存保存在脚本旁的 `cache/statusline-zh/`，保存文件指纹和时间、token 统计。遇到“输出 日志异常”时查看脚本的标准错误，再核对日志权限与格式。

回退时在 VPS 用户设置里恢复原 `statusLine` 值，原先没有该键时移除它。核对当前值仍是本次启用的配置，保留之后的手工修改。若需恢复脚本，使用 [定点回退](#定点回退) 中的安装备份。派生缓存可重建，会话日志保留在原处。

## 诊断顺序

先运行 `scripts/cvm doctor`，从 FAIL 项开始排查。

1. 核对 Mac 在线、项目目录可访问，确认报错来自 SSH 入口、回连还是文件挂载。
2. 查两端 `tailscale status` 和 `tailscale ping`，再验证实际 SSH。若 Tailscale 显示在线但 SSH 超时，用 Mac 的 `route -n get <目标 Tailscale IP>` 核对是否走隧道；若走本地网关，检查是否有其他 TUN 旁路覆盖 `100.64.0.0/10`。
3. 查 VPS claude 用户的 mac-project check；若失败，核对 Mac 远程登录、公钥来源限制、固定主机密钥、tailnet ACL。
4. 新会话首条回复前等待很久时，先核对 `command -v git #vps`：CLI 要等 git status 返回才发第一个请求。对话卡顿用 claude-ssh 做对照；文件操作慢则分别测 Mac 直接执行、mac-project、SSHFS 同一工作负载。
5. 查看 mosh-server 监听和端口池：VPS root 执行 ss -Hlun、pgrep -a mosh-server；核对是否只绑定 tailnet 地址。

## 故障处理

- Tailscale 整体不可达：公网 SSH 只可能救回对话入口，不能替代 VPS 到 Mac 的操作通道。
- Mosh UDP 失败：手动用 claude-ssh，先确认原会话是否仍在，不重复提交不确定是否执行过的修改。
- SSHFS 停滞：退出使用该项目的全部会话后，以 claude 用户普通 fusermount3 -u 卸载对应挂载，再重启入口。不用懒卸载或强制拆除忙挂载。
- 写入后断连：读取实际 Mac 文件、核对 diff 与测试，不能因报错就假设未执行，也不能无条件重放命令。
- 多会话改同一文件：指定一个写入者，或在 Mac 使用明确分工的工作树；SSHFS 不提供冲突合并。
- 主机密钥改变：停止，核对重装或换机事实后更新；不关闭固定校验。

## 已有部署的状态目录

新部署使用 `~/claude-vps-mac` 保存 Mac 登记信息和项目挂载。已有部署若使用其他名称，在 VPS 以普通 claude 用户核对原目录，再建立新名称的符号链接，之后才更新脚本：

```bash
EXISTING_STATE_DIR='/absolute/existing/state-directory'  # 替换为当前实际目录
test -f "$EXISTING_STATE_DIR/mac-connection.json" &&
    test ! -e "$HOME/claude-vps-mac" &&
    test ! -L "$HOME/claude-vps-mac" &&
    ln -s -- "$EXISTING_STATE_DIR" "$HOME/claude-vps-mac"
```

目标名称已存在时先核对，不覆盖。启动器解析符号链接后仍使用原目录作为挂载路径，原会话的 cwd 身份保持不变；mac-project 也从该链接读取原登记文件。此步骤不搬移状态、不卸载忙项目、不迁移 Claude 会话记录。建立链接属于部署配置变更，需在实际升级时执行；仅更新仓库不会改变线上路径。

## 定点回退

保留原文件及修改前指纹；只撤回对应新增项，避免恢复整份旧 settings 或防火墙。

- cvm 安装：每次替换前的文件按原路径存放在 VPS `/var/lib/claude-vps-mac/backups/<时间>/`、Mac `~/.local/state/claude-vps-mac/backups/<时间>/`。先退出受影响的会话，核对当前文件仍为本次安装内容，再从选定的备份恢复单个文件，保留链接、属主与权限；VPS 恢复由 root 执行。目标当前是符号链接时先核对并移开该链接，不让复制穿过链接改写其目标。撤回后 doctor 报告与仓库不同，这是预期。
- 首次新增的文件没有旧备份：依据部署前保存的 dry run 中 `new` 项和安装清单，核对当前指纹后仅移除这些新增文件或链接。不能把“备份中没有”直接认定为本次新增；后续安装会重写 manifest，它不保存完整安装历史。
- Bash 路由：仅删除 hooks.PreToolUse 中 command 为 route-bash-to-mac.py 的条目，保留其他 hook；同步更新工作流提示，随后新开会话。此时 Bash 回到 VPS，不能继续把构建命令当作在 Mac 执行。
- Git 路由：删除 `~/.local/libexec/claude-mac/git`，新会话的 CLI 回到 VPS git（经挂载，较慢）；不需要改 settings 或启动器。
- 搜索路由：恢复备份中的 claude-mac（撤回 `USE_BUILTIN_RIPGREP=0`），新开会话恢复内置搜索；只删除 rg 包装会在 PATH 上缺少 rg 时导致工具报错。
- Mosh：先使用 `claude-ssh`；需要撤除时仅回退本项目加的 Mosh 端口规则。
- Mac 启动器：恢复自己备份的入口；保留已存在的官方 CLI，核对 PATH。
- CLI 登录：不执行 logout，不从历史备份恢复过期令牌。保留普通用户的现有登录与凭据权限。
- 状态路径：保留原目录和实际挂载路径，按上节建立名称链接；不要直接改名或搬移 projects，改变 cwd 身份会影响会话恢复。

## 升级部署

1. 在 Mac 仓库确认工作区、当前提交与目标版本，阅读变更说明；有本地修改时先处理，不覆盖。保留两端当前 `manifest.json`、本轮 dry run 输出和待修改配置的备份，记录实际 CLI 版本。备份留在自己的机器上，不提交仓库。
2. 使用干净、已验证的目标仓库提交。分别运行 `scripts/cvm install vps --dry-run` 和 `scripts/cvm install mac --dry-run`，核对所有 `new/update/modified/unmanaged` 项；后两者需明确接管，不能无差别加 `--adopt`。已有状态目录名称按前文处理。
3. 正常退出使用本桥接的 SSH/Mosh 会话及关联后台任务，然后依次执行 `scripts/cvm install vps`、`scripts/cvm install mac`。安装器逐文件替换，不提供整批事务；中途失败先核对实际文件与备份，不能假定整批都没有安装。
4. 新开临时项目，运行 `scripts/cvm doctor`、运行环境验收与首次工具验收。失败时先停用这次部署，按安装清单定点恢复，不改名或清空项目挂载状态目录。

官方 CLI 与桥接脚本分开更新。原生 CLI 默认会自动更新，因此桥接提交不变时 CLI 版本也可能变化；版本变化后同样执行首次验收。稳定更新通道、指定版本等能力按 [官方版本管理](https://code.claude.com/docs/en/setup#update-claude-code) 配置，不把历史实测版本当作所有环境的默认版本。需要回退 CLI 时使用官方安装方式选择已验证版本，不恢复旧订阅令牌。

## 完整撤除桥接部署

这里撤除的是本项目的桥接能力。项目源码、官方 CLI、订阅登录、Claude 会话、共享的 Tailscale/SSH 服务及其他业务配置保留；若还要删除账号数据或共享服务，另行确定范围。

1. **留好恢复依据并停止会话。** 保存两端安装清单、配置备份、专用 SSH 公钥指纹和原生入口信息。用 `/exit` 退出相关会话，停止这些会话的后台任务。关闭窗口不能证明 Mosh 已退出；按进程用户和命令核对本项目会话，不按进程名批量终止。
2. **解除挂载。** 在 VPS 核对本项目状态目录下的实际 SSHFS 挂载，以 `claude` 用户逐一执行 `fusermount3 -u '<已核对的具体挂载点>'`。忙挂载先查使用者并正常退出，不强制或懒卸载。尚有挂载时不得删除状态目录。
3. **撤除用户设置。** 仅撤销本项目的 Bash Hook、中文状态栏和工作流提示，保留其他设置。专门为此部署加入的环境变量、模型偏好按修改前的值逐键恢复；如果 VPS 官方 CLI 仍按本方案使用出口，保留对应的时区和语言配置。系统时区、locale、时钟同步影响整台服务器，不随桥接卸载自动恢复。
4. **撤回安装文件。** 按 [README 安装位置表](../README.md#组件) 与 manifest 核对脚本和链接。被替换的文件恢复已核实备份，本次新建且指纹未变的文件才移除；有后续修改的先保留处理。Mac 先移除确认属于本项目的 `claude-ssh`、`claude-mosh` 链接，再恢复原 `claude` 入口。使用过 `claude-local` 时核对其原生版本目标，不删除 `~/.local/share/claude` 或 `~/.claude`。新终端用 `type -a claude` 和原生入口的 `--version` 核验。
5. **撤销专用回连授权。** 确认任务已停止，在 VPS 的 `claude` 用户下执行 `ssh -O exit mac-project` 关闭这条专用复用连接（没有主连接时的报错不代表仍有连接）。在 Mac 的 `authorized_keys` 中按已记录的公钥内容/指纹，仅移除本项目那一行；删除公钥行不会终止已经建立的 SSH 会话，应另行核对本项目连接已结束。再逐项移除专用 `Host mac-project` 块、专用私钥/公钥、known_hosts 文件及登记 JSON。共享密钥或文件只撤销本项目条目，不整份删除。
6. **撤销 Mac 管理配置并收尾。** 移除专用 launcher JSON 与 SSH Host 块；管理公钥只有在确认本项目独占、且仍有独立可用的 VPS 管理入口时才撤销。关闭对应的专用复用连接，保留共享连接。只撤销本项目添加的 Mosh 端口规则，不关闭 SSH/Tailscale 服务。挂载全部解除后，空挂载目录可以移除；安装备份、清单、会话数据先保留。确认其他 SSH 和项目使用正常，再按自己的保留策略清理备份。
