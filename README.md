<h1 align="center">claude-vps-mac</h1>

<p align="center">Claude Code 在 VPS 运行并使用其网络出口，源码、依赖和测试留在 Mac。</p>

## 能解决什么

这是一次个人部署的经验项目：整理实际采用的脚本、配置模板、部署步骤和性能取舍。适合希望保留官方 Claude Code 订阅登录、在 Mac 终端直接对话，又将 CLI 放在自有 VPS 上的用户。

| 使用体验 | 实现方式 |
| --- | --- |
| 项目目录输入 `claude` 即可聊天 | Mac 启动器自动传入当前目录 |
| 保留官方 CLI 和订阅登录 | VPS 普通用户运行原生 Claude Code，不自建模型代理 |
| 直接修改 Mac 文件 | Read/Edit/Write 操作 SSHFS 实时挂载 |
| 使用 Mac 的依赖与测试环境 | Bash hook 自动经 SSH 路由到 Mac |
| 新会话不等 git 扫描挂载 | CLI 自身的 git 调用经 PATH 包装在 Mac 执行 |
| 全项目搜索在 Mac 本地执行 | Glob/Grep 使用 PATH 上的 rg 包装，结果路径映射回挂载 |
| 改善跨境终端输入体验 | 默认 Mosh 对话，保留 SSH 入口 |

## 架构

```text
┌──────────────┐  Mosh / SSH  ┌─────────────────────┐
│ Mac terminal │────────────▶│ VPS: native Claude  │────▶ Anthropic
└──────────────┘             └─────────────────────┘       VPS egress
                                     │
                            Tailscale + SSH / SFTP
                                     │
                                     ▼
                            ┌─────────────────────┐
                            │ Mac project + tests │
                            └─────────────────────┘
```

Mosh 承载终端画面和按键；Bash 和文件读写仍走 SSH。项目没有云端同步副本；会话记录和已读代码片段仍会保存在 VPS，必要上下文也会发送给模型。

## 部署

按 [VPS 配置](docs/setup-vps.md) 和 [Mac 配置](docs/setup-mac.md) 完成两端设置。之后在 Mac 的仓库目录用 `scripts/cvm install vps|mac` 从仓库安装或更新脚本，用 `scripts/cvm doctor` 体检；CLI 更新后也运行一次 doctor。模板中的 `__...__` 必须替换成自己的配置；不要把填写后的文件提交到仓库。

原部署验证环境为 Debian 12、2 vCPU、2 GiB RAM、2 GiB swap，macOS 15.8；Claude Code 2.1.296、Tailscale 1.104.1、Mosh 1.4.0、SSHFS 3.7.3。**2 GiB 是轻负载实测，不是推荐容量**；新建 VPS 应优先考虑 4 GiB，官方安装指南列出的内存要求也是 4 GB+。[官方安装指南](https://code.claude.com/docs/en/setup)

## 快速开始

两端部署并验证连接后，在 Mac 的具体项目目录中：

```bash
claude --version
claude
```

进入对话后让 Claude 执行 `uname -s; pwd`，应返回 `Darwin` 和 Mac 项目路径。继续同一项目的最近对话用 `claude -c`；强制普通 SSH 用 `claude-ssh`；正常退出用 `/exit`。

## 文档

| 主题 | 内容 |
| --- | --- |
| [链路与边界](docs/architecture.md) | 三条通道、工具路由、账号权限与状态存储 |
| [配置 VPS](docs/setup-vps.md) | 普通用户、CLI 登录、SSHFS、hook 与防火墙 |
| [配置 Mac](docs/setup-mac.md) | Tailscale、远程登录、固定主机密钥与启动器 |
| [使用、验收与回退](docs/operations.md) | 真实读写测试、断连核对、诊断与定点撤回 |
| [部署经验与测量](docs/deployment-experience.md) | 原部署的瓶颈、改进、代价及待验收项 |
| [验证记录](docs/validation.md) | 原链路实测与仓库便携版本验证的区别 |

## 开发与测试

测试只用 Python 标准库，不联网、不调用模型：

```bash
python3 -m unittest discover -s tests
```

Mac 端进程守护依赖 macOS kqueue，相关用例只在 macOS 上运行；CI 在 Ubuntu 与 macOS（系统 Python）各跑一遍。单元测试不能替代真实部署后的[验收](docs/operations.md)。变更见 [CHANGELOG](CHANGELOG.md)。

## 项目范围

这个仓库不包含服务器凭据、订阅令牌、Reality 节点、第三方技能副本、终端工具 运行时或业务项目。现有代理节点无需改动。它也不提供注册、住宅 IP 稳定性或模型风控结果保证。

模板沿用原部署的 `bypassPermissions` 和 `xhigh`，并非所有用户的推荐值。权限与用量策略见 [VPS 配置](docs/setup-vps.md)。多会话编辑同一文件仍可能冲突；SSHFS 原生文件操作仍有跨境延迟。
