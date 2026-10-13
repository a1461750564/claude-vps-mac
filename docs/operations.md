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

使用独立测试目录，不直接以业务项目试错。以下既是首次安装验收，也是 CLI 更新后的最低回归范围：

1. VPS claude 用户运行 mac-project check，核对 Darwin、真实 Mac 用户和路径。
2. Mac 项目目录运行 claude --version，核对官方 CLI 版本；交互启动时核对订阅和权限模式。
3. 在对话中调用 Bash 执行 uname -s; pwd，检查 hook 自动路由；加 #vps 对照应返回 Linux。
4. 准备一个文本夹具和独立测试，让 Claude 原生 Read、Edit、Write；Mac 本机独立读回 diff，运行测试并核对退出码和 Darwin，不修改测试断言。
5. 如需图像、子 agent、Notebook、MCP、项目 hooks，逐项验证真实工具调用和执行主机。基本文本验收不能代表这些能力全部可用。
6. 在无业务影响的 sleep 测试中验证超时和停止后 Mac 子进程结束；对真实编辑中断先读回状态，再决定重试。
7. 核对节点配置和 DNS 指纹、节点主进程与服务状态、原订阅登录是否变化。把凭据哈希记录放私有证据目录，不提交内容。

新配置模板与原部署源有少量便携性修改，没有重新执行新 VPS 安装或消耗模型额度做完整验收；具体证据边界见 [验证记录](validation.md)。

## 诊断顺序

1. 查资源：VPS free -m、df -h、当前 Claude/mosh/sshfs 进程数量；Mac 是否睡眠或外置盘离线。
2. 查两端 tailscale status、tailscale ping；确认 direct 或 relay，不把一次 ping 当长期线路质量。
3. 查 VPS claude 用户的 mac-project check；若失败，核对 Mac 远程登录、公钥来源限制、固定主机密钥、tailnet ACL。
4. 对话卡顿用 claude-ssh 做对照；文件操作慢则分别测 Mac 直接执行、mac-project、SSHFS 同一工作负载。
5. 查看 mosh-server 监听和端口池：VPS root 执行 ss -Hlun、pgrep -a mosh-server；核对是否只绑定 tailnet 地址。

## 故障处理

- Tailscale 整体不可达：公网 SSH 只可能救回对话入口，不能替代 VPS 到 Mac 的操作通道。
- Mosh UDP 失败：手动用 claude-ssh，先确认原会话是否仍在，不重复提交不确定是否执行过的修改。
- SSHFS 停滞：退出使用该项目的全部会话后，以 claude 用户普通 fusermount3 -u 卸载对应挂载，再重启入口。不用懒卸载或强制拆除忙挂载。
- 写入后断连：读取实际 Mac 文件、核对 diff 与测试，不能因报错就假设未执行，也不能无条件重放命令。
- 多会话改同一文件：指定一个写入者，或在 Mac 使用明确分工的工作树；SSHFS 不提供冲突合并。
- 主机密钥改变：停止，核对重装或换机事实后更新；不关闭固定校验。

## 定点回退

保留原文件及修改前指纹；只撤回对应新增项，避免恢复整份旧 settings 或防火墙。

- Bash 路由：仅删除 hooks.PreToolUse 中 command 为 route-bash-to-mac.py 的条目，保留其他 hook；同步更新工作流提示，随后新开会话。此时 Bash 回到 VPS，不能继续把构建命令当作在 Mac 执行。
- Mosh：先使用 claude-ssh；需要撤除时仅删除 Mosh 专用规则，保留 Tailscale 和既有节点规则。
- Mac 启动器：恢复自己备份的入口；保留已存在的官方 CLI，核对 PATH。
- CLI 登录：不执行 logout，不从历史备份恢复过期令牌。保留普通用户的现有登录与凭据权限。
- 状态路径：不要直接改名 ~/claude-vps-mac/projects；改变 cwd 身份会影响会话恢复。
