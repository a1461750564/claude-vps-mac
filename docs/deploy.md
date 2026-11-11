# 从准备到首次验收

完成后，在 Mac 项目目录输入 `claude`，对话和模型请求由 VPS 上的官方 Claude Code 处理。文件、依赖、构建与测试仍使用 Mac 上原有的项目目录。

## 部署前确认

| 对象 | 准备与检查 |
| --- | --- |
| Mac | 能运行 Tailscale、`/usr/bin/python3`、Git 和 ripgrep；知道实际登录用户名和项目绝对路径。项目账号通过远程登录时也需要读写项目所在目录。 |
| VPS | Debian 12、可用的 root SSH 入口、Tailscale 所需的 TUN，以及普通用户可用的 FUSE。只有普通账号加 `sudo` 时，当前 `cvm` 和终端分发器不能直接使用该入口。 |
| 连接与登录 | 两台机器加入同一 tailnet，准备双向 SSH 授权和已核对的主机公钥。Claude 由使用者在 VPS 上登录自己的账号。先准备 SSH，Mosh 可选。 |

每套部署配对一台 Mac 和一台 VPS。用户名、SSH 端口、项目路径和工具安装位置按各自环境填写。

## 安装与验收

在 Mac 上克隆本仓库：

```bash
git clone https://github.com/a1461750564/claude-vps-mac.git
cd claude-vps-mac
```

下文的 `scripts/cvm` 命令都在这个仓库目录运行。配置模板中的 `__...__` 换成自己的值；填写后的配置、SSH 私钥和登录凭据留在各自的机器上。

1. **准备两端和官方 CLI。** 按 [VPS 准备](setup-vps.md#1-系统与网络前提) 补齐依赖、加入 Tailscale，按 [CLI 安装与登录](setup-vps.md#2-普通账号与官方订阅登录) 在 VPS 的普通用户 `claude` 下安装并完成自己的订阅授权。按 [Mac 准备](setup-mac.md#1-私网与远程登录) 开启远程登录，确认项目账号可以读写目标目录。按 [连接要求](setup-vps.md#6-本项目所需的端口) 接通双向 SSH；Mosh 可稍后配置。
2. **准备 Mac 到 VPS 的入口。** 按 [管理 SSH](setup-mac.md#3-mac-到-vps-的管理入口) 配置 SSH 别名与已核对的主机密钥，再填写 [启动器配置](setup-mac.md#4-准备启动器配置)。用相同 Tailscale 地址和主机密钥别名验证非交互 SSH。使用原密码时，先建立可复用的已认证连接。
3. **安装两端脚本。** 逐条执行下列命令。dry run 如果显示 `modified` 或 `unmanaged`，先核对归属，确认接管后才使用 `--adopt`。Mac 已有原生 `claude` 时，先保留原入口。

   ```bash
   scripts/cvm install vps --dry-run
   scripts/cvm install vps
   scripts/cvm install mac --dry-run
   scripts/cvm install mac
   ```

4. **验证 VPS 到 Mac 的回连。** 按 [回连配置](setup-vps.md#4-vps-到-mac-的-ssh) 建立专用密钥、固定 Mac 主机密钥并填写 `mac-connection.json`。在 VPS 以 `claude` 用户运行 `mac-project check`，应返回 `Darwin` 和预期的 Mac 用户。管理 VPS 的认证与这个回连密钥相互独立。
5. **合并 CLI 配置。** 按 [CLI 设置](setup-vps.md#5-cli-设置与全局规则) 注册 Bash 路由 Hook。可按需合并 `examples/claude-preferences.json` 的模型、压缩窗口、缓存和隐私偏好，也可 [启用中文状态栏](setup-vps.md#7-可选中文状态栏)。已有的用户配置按键保留。
6. **在临时项目完成验收。** 按 [首次验收](operations.md#首次验收) 核对实际终端入口、Mac 回连读写和 `cvm doctor`。先用 `claude-ssh` 验证挂载和真实工具调用；配置 Mosh 后，再用 `claude` 验证交互。

`cvm` 管理桥接脚本、启动器、链接和安装记录。官方 CLI 的安装与登录、SSH 授权、连接放行和用户设置由上面的步骤完成。已有部署先核对现状，保留原文件；替换时按安装清单与备份逐项回退。
