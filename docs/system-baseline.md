# 系统基线与共存

本项目只分发终端和工具路由脚本，不自动配置代理节点、清空防火墙、修改 DNS 或重启系统。

| 项目 | 原部署经验 | 操作边界 |
| --- | --- | --- |
| SSH | 管理密钥登录、fail2ban | 关闭密码前独立测试密钥；保留正在使用的会话 |
| 防火墙 | nftables 默认入站 drop、出站保留 | 增量合并；同时核对其他防火墙和 tailnet ACL |
| 更新 | 自动安全更新、无自动重启 | 保留实际服务与维护窗口 |
| BBR+fq | 支持该算法的 Debian 内核 | 核对接口与实际拥塞控制；不承诺解决应用或 SSHFS 延迟 |
| Swap | 2 GiB RAM + 2 GiB swap | 只是内存缓冲，不替代物理 RAM；已有 swap 不重建 |
| 权限 | CLI 普通 claude 用户，无 sudo | root 入口只分发，Mac 权限另核对 |
| 出站 | VPS 原有住宅网络 | Tailscale 不接管 DNS、默认路由或出口节点 |

只读检查示例：

```bash
uname -a
free -m
swapon --show
df -h
sysctl net.ipv4.tcp_congestion_control net.core.default_qdisc
ss -ti
ip route show default
nft list ruleset
systemctl is-active ssh tailscaled
```

原部署同机有 sing-box Reality 节点；它与 CLI 共用 CPU、内存和网络。记录部署前后的配置指纹、服务 MainPID 和资源负载，仅在明确有问题时处理该服务。本项目不包含或更改节点的 UUID、私钥、SNI、DNS 或监听配置。

新增 swap、防火墙或系统设置均属于实际服务器部署动作，需按目标环境制定恢复边界；本仓库的人工文档不是对任何机器批量改动的授权。
