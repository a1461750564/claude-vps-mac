# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布] — 0.2.0

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
