# 配置 Mac

本机需要 Tailscale、远程登录、系统 Python 和 SSH。Mosh 是终端体验选项，没有安装时启动器使用 SSH。以下手动安装步骤面向新使用者，不用于覆盖已经在线的部署。

## 1. 私网与远程登录

安装 [Tailscale macOS 客户端](https://tailscale.com/docs/install/mac)，完成系统权限和登录，加入与 VPS 相同的 tailnet。关闭 DNS 接管、接受子网路由和出口节点。记录 Mac 的 Tailscale IPv4，保持设备在线和唤醒。

系统设置 → 通用 → 共享 → 远程登录，允许实际项目账号。无需另启 Tailscale SSH，本链路使用 macOS 的 OpenSSH。[Apple 远程登录说明](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)

登录账号必须对项目及外置盘有真实读写权限。系统隐私权限可能限制远程进程访问特定目录；不能由 Unix mode 或提示词推断已获得 macOS 授权。

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

沿用现有已验证的管理密钥；新环境才生成独立管理密钥并通过供应商控制台等可信路径把公钥装到 VPS。根据 `examples/mac-ssh.config` 合并 `~/.ssh/config`，填写固定公网主机名/IP 与密钥文件。

在可信 VPS 控制台核对 SSH 主机公钥，将其加入 Mac known_hosts；HostKeyAlias 必须与启动器 JSON 中一致。此处默认 root 管理入口只用于分发，实际 CLI 经 runuser 以 claude 用户运行。

## 4. 安装配置与启动器

在本仓库目录中执行；若 `~/.local/bin/claude` 已存在，先核对它是原生 CLI 还是已有远端启动器，保留备份，避免直接覆盖。

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

确认配置后，用 cvm 安装启动器和 claude-ssh、claude-mosh 两个链接，已有文件先备份到 `~/.local/state/claude-vps-mac/backups/`：

```bash
scripts/cvm install mac --dry-run
scripts/cvm install mac
```

已有的 `~/.local/bin/claude` 显示为 unmanaged 时，先确认它是旧的远端启动器而不是原生 CLI，再加 `--adopt`。确保 `~/.local/bin` 在本机 PATH 中；需要时把 `export PATH="$HOME/.local/bin:$PATH"` 合并到现有 shell 配置，不整份覆盖。

可用 `CLAUDE_MAC_CONFIG` 指向另一份私有 JSON。字段缺失或仍是占位符时，启动器先报错，不发起连接。

## 5. 可选 Mosh

原部署使用 Homebrew Mosh 1.4.0，启动器从 PATH 查找 mosh。按 [Mosh 安装说明](https://mosh.org/#getting) 安装本机客户端；遵循自己的运行环境管理约定，不额外安装业务 Node/Python 或容器。

交互终端默认用 Mosh；`claude-ssh` 强制 SSH。非终端、help/version/print 和子命令走 SSH。Mosh 端口占满时回退 SSH；UDP 建立阶段失败时需手动选择 claude-ssh，不自动启动第二个会话。

## 6. 首次使用

进入具体项目目录运行 `claude --version`、`claude`，执行 [真实验收](operations.md)。不要从家目录或整盘根目录启动；启动器会拒绝这些路径。

项目依赖和测试使用 Mac 上已有的项目环境。原部署通过 EnvKit 管理，若你使用别的管理器，以项目规范和实际版本为准，远端登录 PATH 不能替代这项核验。
