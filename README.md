# VibeSignal

VibeSignal 是一个给 AI 编码工具用的桌面状态面板和 USB 状态灯控制器。它把 Claude Code、Codex 等本机会话的状态收集到同一个本地状态库里：工具正在工作时显示 working，需要你处理权限或输入时显示 blocked，完成一轮后显示 done。

源码仓库：<https://github.com/gt11799/vibesignal>

本仓库基于上游 `yzhao062/vibesignal` 做了本地化定制，重点是把桌面面板做得更适合长期常驻使用，并增加 Codex / Claude Code 剩余额度信息的展示。

## 主要特性

- 桌面浮窗：始终置顶、可拖拽、右键退出，读取同一份会话状态。
- 页面美化：高对比深色主题、右上角停靠、清晰白字、blocked/error 高亮报警态。
- Claude Code 支持：通过 hooks 自动上报 working、blocked、done 和 SessionEnd。
- Codex 进程支持：通过 Codex hooks 把本地 Codex 会话纳入同一个状态面板。
- 剩余额度展示：面板底部可显示 Codex 或 Claude Code 的 5 小时窗口和 7 天窗口剩余比例与重置倒计时。
- Cowork 桥接：可把 Claude.app Cowork 本地 VM 的活动近似显示为 `cowork/local-vm`。
- 多会话聚合：多个 agent 同时跑时按 `blocked > error > done > working > idle` 聚合。
- 多种展示方式：USB busylight、终端 watch 面板、Tk 桌面 widget。

## 安装

推荐在 macOS 上使用 `uv` 托管 Python 安装。Homebrew Python 常见问题是缺少可用的 Tkinter，而 `uv --python-preference only-managed` 会使用自带 Tk 的 CPython。

```bash
uv tool install --force --python-preference only-managed --python 3.13 \
  'vibesignal[macos] @ git+https://github.com/gt11799/vibesignal.git'
```

安装后确认命令可用：

```bash
vibesignal status
```

如果使用的是 Windows 或 Linux，可以用普通 pip 安装，但桌面 widget 仍需要系统里有可用的 Tk：

```bash
pip install 'vibesignal @ git+https://github.com/gt11799/vibesignal.git'
```

## macOS 初始化

安装后建议执行这些步骤，让面板可以像普通应用一样启动并开机自启：

```bash
cp scripts/vibesignal-restyle ~/.local/bin/
chmod +x ~/.local/bin/vibesignal-restyle
~/.local/bin/vibesignal-restyle

vibesignal install-launcher
vibesignal install-autostart
```

`vibesignal-restyle` 会修复 uv tool venv 里 Tcl/Tk 路径找不到的问题。每次 `uv tool install --force` 或升级后，都建议重新跑一次。
如果只改了 hooks，不需要重启 widget；如果改了 `widget.py` 样式或图标资产，需要重启 `vibesignal widget` 才能看到新效果。
`vibesignal install-launcher` 会自动把内置图标复制到启动器和 `~/.local/share/vibesignal/`，不需要再手动覆盖 `.app` 图标。

状态栏 provider 可以在安装时选择：

```bash
vibesignal install-launcher --usage-provider codex
vibesignal install-autostart --usage-provider codex

vibesignal install-launcher --usage-provider claude
vibesignal install-autostart --usage-provider claude
```

`auto` 会优先显示 Codex，取不到时尝试 Claude Code；`off` 会关闭底部剩余额度状态栏。

## 常用命令

```bash
vibesignal widget          # 启动桌面浮窗
vibesignal watch           # 在终端查看实时会话表
vibesignal status          # 查看当前聚合状态
vibesignal clear           # 清空所有会话状态
vibesignal off             # 清空状态并关闭 USB 灯
```

也可以手动写入一条状态，用于测试：

```bash
echo '{"session_id":"demo","cwd":"'$PWD'"}' \
  | vibesignal event --agent claude --state working
```

## 配置 Claude Code

把 `hooks/claude-settings.snippet.json` 合并到 `~/.claude/settings.json` 的 `hooks` 字段里。建议把 snippet 里的 `vibesignal` 命令改成绝对路径，例如：

```bash
~/.local/bin/vibesignal
```

Claude Code hooks 覆盖这些事件：

- `UserPromptSubmit`：标记为 working。
- `PostToolUse`：工具调用后回到 working。
- `Notification permission_prompt`：标记为 blocked。
- `Notification idle_prompt`、`Stop`、`StopFailure`：标记为 done。
- `SessionEnd`：立即清除结束的会话。

验证：

```bash
echo '{"session_id":"claude-test"}' \
  | ~/.local/bin/vibesignal event --agent claude --state working --quiet
~/.local/bin/vibesignal status
echo '{"session_id":"claude-test"}' \
  | ~/.local/bin/vibesignal end --agent claude --quiet
```

## Codex 支持 AI 操作手册

目标：让 AI agent 在本机 Codex 运行时，通过 Codex command hooks 自动把当前会话写入 VibeSignal 状态库。完成后，Codex 正在执行任务时面板应出现 `codex/<session>` 行，并显示 `working`、`blocked` 或 `done`。

### 1. 前置检查

```bash
command -v ~/.local/bin/vibesignal
~/.local/bin/vibesignal status
test -f hooks/codex-hooks.snippet.json
```

如果 `~/.local/bin/vibesignal` 不存在，先按上面的安装步骤安装。本仓库建议 hook 命令始终使用绝对路径，因为 Codex hook 环境不一定包含 `~/.local/bin`。

