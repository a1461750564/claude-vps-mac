# 配置 VPS

从 [部署顺序](deploy.md) 开始，本页提供 VPS 侧操作细节。适用 Debian 12、固定账号 `claude` 和 `/home/claude`。先固定服务器主机密钥并验证管理 SSH 登录。可以使用原密码或已有管理密钥；已有 Claude Code 和订阅登录时可复用。

## 1. 系统与网络前提

需要可用的 root SSH 入口、TUN 设备、FUSE 和 Claude Code 所需的出站连接。`cvm` 和远端分发器不会从普通 SSH 用户自动提权。加入与 Mac 相同的 tailnet，记录两端 Tailscale IPv4。安装参照 [Tailscale Linux 文档](https://tailscale.com/docs/install/linux)。

新建 VPS 使用 x86_64 或 ARM64、至少 4 GB 内存；先检查根分区及 `/home/claude` 所在分区的剩余空间，给 CLI 版本文件、会话日志和安装备份留余量。项目源码和构建依赖留在 Mac，但 VPS 仍会增长这些运行数据。历史 2 GiB 环境只代表轻负载样本。[官方系统要求](https://code.claude.com/docs/en/setup#system-requirements)

```bash
uname -m
free -h
df -h / /home
test -c /dev/net/tun && test -c /dev/fuse
```

选 VPS 时先确认服务商允许普通用户使用 FUSE。`test -c /dev/fuse` 应退出 0；装了 `sshfs` 和 `fuse3` 并不代表设备可用。设备存在后，还需用 `claude` 用户实际挂载临时项目，见 [首次验收](operations.md#首次验收)。

新加入 tailnet 的 VPS 可按下面的设置启用连接：

```bash
tailscale up --accept-dns=false --accept-routes=false
tailscale status
tailscale ip -4
```

本链路不需要出口节点或子网路由。已有 Tailscale 连接时，先核对是否能满足 [本项目的端口要求](#6-本项目所需的端口)，不改动其他连接。

安装本链路需要的程序，不做全系统升级：

```bash
apt-get update
apt-get install --no-install-recommends python3 openssh-client git ripgrep curl ca-certificates locales iproute2 sshfs fuse3 mosh
```

### 配置 Claude 出口的时区与语言

**这是本项目的部署前置要求：环境检查通过后，才能安装和登录 Claude Code。** 先确认访问 Anthropic 时实际使用的公网出口 IP 及所在地区，确定对应的 IANA 时区和当地语言的 UTF-8 locale，再配置服务器。不能只按服务器购买地区或 Mac 所在地区填写。服务可用地区以官方列表为准。[Claude 支持地区](https://support.claude.com/en/articles/8461763-where-can-i-access-claude)

有出站代理或按域名分流时，通过实际代理配置和路由日志核对 Anthropic 域名的出口；单独访问 IP 查询站不一定经过同一路由。IPv4、IPv6 都可能承载请求时分别核对。出口地区不明确或两条路径不一致时，先处理网络条件，再继续。出口信息只记在自己的部署记录中，不提交到仓库。

以**已核实的美国洛杉矶出口**为例，时区用 `America/Los_Angeles`，locale 用 `en_US.UTF-8`。其他地区替换为自己的值，不直接照抄。时间要求是时区正确且时钟同步，不是手动拨快或拨慢系统时钟。

以 root 先备份 `/etc/localtime`、`/etc/timezone`、`/etc/default/locale` 和 `/etc/locale.gen` 中实际存在的文件，保留符号链接。然后在 `/etc/locale.gen` 启用 `en_US.UTF-8 UTF-8`，执行：

```bash
timedatectl set-timezone America/Los_Angeles
locale-gen
update-locale --reset LANG=en_US.UTF-8 LANGUAGE=en_US:en
timedatectl status
timedatectl show -p Timezone -p NTPSynchronized
locale -a
```

`--reset` 清除系统 locale 文件里旧的分类覆盖值，避免只改 `LANG` 后仍有其他语言生效；使用前须已备份并确认这台服务器的语言调整范围。[Debian update-locale](https://manpages.debian.org/bookworm/locales/update-locale.8.en.html)

本例应看到 `Timezone=America/Los_Angeles`、`NTPSynchronized=yes`，且 `locale -a` 包含 `en_US.utf8`。若时钟未同步，先检查已有的 timesyncd、chrony 等同步服务；使用 systemd 管理的时间同步服务时可运行 `timedatectl set-ntp true` 后再检查。全新 Debian 没有同步服务时，可安装并启用 `systemd-timesyncd`；已有其他同步服务时修复现有服务，不同时安装替代服务。没有同步成功就不继续安装 CLI。

完成后重新连接 VPS。SSH/Mosh 可以传递 Mac 的语言变量，不能只凭系统默认值判断 Claude 实际环境；下一节要在 `claude` 账号中再检查，并为 CLI 固定会话环境。

## 2. 普通账号与官方订阅登录

**全新服务器、账号尚不存在时**，以 root 执行：

```bash
useradd --create-home --user-group --shell /bin/bash claude
chmod 700 /home/claude
```

以 root 切到实际运行 CLI 的账号；以下准备操作在该账号的 shell 中进行，仍未安装 CLI：

```bash
runuser -l claude
```

沿用上面的洛杉矶示例，在安装 shell 中明确设置并验证；其他地区同时替换这组值：

```bash
export TZ=America/Los_Angeles
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LANGUAGE=en_US:en
date '+%F %T %Z %z'
locale
locale charmap
```

要求时间和时区偏移符合出口地区（夏令时按实际日期判断）、`LANG` 与各 `LC_*` 分类采用所选 locale、字符集为 `UTF-8`，且没有 locale 警告。在这个普通用户环境下再次核对实际出口。代理若只写在 root 或交互 shell 配置中，不会自动成为远端分发器的环境；所需代理设置按 [官方网络配置](https://code.claude.com/docs/en/network-config) 为安装 shell 和 CLI 分别落实，保留现有网络方案。

### 固定 Claude 会话环境

在安装和首次登录前，为当前 VPS 的 `claude` 用户准备 `~/.claude/settings.json`。先运行 `install -d -m 700 ~/.claude`；文件已有时先校验 JSON 并备份，然后只合并以下 `env` 键，保留模型、权限、Hook 和其他环境变量。文件不存在时才创建以下 JSON：

```json
{
  "env": {
    "TZ": "America/Los_Angeles",
    "LANG": "en_US.UTF-8",
    "LC_ALL": "en_US.UTF-8",
    "LANGUAGE": "en_US:en"
  }
}
```

这组值必须与前面已核实的服务器环境一致，属于部署配置，不是可选的模型偏好。CLI 的用户 `env` 设置会覆盖终端传入的同名变量；`LC_ALL` 统一 locale 分类，`LANGUAGE` 避免保留客户端的翻译语言。这样 SSH、Mosh 可以继续使用 Mac 自己的语言，而 CLI 按 VPS 的部署环境运行。[官方 env 设置及优先级](https://code.claude.com/docs/en/settings-reference#env)

```bash
chmod 600 ~/.claude/settings.json
/usr/bin/python3 -m json.tool ~/.claude/settings.json >/dev/null
```

还需核对项目、项目本地、受管设置和 `--settings` 是否覆盖了这四个环境变量；存在冲突时按真实生效来源修正，不能只验证用户文件。出口变化后，应同时重新核对系统设置和 CLI 的这四个值，再新开会话验收。

### 安装和登录

**只有实际出口、服务器时区、语言、时钟同步，以及当前安装 shell 和 CLI 环境设置全部确认后，才执行：**

```bash
curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude --version
~/.local/bin/claude
```

按 CLI 提示完成官方登录；用 `/exit` 退出 CLI，再用 `~/.local/bin/claude auth status` 确认登录。随后退出该用户 shell 返回 root。无需 root 先登录，也不需要 npm、第三方 SDK 或 API 中转。[官方安装与认证说明](https://code.claude.com/docs/en/setup)

**已有环境**：复用 claude 用户及其原生 CLI、订阅登录。不要执行 useradd，不调用 logout，不把凭据复制到 Mac 或仓库。不使用原部署的 root→普通用户迁移脚本作为新安装器；需要迁移时另行核对会话、路径和凭据归属。

已有 CLI 的机器同样需要完成上面的环境检查与按键合并，再新开会话；不为满足准备顺序重装 CLI。后续通过 SSH 和 Mosh 分别完成 [运行环境验收](operations.md#运行环境验收)。

## 3. 安装部署源

推荐在 Mac 的本仓库目录用 `scripts/cvm` 安装。它经 `launcher.json` 指定的管理入口以 root 写入桥接脚本，替换前备份到 VPS 的 `/var/lib/claude-vps-mac/backups/`，并在同目录的 `manifest.json` 记录所装的提交。需要先完成 [Mac 管理入口](setup-mac.md#3-mac-到-vps-的管理入口) 和 [启动器配置](setup-mac.md#4-准备启动器配置)，暂不需要安装本地启动器。

已有状态目录使用其他名称时，先按[状态目录升级步骤](operations.md#已有部署的状态目录)建立链接，再安装 VPS 脚本，以保留现有登记和会话路径。

```bash
scripts/cvm install vps --dry-run
scripts/cvm install vps
```

dry run 逐个列出状态：new、same、update，以及 modified（cvm 安装后被改过）和 unmanaged（不是 cvm 装的，例如已有部署）。后两种核对后加 `--adopt` 才会替换。源文件有未提交的修改时 cvm 拒绝安装，线上因此总能对应到一个提交。

不使用 cvm 时，把本仓库放在 VPS 的 `/opt/claude-vps-mac` 手动安装。先为目标文件留备份；已有部署不要直接覆盖未经核对的文件。已有状态目录使用其他名称时，先按[状态目录升级步骤](operations.md#已有部署的状态目录)建立链接，再执行安装。

```bash
cd /opt/claude-vps-mac
install -d -m 700 /root/.local/bin
install -d -o claude -g claude -m 700 /home/claude/.local/bin /home/claude/.claude/hooks /home/claude/claude-vps-mac \
    /home/claude/.local/libexec /home/claude/.local/libexec/claude-mac
install -m 755 scripts/vps/claude-mac-root.sh /root/.local/bin/claude-mac
install -m 755 scripts/vps/mac-project.py /usr/local/bin/mac-project
install -o claude -g claude -m 700 scripts/vps/claude-mac.py /home/claude/.local/bin/claude-mac
install -o claude -g claude -m 700 scripts/vps/mac-run.py /home/claude/.local/bin/mac-run
install -o claude -g claude -m 700 scripts/vps/route-bash-hook.py /home/claude/.claude/hooks/route-bash-to-mac.py
install -o claude -g claude -m 700 scripts/vps/claude-statusline-zh.py /home/claude/.claude/statusline-zh.py
install -o claude -g claude -m 700 scripts/vps/mac-git.py /home/claude/.local/libexec/claude-mac/git
install -o claude -g claude -m 700 scripts/vps/mac-rg.py /home/claude/.local/libexec/claude-mac/rg
```

claude-mac 只在 Mac 项目会话把 `~/.local/libexec/claude-mac` 放到 PATH 最前，CLI 自身的 git 调用随之在 Mac 执行。缺少该文件时 CLI 回到 VPS git，经挂载执行，新会话首条回复前会多等 git status 的时间。

同一目录的 rg 包装负责 Glob/Grep，启动器仅在 Mac 项目会话设置 `USE_BUILTIN_RIPGREP=0`。Mac 的登录环境需已有 rg，VPS 的 `/usr/bin/rg` 负责本机配置、插件等目录的搜索；保留两端正常配置和真实权限。

不覆盖 `/home/claude/.local/bin/claude`：它必须继续指向官方 CLI。

## 4. VPS 到 Mac 的 SSH

以 `claude` 用户生成独立访问密钥，私钥只留 VPS。若已存在本项目的密钥，直接读取其公钥，不重新生成：

```bash
runuser -l claude
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/claude_mac_ed25519 -N '' -C claude-vps-to-mac
cat ~/.ssh/claude_mac_ed25519.pub
```

只把公钥加入 Mac，见 [授权 VPS 公钥](setup-mac.md#2-授权-vps-公钥)。

1. 依据 `examples/vps-ssh.config` 合并当前用户 `~/.ssh/config`，替换 Mac 用户名和 Tailscale IP，保留其他 Host 块。
2. 在 **Mac 本机**读取 `/etc/ssh/ssh_host_ed25519_key.pub`，通过已验证管理路径核对后，在 VPS `~/.ssh/claude_mac_known_hosts` 写入一行：

   ```text
   claude-mac-project ssh-ed25519 __VERIFIED_MAC_PUBLIC_HOST_KEY__
   ```

3. 全新部署先在当前 `claude` 用户 shell 创建登记目录，再依据 `examples/mac-connection.json` 创建其中的 JSON；模板从 Mac 仓库读取，不假设 VPS 已克隆仓库。已有状态目录先按 [状态目录升级步骤](operations.md#已有部署的状态目录) 核对，不覆盖已有登记。

   ```bash
   mkdir -p ~/claude-vps-mac
   chmod 700 ~/claude-vps-mac
   ```

   把模板中的 Mac 用户名、用户 home 和 Tailscale IP 换成实际值后保存为 `~/claude-vps-mac/mac-connection.json`。实际 SSH 目标由前面的 `~/.ssh/config` 决定，登记内容应与之保持一致。
4. config、known_hosts、登记 JSON 和私钥均设为 600，所属用户 claude；登记 JSON 不包含密钥。

   ```bash
   chmod 600 ~/.ssh/config ~/.ssh/claude_mac_known_hosts ~/.ssh/claude_mac_ed25519 \
       ~/claude-vps-mac/mac-connection.json
   /usr/bin/python3 -m json.tool ~/claude-vps-mac/mac-connection.json >/dev/null
   ```

先验证只读连接：

```bash
mac-project check
mac-project exec '/absolute/Mac/project/path' 'uname -s; pwd; git status --short'
```

应返回 Darwin 与真实 Mac 路径。未完成连接时不要启动业务会话。

## 5. CLI 设置与全局规则

将 [`examples/claude-settings.json`](../examples/claude-settings.json) 的 Bash PreToolUse Hook 合并到 `/home/claude/.claude/settings.json`。保留前面固定的环境变量和已有 Hook，不重复添加同一命令；文件由 `claude` 用户持有，权限设为 600。[官方 hooks 格式](https://code.claude.com/docs/en/hooks)

路由 Hook 对转发的 Bash 命令返回 `allow`；安装前要理解其执行权限。它与 CLI 的 `permissions.defaultMode` 分开生效，仅改后者不会改变路由 Hook 的放行行为。

[`examples/claude-preferences.json`](../examples/claude-preferences.json) 是可选的实装偏好示例。想复用这组偏好时，选择所需的键合并，保留已有 `env`、模型、权限和插件设置。示例包含 Opus、对应的思考强度、`272000` 自动压缩窗口、主会话 `1h` 缓存设置和 `bypassPermissions`。模型和配置项以所装 CLI 及账号可用能力为准。[官方模型配置](https://code.claude.com/docs/en/model-config)、[环境变量](https://code.claude.com/docs/en/env-vars)

遥测字段为原部署选择；不使用 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 总开关。遥测关闭可能影响部分远程功能开关，应按实际版本验证。

把 `examples/CLAUDE.md` 中工作流段落合并到现有全局规则，不整份替换其他约定。技能按需要单独安装到 `~/.claude/skills`，本仓库不打包第三方技能。项目 AGENTS.md/CLAUDE.md 的加载行为按 CLI 版本配置，原部署用内置 instructionFiles 选项，非链路成立的前提。

## 6. 本项目所需的端口

| 用途 | 方向 | 端口 |
| --- | --- | --- |
| 管理与 SSH 对话 | Mac → VPS，经 Tailscale | TCP 22，或 VPS 实际 SSH 端口 |
| 项目文件和命令 | VPS → Mac，经 Tailscale | TCP 22 |
| Mosh 对话（可选） | Mac → VPS，经 Tailscale | UDP 60001–60004 |
| Tailscale 直连（按需要） | 到 VPS 的公网 UDP | UDP 41641 |

在自己管理的主机防火墙和 tailnet 访问规则中，按表放行所需方向。Mosh 端口仅向 Mac 的 Tailscale 地址开放。公网 SSH 用于已有管理入口和对话回退，项目脚本不改动该入口或防火墙。

## 7. 可选中文状态栏

`scripts/cvm install vps` 管理状态栏脚本的安装、更新和备份。脚本由 VPS 的 `claude` 用户运行，使用系统 Python 3 标准库。Mac 通过原有终端入口显示状态栏。

需要启用时，以 `claude` 用户先验证并备份现有 `~/.claude/settings.json`。将 [状态栏示例](../examples/claude-statusline.json) 中的 `statusLine` 合并到顶层，保留其他键、文件属主和权限。已有 `statusLine` 时，先保存原值，确认要替换再更新该键。

保存后用 `/usr/bin/python3 -m json.tool ~/.claude/settings.json >/dev/null` 校验 JSON，再按 [状态栏验收与回退](operations.md#中文状态栏) 检查。示例设置空闲时每 10 秒刷新。上下文、缓存和额度以当前会话数据和实际设置为准。[Claude Code 状态栏文档](https://code.claude.com/docs/en/statusline)
