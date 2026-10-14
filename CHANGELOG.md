# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 变更

- 状态目录默认名称统一为 `~/claude-vps-mac`，解析符号链接后保留实际挂载与会话路径；已有部署需先建立指向原目录的链接再更新脚本。
- 测试使用通用账号和磁盘目录名，文档去除无关终端品牌叙述。

## [0.3.0] — 2026-10-13

### 新增

- `scripts/vps/mac-git.py`（安装为 `~/.local/libexec/claude-mac/git`）：Mac 项目会话中，CLI 自身的 git 调用（会话上下文的 status/log、diff、worktree 等）在 Mac 执行，不再经 SSHFS 逐个文件读取。挂载外的目录、参数或环境变量中的 VPS 路径、`--version`/`help` 仍用 VPS git；`rev-parse`、`worktree` 输出里的 Mac 路径映射回挂载路径；Mac 端设置 `GIT_CEILING_DIRECTORIES`，仓库查找止于项目目录，与挂载上的结果一致。
- `scripts/vps/mac-rg.py`（安装为同一目录的 `rg`）：Mac 项目会话的 Glob/Grep 使用 PATH rg，在 Mac 搜索并映射结果路径，保留命中文本、NUL 文件名、JSON 数据和退出码；VPS 目录及主机专用调用仍用 VPS rg。
- `scripts/cvm`，在 Mac 仓库目录运行。`install vps|mac` 从仓库安装两端文件（VPS 经启动器的管理入口以 root 写入）：支持 `--dry-run`，替换前备份，记录所装提交；不是 cvm 装的或装后被改过的文件需 `--adopt` 才替换；源文件有未提交修改时拒绝安装。`doctor` 核对两端文件与仓库一致、CLI 版本变化、VPS → Mac、hook 路由与注册、git 包装、服务、Mosh 端口与内存，并经真实入口运行 `claude --version`。
- 42 项新增测试：git/rg 路由、参数及路径映射、保留命中文本与 JSON 偏移、真实命令输出和退出码、连接失败不重放、会话环境与脚本可执行位；cvm 的状态判定、连续更新保留备份、`--adopt`、远端运行和 doctor 判定。

### 变更

- claude-mac 只在 Mac 项目会话把 `~/.local/libexec/claude-mac` 放到 PATH 最前；非项目会话移除该目录和项目变量。

### 测量

- 30 个文件的本仓库：VPS git 经挂载执行 `status` 37–42 s、`log -n 5` 13 s。CLI 要等 git status 返回才发出第一个 API 请求，启动后 42.4 s 才发出；路由后每次 git 约 0.5 s，第一个请求在 5.6–7.2 s 发出。方法见[部署经验](docs/deployment-experience.md#cli-内部的-git)。
- 同一仓库的 rg 搜索（每组 3 次中位数）：列出文件经 SSHFS 73.9 s、经 Mac 0.80 s；内容搜索 13.7 s、0.75 s，结果排序后 SHA256 与退出码一致。见[验证记录](docs/validation.md#搜索路由测量)。

## [0.2.0] — 2026-10-13

### 新增

- `tests/`：51 项标准库单元测试，不联网、不调用模型。覆盖 Bash hook 路由与失败拒绝、mac-run 路径映射、启动器通道选择与配置校验、过宽目录与挂载参数、SSH/Mosh 参数经两层 shell 的引用往返、仓库密钥扫描；Mac 端进程守护的退出码、stdin、遗留进程、断开通道、TERM 清理和临时/持续权限错误在 macOS 上实际运行。
- GitHub Actions CI：Ubuntu 与 macOS（系统 `/usr/bin/python3`）各运行一遍测试。

### 变更

- mac-run 在 Mac 端导出 `MAC_PROJECT_DIR`、`MAC_PROJECT_MOUNT`（均为 Mac 项目路径），与原部署 2026-10-13 的线上版本一致。
- 抽出 `wants_mosh`、`mosh_ports_full`、`plan`、`cache_outdated` 等纯函数以便测试，行为不变。

### 修复

- macOS 进程组清理遇到僵尸进程导致的短暂 `EPERM` 时，在原有清理时限内回收并重试，避免断连退出码偶发变成 `1`；持续权限错误仍报告失败。

## [0.1.0] — 2026-10-13

- 首次整理：链路文档、配置模板与原部署脚本的便携版本。
