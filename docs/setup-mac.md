# 配置 Mac

从 [部署顺序](deploy.md) 开始，本页提供 Mac 侧操作细节。本机需要 Tailscale、远程登录、系统 Python、SSH、Git 和 ripgrep。Mosh 为可选项，未安装时启动器使用 SSH。

## 1. 私网与远程登录

安装 [Tailscale macOS 客户端](https://tailscale.com/docs/install/mac)，完成系统权限和登录，加入与 VPS 相同的 tailnet。关闭 DNS 接管、接受子网路由和出口节点。记录 Mac 的 Tailscale IPv4，保持设备在线和唤醒。

系统设置 → 通用 → 共享 → 远程登录，允许实际项目账号。无需另启 Tailscale SSH，本链路使用 macOS 的 OpenSSH。[Apple 远程登录说明](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)

登录账号必须对项目及外置盘有真实读写权限。系统隐私权限可能限制远程进程访问特定目录；不能由 Unix mode 或提示词推断已获得 macOS 授权。

在 Mac 上先确认 `/usr/bin/python3 --version` 能运行，且已安装 Git 和 ripgrep。启动器与回连守护使用系统 Python 的绝对路径。项目命令从非交互登录 Zsh 的环境进入 Bash；工具路径按这台 Mac 的实际安装位置配置，再用 [首次验收](operations.md#首次验收) 的回连命令核对。

## 2. 授权 VPS 公钥

把 VPS 普通 claude 用户生成的 **公钥**追加到本项目账号 `~/.ssh/authorized_keys`。保留现有密钥，一行示例：

```text
restrict,from="__VPS_TAILSCALE_IPV4__" ssh-ed25519 __VPS_TO_MAC_PUBLIC_KEY__ claude-vps-to-mac
```

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
cat /etc/ssh/ssh_host_ed25519_key.pub
```

最后一项是 Mac 的公开主机密钥，提供给 VPS 固定校验。不能用关闭 StrictHostKeyChecking 解决连接问题。

restrict 禁止转发和 PTY，但仍允许普通命令和 SFTP。来源地址限制只允许这一台 VPS，经它登录后继承 Mac 账号正常权限，**不是只读写所选项目的系统隔离**。

## 3. Mac 到 VPS 的管理入口

沿用现有已验证的管理入口。根据 `examples/mac-ssh.config` 合并 `~/.ssh/config`，填写固定公网主机名/IP、SSH端口及认证方式。

若使用服务商原密码，去掉模板的 `IdentityFile`，设置 `PubkeyAuthentication no` 和 `PreferredAuthentications password`；保留 `ControlMaster auto`、`ControlPersist` 和 `ControlPath`。交互运行 `claude` 时，OpenSSH会提示密码并建立复用连接，密码不写入启动器配置。非交互入口、`cvm install vps` 和 `cvm doctor`不主动询问密码，需要先通过同一别名、Tailscale地址和HostKeyAlias建立已认证连接。VPS自动回连Mac仍使用前文登记的专用公钥，与管理登录分开。

若使用管理密钥，沿用已有密钥；新环境才生成独立密钥并通过供应商控制台等可信路径安装公钥。

在可信 VPS 控制台核对 SSH 主机公钥，将其追加到 Mac 的 `~/.ssh/known_hosts`。以下以 Ed25519 为例，公钥类型和值按实机填写：

```text
__VPS_PUBLIC_HOSTNAME_OR_IP__ ssh-ed25519 __VERIFIED_VPS_PUBLIC_HOST_KEY__
```

第一列是 `HostKeyAlias`，须与启动器 JSON 中一致。此处的 root SSH 入口负责管理和分发，实际 CLI 经 `runuser` 以 `claude` 用户运行。

## 4. 准备启动器配置

首次配置时，在本仓库目录中执行。已有 `launcher.json` 时先核对并按键更新，不整份覆盖。

```bash
mkdir -p ~/.config/claude-mac ~/.local/bin
chmod 700 ~/.config/claude-mac
cp examples/launcher.json ~/.config/claude-mac/launcher.json
chmod 600 ~/.config/claude-mac/launcher.json
```

编辑 launcher.json 的三个字段：

| 字段 | 内容 |
| --- | --- |
| ssh_alias | 对应 ~/.ssh/config 的管理别名，默认 CLAUDE-VPS |
| tailscale_host | VPS 的 Tailscale IPv4，不是公网 IP |
| host_key_alias | 与已验证 VPS 主机密钥条目一致的主机名/IP |

在 Mac 终端用与 `cvm` 相同的连接参数验证。下列地址、主机密钥别名和 SSH 别名按实际配置替换：

```bash
ssh -o HostName=__VPS_TAILSCALE_IPV4__ -o HostKeyAlias=__VPS_PUBLIC_HOSTNAME_OR_IP__ CLAUDE-VPS true
ssh -o BatchMode=yes -o HostName=__VPS_TAILSCALE_IPV4__ -o HostKeyAlias=__VPS_PUBLIC_HOSTNAME_OR_IP__ CLAUDE-VPS id -u
```

第一条可交互认证；第二条应无需再次输入密码并输出 `0`，确认非交互连接使用 root。密码方式依赖 `ControlMaster` 复用；只登录过公网地址不能代替这项检查。`HostKeyAlias` 用于查找已固定的主机公钥，实际连接地址由 `HostName` 决定。

可用 `CLAUDE_MAC_CONFIG` 指向另一份私有 JSON。字段缺失或仍是占位符时，启动器先报错，不发起连接。

## 5. 安装本地启动器

按 [部署顺序](deploy.md) 安装 VPS 脚本后，用 cvm 安装启动器和 `claude-ssh`、`claude-mosh` 两个链接。替换的文件备份到 `~/.local/state/claude-vps-mac/backups/`：

```bash
scripts/cvm install mac --dry-run
scripts/cvm install mac
```

已有的 `~/.local/bin/claude` 显示为 unmanaged 时，先确认它是旧的远端启动器而不是原生 CLI，再加 `--adopt`。确保 `~/.local/bin` 在本机 PATH 中；需要时把 `export PATH="$HOME/.local/bin:$PATH"` 合并到现有 shell 配置，不整份覆盖。

在日常使用的终端分别运行 `type -a claude` 和 `type -a claude-ssh`。用于本项目的入口应优先解析到 `~/.local/bin/claude` 与 `~/.local/bin/claude-ssh`。`doctor` 的 PATH 检查只识别可执行文件；同名别名、函数以当前终端的 `type -a` 为准。

## 6. 可选 Mosh

原部署使用 Homebrew Mosh 1.4.0，启动器从 PATH 查找 mosh。按 [Mosh 安装说明](https://mosh.org/#getting) 安装本机客户端；遵循自己的运行环境管理约定，不额外安装业务 Node/Python 或容器。

交互终端默认用 Mosh；`claude-ssh` 强制 SSH。非终端、help/version/print 和子命令走 SSH。Mosh 端口占满时回退 SSH；UDP 建立阶段失败时需手动选择 claude-ssh，不自动启动第二个会话。

## 7. 首次使用

进入具体项目目录运行 `claude --version`、`claude`，执行 [真实验收](operations.md)。不要从家目录或整盘根目录启动；启动器会拒绝这些路径。

项目依赖和测试使用 Mac 上已有的项目环境。验收时用实际项目命令确认远程登录环境能找到它们。