### 2. 合并 hooks

把 `hooks/codex-hooks.snippet.json` 合并到 `~/.codex/hooks.json`，不要覆盖用户已有 hooks。合并后把 snippet 中的 `vibesignal` 命令替换成 `~/.local/bin/vibesignal` 的绝对路径。

可由 AI agent 直接执行的安全合并示例：

```bash
python3 - <<'PY'
import json
from pathlib import Path

home = Path.home()
target = home / ".codex" / "hooks.json"
snippet = Path("hooks/codex-hooks.snippet.json")
target.parent.mkdir(parents=True, exist_ok=True)

base = json.loads(target.read_text()) if target.exists() else {}
patch = json.loads(snippet.read_text())
base.setdefault("hooks", {})

for event, entries in patch["hooks"].items():
    fixed_entries = json.loads(json.dumps(entries).replace(
        "vibesignal event",
        str(home / ".local/bin/vibesignal") + " event",
    ))
    base["hooks"].setdefault(event, [])
    for entry in fixed_entries:
        if entry not in base["hooks"][event]:
            base["hooks"][event].append(entry)

target.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n")
print(target)
PY
```

Codex hooks 覆盖这些事件：

- `UserPromptSubmit`：标记为 working。
- `PermissionRequest`：标记为 blocked。
- `Stop`：标记为 done。

不要把 Codex 的 `PostToolUse` 映射成 `working`：在 Codex app 里它可能刷新并没有真正运行的旧会话，导致面板误报 working。

### 3. 信任 hooks

Codex command hooks 需要用户信任后才会执行。合并 `~/.codex/hooks.json` 后：

1. 重启 Codex 客户端或新开一个 Codex 会话。
2. 在 Codex 会话里执行 `/hooks`。
3. 确认 `~/.codex/hooks.json` 下的 4 条 VibeSignal command hooks 已列出。
4. 信任这些 hooks。

未信任时，Codex 会跳过 command hooks，VibeSignal 面板不会显示正在执行的 Codex 任务。

### 4. 验证

先做 pipe-test，确认 VibeSignal 命令本身可以写状态：

```bash
echo '{"session_id":"codex-pipetest","cwd":"'$PWD'"}' \
  | ~/.local/bin/vibesignal event --agent codex --state working --quiet
~/.local/bin/vibesignal status
echo '{"session_id":"codex-pipetest"}' \
  | ~/.local/bin/vibesignal end --agent codex --quiet
```

再做真实验证：信任 hooks 后，在 Codex 里发一条会触发工具调用的消息，然后运行：

```bash
~/.local/bin/vibesignal status
```

期望看到类似：

```text
aggregate: working
  codex/<session-id>: working project=<repo-name>
```

如果只改了 hooks，不需要重启 `vibesignal widget`，面板会读取同一份状态库并自动刷新。

### 5. 排障

- `vibesignal status` 看不到 `codex/...`：优先确认 `/hooks` 里已经信任 VibeSignal hooks。
- pipe-test 可用但真实 Codex 不触发：重启 Codex 或新开会话，再执行 `/hooks` 检查信任状态。
- hook 报找不到命令：把 `~/.codex/hooks.json` 里的命令改成 `$HOME/.local/bin/vibesignal` 的绝对路径。
- 状态显示 `done`、旧的 `working` 或旧的 `blocked` 后没有立即消失：Codex 没有 SessionEnd 事件，会话行靠 TTL 过期。`done` 和 Codex `working` 会在约 90 秒后淡出；Codex `blocked` 会在约 10 分钟后淡出。

## 剩余额度状态栏

桌面面板底部会尝试显示：

```text
5h余 57% 重置4h40m · 7d余 64% 重置5d16h
```

可选 provider：

- `codex`：读取 `~/.codex/auth.json` 里的 Codex ChatGPT 登录态 access token，优先请求 Codex usage 接口；接口不可用时，读取本机 `~/.codex/sessions/**/*.jsonl` 里最新的 `rate_limits`。
- `claude`：读取 macOS Keychain 里的 Claude Code OAuth token，请求 Anthropic OAuth usage 接口。
- `auto`：先尝试 Codex，再尝试 Claude Code。
- `off`：不显示底部剩余额度状态栏。

面板显示的是剩余比例和 reset 倒计时。没有可用额度数据时 footer 会留空，不影响会话状态展示。

## Cowork 桥接

Claude.app 的 Cowork 会话跑在本地 VM 里，宿主机 hooks 不能直接观察 VM 内部状态。本仓库提供 `scripts/cowork-vibesignal-bridge`，通过 VM 进程 CPU 和本地会话文件活动近似判断 Cowork 是否在工作。

安装：

```bash
cp scripts/cowork-vibesignal-bridge ~/.local/bin/
chmod +x ~/.local/bin/cowork-vibesignal-bridge
cp scripts/io.github.yzhao062.vibesignal.cowork-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.github.yzhao062.vibesignal.cowork-bridge.plist
```

调试：

```bash
cowork-vibesignal-bridge --once
```

更多迁移和排障步骤见 [INSTALL.md](INSTALL.md)，相对上游的定制说明见 [CUSTOMIZATIONS.md](CUSTOMIZATIONS.md)。

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,macos]'
pytest
```

项目入口在 `vibesignal/__main__.py`，桌面面板在 `vibesignal/widget.py`，状态解析逻辑在 `vibesignal/resolve.py`。

## 许可证

本项目沿用上游的 BSD-2-Clause License，详见 [LICENSE](LICENSE)。
