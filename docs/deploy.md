# 从准备到首次验收

完成后，在 Mac 项目目录输入 `claude`，对话和模型请求由 VPS 上的官方 Claude Code 处理。文件、依赖、构建与测试仍使用 Mac 上原有的项目目录。

## 部署前确认

| 对象 | 准备与检查 |
| --- | --- |
| Mac | 能运行 Tailscale、`/usr/bin/python3`、Git 和 ripgrep；知道实际登录用户名和项目绝对路径。项目账号通过远程登录时也需要读写项目所在目录。 |
| VPS | Debian 12，x86_64/ARM64、至少 4 GB 内存，磁盘给 CLI、日志和备份留余量；可用的 root SSH 入口、Tailscale 所需的 TUN，以及普通用户可用的 FUSE。只有普通账号加 `sudo` 时，当前入口不能直接使用。[资源检查](setup-vps.md#1-系统与网络前提) |
| Claude 出口 | **CLI 安装前的必做项：** 核实实际出口 IP 及地区，配置匹配的服务器时区和语言（UTF-8），确认时钟同步，再固定 CLI 会话环境。未核实就不继续安装或登录。[配置步骤](setup-vps.md#配置-claude-出口的时区与语言) |
| 连接与登录 | 两台机器加入同一 tailnet，准备双向 SSH 授权和已核对的主机公钥。Claude 由使用者在 VPS 上登录自己的账号。先准备 SSH，Mosh 可选。 |

每套部署配对一台 Mac 和一台 VPS。用户名、SSH 端口、项目路径和工具安装位置按各自环境填写。

## 安装与验收

在 Mac 上克隆本仓库：

```bash
git clone https://github.com/a1461750564/claude-vps-mac.git
cd claude-vps-mac
```

下文的 `scripts/cvm` 命令都在这个仓库目录运行。配置模板中的 `__...__` 换成自己的值；填写后的配置、SSH 私钥和登录凭据留在各自的机器上。

1. **先准备 VPS 环境，再安装官方 CLI。** 补齐依赖并加入 Tailscale，核实实际公网出口 IP 及地区，配置匹配的系统时区、语言和时钟同步。切换到普通用户 `claude`，核对安装 shell 的环境，并在用户 settings 中固定同一组时区和语言；通过后才安装并登录官方 CLI。Mac 开启远程登录，确认非交互环境能找到工具、能读写项目。Mosh 可稍后配置。[VPS 准备](setup-vps.md#1-系统与网络前提) · [CLI 准备与安装](setup-vps.md#2-普通账号与官方订阅登录) · [Mac 准备](setup-mac.md#1-私网与远程登录) · [连接要求](setup-vps.md#6-本项目所需的端口)
2. **准备 Mac 到 VPS 的入口。** 按 [管理 SSH](setup-mac.md#3-mac-到-vps-的管理入口) 配置 SSH 别名与已核对的主机密钥，再填写 [启动器配置](setup-mac.md#4-准备启动器配置)。用相同 Tailscale 地址和主机密钥别名验证非交互 SSH。使用原密码时，先建立可复用的已认证连接。
3. **安装两端脚本。** 逐条执行下列命令，保存 dry run 输出和已有安装清单，以便分清新增与替换文件。出现 `modified` 或 `unmanaged`，先核对归属，确认接管后才使用 `--adopt`。Mac 已有原生 `claude` 时，先完成 [入口共存](setup-mac.md#与本机原生-cli-共存)。

   ```bash
   scripts/cvm install vps --dry-run
   scripts/cvm install vps
   scripts/cvm install mac --dry-run
   scripts/cvm install mac
   ```

4. **验证 VPS 到 Mac 的回连。** 按 [回连配置](setup-vps.md#4-vps-到-mac-的-ssh) 建立专用密钥、固定 Mac 主机密钥，创建登记目录后填写并校验 `mac-connection.json`。在 VPS 以 `claude` 用户运行 `mac-project check`，应返回 `Darwin` 和预期的 Mac 用户。管理 VPS 的认证与这个回连密钥相互独立。
5. **合并 CLI 配置。** 按 [CLI 设置](setup-vps.md#5-cli-设置与全局规则) 注册 Bash 路由 Hook。保留第 1 步固定的时区和语言；可按需合并 `examples/claude-preferences.json` 的模型、压缩窗口、缓存和隐私偏好，也可 [启用中文状态栏](setup-vps.md#7-可选中文状态栏)。已有的用户配置按键保留。
6. **在临时项目完成验收。** 按 [首次验收](operations.md#首次验收) 核对实际终端入口、Mac 回连读写和 `cvm doctor`。先用 `claude-ssh` 验证挂载、实际运行环境和真实工具调用；配置 Mosh 后，再用 `claude` 复验。`doctor` 不检查出口地理位置、时区或语言，不能代替这些人工验收。

`cvm` 管理桥接脚本、启动器、链接和安装记录。官方 CLI 的安装与登录、SSH 授权、连接放行和用户设置由上面的步骤完成。已有部署先核对现状，保留原文件；替换时按安装清单与备份逐项回退。

## 后续维护

升级时保存当前版本、安装清单和配置，核对 dry run，退出相关会话后更新两端，再执行环境与工具验收。故障时按实际变更定点回退；首次新增的文件没有旧备份，需结合部署前记录辨认。完整撤除时还应解除挂载、撤销专用密钥授权并恢复原生入口。[升级部署](operations.md#升级部署) · [定点回退](operations.md#定点回退) · [完整撤除桥接部署](operations.md#完整撤除桥接部署)
