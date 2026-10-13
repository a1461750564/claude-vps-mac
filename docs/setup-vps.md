# 配置 VPS

以下是人工分步部署，不是一键改造脚本。适用 Debian 12、固定账号 claude 和 `/home/claude`。先完成管理 SSH 密钥登录并独立测试，保留原会话；复用已有服务器时先核对现有用户、CLI、节点、防火墙和登录状态。

## 1. 系统与网络前提

需要公网管理入口、TUN 设备、正常出站、足够磁盘空间。加入与 Mac 相同的 Tailscale 账号，记录两端 Tailscale IPv4。安装参照 [Tailscale Linux 文档](https://tailscale.com/docs/install/linux)。

原部署的 VPS Tailscale 配置是：

```bash
tailscale up --accept-dns=false --accept-routes=false --exit-node= --netfilter-mode=off
tailscale status
tailscale ip -4
```

不要把 Mac 或其他节点设成出口节点。netfilter-mode=off 代表需自行维护 nftables 的放行；这不是“无需防火墙配置”。已有设备执行 tailscale up 时，应先核对当前选项，不覆盖范围外配置。

原部署另有密钥登录、fail2ban、安全更新、BBR+fq 和 2 GiB swap。它们是系统运维前提，不在本项目自动写入；不得清空现有规则集或照搬绑定旧主机名的历史脚本。见 [系统基线](system-baseline.md)。

安装本链路需要的程序，不做全系统升级：

```bash
apt-get update
apt-get install --no-install-recommends python3 openssh-client git curl ca-certificates locales iproute2 sshfs fuse3 mosh
```

Mosh 两端需要 UTF-8 locale。确认 en_US.UTF-8 已生成；若没有，在 `/etc/locale.gen` 启用该项后运行 locale-gen。系统时区按实际运维需求设置，与本链路的文件路由无关。

## 2. 普通账号与官方订阅登录

**全新服务器、账号尚不存在时**，以 root 执行：

```bash
useradd --create-home --user-group --shell /bin/bash claude
chmod 700 /home/claude
runuser -l claude
```

接下来在 claude 用户的 shell 中安装官方原生 CLI 并本人登录：

```bash
curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude --version
~/.local/bin/claude
```

按 CLI 提示完成官方登录；用 `/exit` 退出 CLI，再退出该用户 shell 返回 root。无需 root 先登录，也不需要 npm、第三方 SDK 或 API 中转。[官方安装与认证说明](https://code.claude.com/docs/en/setup)

**已有环境**：复用 claude 用户及其原生 CLI、订阅登录。不要执行 useradd，不调用 logout，不把凭据复制到 Mac 或仓库。不使用原部署的 root→普通用户迁移脚本作为新安装器；需要迁移时另行核对会话、路径和凭据归属。

## 3. 安装部署源

把本仓库放在 VPS 的 `/opt/claude-vps-mac`，以下仅安装本链路的文件。先为目标文件留备份；已有部署不要直接覆盖未经核对的文件。

```bash
cd /opt/claude-vps-mac
install -d -m 700 /root/.local/bin
install -d -o claude -g claude -m 700 /home/claude/.local/bin /home/claude/.claude/hooks /home/claude/claude-vps-mac
install -m 755 scripts/vps/claude-mac-root.sh /root/.local/bin/claude-mac
install -m 755 scripts/vps/mac-project.py /usr/local/bin/mac-project
install -o claude -g claude -m 700 scripts/vps/claude-mac.py /home/claude/.local/bin/claude-mac
install -o claude -g claude -m 700 scripts/vps/mac-run.py /home/claude/.local/bin/mac-run
install -o claude -g claude -m 700 scripts/vps/route-bash-hook.py /home/claude/.claude/hooks/route-bash-to-mac.py
```

不覆盖 `/home/claude/.local/bin/claude`：它必须继续指向官方 CLI。

## 4. VPS 到 Mac 的 SSH

以 claude 用户生成独立访问密钥，私钥只留 VPS：

```bash
runuser -l claude
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/claude_mac_ed25519 -N '' -C claude-vps-to-mac
cat ~/.ssh/claude_mac_ed25519.pub
```

若密钥已存在，不重新生成。只把公钥加入 Mac，见 [Mac 配置](setup-mac.md)。

1. 依据 `examples/vps-ssh.config` 合并当前用户 `~/.ssh/config`，替换 Mac 用户名和 Tailscale IP，保留其他 Host 块。
2. 在 **Mac 本机**读取 `/etc/ssh/ssh_host_ed25519_key.pub`，通过已验证管理路径核对后，在 VPS `~/.ssh/claude_mac_known_hosts` 写入一行：

   ```text
   claude-mac-project ssh-ed25519 __VERIFIED_MAC_PUBLIC_HOST_KEY__
   ```

3. 依据 `examples/mac-connection.json` 创建 `~/claude-vps-mac/mac-connection.json`。
4. config、known_hosts、登记 JSON 和私钥均设为 600，所属用户 claude；登记 JSON 不包含密钥。

先验证只读连接：

```bash
mac-project check
mac-project exec '/absolute/Mac/project/path' 'uname -s; pwd; git status --short'
```

应返回 Darwin 与真实 Mac 路径。未完成连接时不要启动业务会话。

## 5. CLI 设置与全局规则

`examples/claude-settings.json` 是原部署的参考配置。新装时可使用；已有 `~/.claude/settings.json` 时按键合并，保留其他 env、hooks、权限和插件。文件设为 600、用户 claude。CLI 需要读到 Bash PreToolUse hook。[官方 hooks 格式](https://code.claude.com/docs/en/hooks)

参考模板的权限模式是 bypassPermissions，Bash 路由 hook 也返回 allow：它们都属于原部署明确选择的自动执行策略，不是面向任意环境的安全默认。只改 defaultMode 不等于恢复全部 Bash 审批，改变审批方式时须同时检查 hook。

原部署选择 xhigh；以参谋和节省 Pro 用量为主时可在 CLI 通过 `/effort medium` 调整。模型名称与持久化设置以所安装 CLI 为准，升级后核对 modelSettings 格式，不假定旧示例永久兼容。[官方模型配置](https://code.claude.com/docs/en/model-config)

遥测字段为原部署选择；不使用 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 总开关。遥测关闭可能影响部分远程功能开关，应按实际版本验证。

把 `examples/CLAUDE.md` 中工作流段落合并到现有全局规则，不整份替换其他约定。技能按需要单独安装到 `~/.claude/skills`，本仓库不打包第三方技能。项目 AGENTS.md/CLAUDE.md 的加载行为按 CLI 版本配置，原部署用内置 instructionFiles 选项，非链路成立的前提。

## 6. 防火墙：只增量放行

管理 SSH 与既有 Reality/其他服务规则保持原样。原部署另放行公网 41641/UDP 供 Tailscale 直连；Mosh 内层只放行 Mac 的私网地址。下面的表名必须改成当前受管 nftables 表/链：

```text
udp dport 41641 accept comment "tailscale-direct"
iifname "tailscale0" ip saddr __MAC_TAILSCALE_IPV4__ ip daddr __VPS_TAILSCALE_IPV4__ udp dport 60001-60004 accept comment "mosh-from-mac-tailnet"
```

还需允许 Mac 经 tailscale0 访问 VPS SSH，和 VPS 访问 Mac 的 SSH；tailnet ACL 也必须允许这些方向。默认出站限制、另一套 ufw/firewalld 规则或 ACL 可能继续阻断。

先检查 `nft list ruleset`，在正确链增量添加；将新增规则同步到当前持久化来源，并用 nft -c 校验。**不要 flush ruleset，不整份替换 `/etc/nftables.conf`，不重启节点。**Mosh 不需要向公网开放 60001–60004。

部署完成再执行 [验收步骤](operations.md)，并读回现有节点配置、DNS 与服务状态。
