# selfu

一个使用 [typer](https://typer.tiangolo.com/)、[rich](https://rich.readthedocs.io/)
和 [textual](https://textual.textualize.io/) 构建的运维自检工具包。

`selfu` 通过**原生系统命令**（`df`、`free`、`resolvectl`、`nmcli`、`firewall-cmd`、
`systemctl`、`hostnamectl` ……）来检查主机，而不是引入额外的 Python 依赖，因此只要
这些工具存在，它就能在任何地方运行。

简体中文 | [English](README.md)

## 安装

```bash
uv pip install -e .     # 或：pip install -e .
```

这会注册 `selfu` 命令行脚本（同时保留 `python main.py` 可用）。

## 使用

```text
selfu                          # 顶层帮助
selfu network                  # 一次性执行所有网络检查
selfu network dns              # DNS 服务器（resolvectl / /etc/resolv.conf）
selfu network resolve [域名]   # 实际解析某个域名（getent/resolvectl）
selfu network connectivity     # ping 某台主机（默认：1.1.1.1）
selfu network connectivity -H example.com
selfu network wifi             # Wi-Fi 状态 + 扫描（nmcli）
selfu network firewall         # firewalld / nftables / iptables
selfu network ports            # 监听端口 + 连接汇总（ss）
selfu cpu                      # 负载均值 + 占用最高的 CPU/内存进程
selfu disk                     # 带使用率进度条的 df -h
selfu disk -i                  # 同时显示 inode 使用率（df -i）
selfu disk --raw               # 原始 df 输出
selfu memory                   # 带使用率进度条的 free
selfu health                   # 启动错误 + OOM + 启动时间 + NTP + 熵
selfu security                 # 登录失败 + 会话 + MAC + SSH 配置
selfu updates                  # 按发行版检测：待办/安全更新 + 是否需重启
selfu system                   # shell rc + systemd + 主机
selfu system shell             # rc/profile 文件清单
selfu system systemd           # 失败 / 已启用的单元
selfu system host              # hostnamectl 身份信息
selfu all                      # 汇总的纯文本报告
selfu dashboard                # 交互式 Textual TUI
selfu completions bash         # 打印 shell 补全脚本
selfu completions fish --install   # 永久安装补全
```

#### Shell 补全

`selfu` 内置了 bash、zsh、fish 和 PowerShell 的补全。既可以由 typer 自动接入
（`selfu --install-completion`），也可以使用专用命令：

```bash
eval "$(selfu completions bash)"        # 仅当前会话生效
selfu completions zsh --install         # 写入 ~/.zfunc/_selfu
selfu completions fish --install        # 写入 ~/.config/fish/completions/
```

`selfu updates` 会从 `/etc/os-release` 识别发行版家族，然后分发到对应的后端：
`dnf`/`yum`（RHEL 家族）、`apt`（Debian 家族）、`checkupdates`（Arch 家族）、
`zypper`（SUSE 家族）。重启检测使用 `/var/run/reboot-required`（Debian）、
`needs-restarting -r`（RHEL），或最后退回到运行内核与已安装内核的比较。

### Textual 面板

`selfu dashboard` 打开一个带标签页的界面（网络 / 磁盘 / 内存 / 系统）：

| 按键      | 动作                 |
|-----------|----------------------|
| `r`       | 刷新当前标签页       |
| `Ctrl+R`  | 刷新全部             |
| `q`       | 退出                 |

## 项目结构

```
src/selfu/
├── cli.py            # typer 命令树
├── completions.py    # shell 补全生成与安装
├── runner.py         # 原生命令的 subprocess 封装
├── ui.py             # 每项检查的 rich 面板/表格
├── tui.py            # textual 面板
└── checks/
    ├── network.py    # dns / resolve / connectivity / wifi / firewall / ports
    ├── cpu.py        # 负载均值 + 占用最高的进程
    ├── disk.py       # df（+ inode 使用率）
    ├── memory.py     # free
    ├── health.py     # journal 错误 / OOM / 启动时间 / NTP / 熵
    ├── security.py   # 登录失败 / 会话 / MAC / SSH 配置
    ├── system.py     # shell rc/profile / systemd（+不可变路径解析）/ hostnamectl
    └── updates.py    # 按发行版检测待办/安全更新 + 是否需重启
```

#### 不可变系统感知

`selfu system systemd` 能识别 ostree/镜像式主机，并为每个失败单元解析其
`FragmentPath`。位于只读 `/usr/lib/systemd/system/` 树中、随系统分发的单元会被
标记为不可编辑，并给出 `systemctl edit <unit>` 的 drop-in 提示；而
`/etc/systemd/system/` 中的单元则显示为可直接编辑。

每项检查都返回一个类型化的 dataclass，因此渲染层（`ui.py`、`tui.py`）与数据采集层
保持清晰的分离。

## 许可证

本项目基于 MIT 许可证发布，详见 [LICENSE](LICENSE) 文件。
