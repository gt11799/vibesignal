# AI 安装指南 —— 在新 Mac 上完整部署本套件

> 读者：执行迁移安装的 AI agent（Claude Code / Codex 等）。
> 目标：把本仓库的定制版 vibesignal 及全部周边（hooks、图标、Codex 剩余额度 footer、Cowork 桥接）在一台新 Mac 上恢复到与源机器一致的状态。
> 原则：每步都有验证命令，验证不过不要进入下一步。标注 **[需要人类]** 的步骤 AI 无法代劳，必须明确请用户操作。

## 0. 这套东西是什么

- **vibesignal**（本仓库，fork 自 yzhao062/vibesignal）：AI 编码客户端的桌面状态面板。
  定制内容见 `CUSTOMIZATIONS.md`（高对比深色主题、右上角停靠、Tk 9 无边框修复、Dock 图标、Codex 剩余额度 footer）。
- **hooks**：Claude Code（`~/.claude/settings.json`）和 Codex（`~/.codex/hooks.json`）在会话事件时调 `vibesignal event` 上报状态。
- **Cowork 桥接**（`scripts/cowork-vibesignal-bridge`）：Claude.app 的 Cowork 跑在本地 VM 里、hooks 够不到，用 VM 进程 CPU + 文件活动近似出状态行。
- **能力边界**：只覆盖本机执行的会话。云端会话（claude.ai cloud）原理上不可见，不要试图"修"它。

## 1. 前置条件检查

```bash
sw_vers                 # macOS，本套件只在 Apple Silicon 验证过
uv --version            # 没有则: curl -LsSf https://astral.sh/uv/install.sh | sh
codex --version         # Codex 已安装
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".codex/auth.json"
data = json.loads(p.read_text())
assert (data.get("tokens") or {}).get("access_token")
print("Codex 登录态 OK")
PY
```

## 2. 安装 vibesignal（从本仓库）

```bash
uv tool install --force --python-preference only-managed --python 3.13 \
  'vibesignal[macos] @ git+file://<本仓库的绝对路径>'
vibesignal --version 2>/dev/null || ~/.local/bin/vibesignal status
```

必须 `--python-preference only-managed`：Homebrew Python 不带 tkinter；uv 托管的 CPython 带。

## 3. 安装后修复（Tcl/Tk 符号链接）—— 必做

uv 托管 Python 的 venv 找不到 `init.tcl`，widget 会崩（日志报 "Tcl wasn't installed properly"）。
最简单：跑一次仓库里的 restyle 脚本（幂等；对本 fork 安装它只做符号链接和重启，源码补丁会检测到已应用而跳过）：

```bash
cp scripts/vibesignal-restyle ~/.local/bin/ && chmod +x ~/.local/bin/vibesignal-restyle
~/.local/bin/vibesignal-restyle   # 输出应含 "linked ... tcl9.0" 和 "widget.py already patched"
```

注意：`launchctl kickstart` 在第 4 步 autostart 装好前会报错，忽略即可。
**每次 `uv tool install --force/upgrade` 重建 venv 后，都要重跑一次本脚本。**

## 4. 启动器 + 图标资产 + 自启

```bash
~/.local/bin/vibesignal install-launcher
~/.local/bin/vibesignal install-autostart      # widget 立即启动并登录自启
```

`install-launcher` 会自动把包内置图标复制到 `~/Applications/VibeSignal.app/Contents/Resources/applet.icns`
并重签 `.app`，同时把 `dock-icon.png` 和 `VibeSignal.icns` 放到 `~/.local/share/vibesignal/`，
供运行中的 widget 设置 Dock 图标使用。若看到默认空白脚本图标，重新运行
`~/.local/bin/vibesignal install-launcher`。

验证：`pgrep -fl "vibesignal widget"` 有进程；`tail /tmp/io.github.yzhao062.vibesignal.err` 无新报错；
面板出现在**主屏右上角**（多显示器时在"键盘焦点所在屏"的右上角），文字为高对比白色粗体，底部 Codex 剩余额度状态栏清晰可读。

## 5. Claude Code hooks

把 `hooks/claude-settings.snippet.json` **合并**（不是覆盖）进 `~/.claude/settings.json` 的 `hooks`，
并把命令里的 `vibesignal` 换成绝对路径 `$HOME/.local/bin/vibesignal`（hook 环境的 PATH 不含 `~/.local/bin`）。
若已有其他 hooks（如 Otty），在同一事件的数组里**追加**新条目。

pipe-test（先于真实验证做）：

```bash
echo '{"session_id":"pipetest"}' | ~/.local/bin/vibesignal event --agent claude --state working --quiet; echo $?   # 0
~/.local/bin/vibesignal status    # 应出现 claude/pipetest
echo '{"session_id":"pipetest"}' | ~/.local/bin/vibesignal end --agent claude --quiet
jq -e '.hooks | keys' ~/.claude/settings.json   # JSON 合法性；坏 JSON 会静默禁用整个 settings 文件
```

真实验证：新开一个 claude 会话发条消息 → `vibesignal status` 出现该会话。
（正在运行的旧会话通常会热加载新 hooks；不行就开新会话。）

## 6. Codex hooks（如装有 Codex）

把 `hooks/codex-hooks.snippet.json` 合并进 `~/.codex/hooks.json`（同样：绝对路径、追加不覆盖、改前备份）。

**[需要人类]** Codex 的信任机制：合并后必须重启 Codex 客户端，在会话里执行 `/hooks`，
确认 `~/.codex/hooks.json` 下的 4 条 VibeSignal command hooks 已列出，并把它们设为信任。
未信任的 command hooks 会被 Codex 跳过。之后跑一轮真实对话，`vibesignal status` 应出现
`codex/…` 行。

坑：npm 全局的 codex CLI 若低于 0.119.0，会被 macOS XProtect 当恶意软件拦截
（2026-05 OpenAI 证书轮换事件），`npm install -g @openai/codex@latest` 升级即可，不要绕 Gatekeeper。

## 7. Codex 额度 footer

- widget 每 5 分钟读取 `~/.codex/auth.json` 的 ChatGPT access token，优先调
  `https://chatgpt.com/backend-api/codex/usage`；接口不可用时读取本机
  `~/.codex/sessions/**/*.jsonl` 最新 `rate_limits`。
- footer 显示 Codex 5 小时窗口和周窗口的剩余比例与 reset 倒计时，例如
  `5h 57% (4h40m) · wk 64% (5d16h)`。没有可用额度数据时 footer 留空，不影响状态面板。
- 验证：`env -i HOME="$HOME" PATH=/usr/bin:/bin \
  ~/.local/share/uv/tools/vibesignal/bin/python -c "from vibesignal.widget import _fetch_usage; print(_fetch_usage())"`
  应输出形如 `5h 57% (4h40m) · wk 64% (5d16h)`。

## 8. Cowork 桥接（如使用 Claude.app 的 Cowork）

```bash
cp scripts/cowork-vibesignal-bridge ~/.local/bin/ && chmod +x ~/.local/bin/cowork-vibesignal-bridge
cp scripts/io.github.yzhao062.vibesignal.cowork-bridge.plist ~/Library/LaunchAgents/
# 两个文件里硬编码了源机器用户目录，替换为本机的：
sed -i '' "s|/Users/kris.gong|$HOME|g" \
  ~/.local/bin/cowork-vibesignal-bridge \
  ~/Library/LaunchAgents/io.github.yzhao062.vibesignal.cowork-bridge.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.github.yzhao062.vibesignal.cowork-bridge.plist
~/.local/bin/cowork-vibesignal-bridge --once   # Cowork 未跑时应输出 quiet
```

## 9. 全链路验收清单

| # | 检查 | 期望 |
|---|---|---|
| 1 | `pgrep -fl "vibesignal widget"` | 有进程 |
| 2 | 面板外观 | 深色、无边框、右上角、压在其他窗口之上，白底桌面上文字清楚 |
| 3 | 新开 claude 会话发消息 | 面板出现 claude 行（绿色 working） |
| 4 | Codex 跑一轮对话 | 面板出现 codex 行 |
| 5 | footer | 显示 `5h x% (…) · wk x% (…)` |
| 6 | `launchctl list \| grep vibesignal` | 两个服务（widget + cowork-bridge）都有 PID |
| 7 | 跑一个 Cowork 任务 | ~20 秒内出现 `cowork-vm` 行，静默 3 分钟后转 done |

## 10. 已知坑速查

- **widget 崩、日志报 Tcl**：第 3 步符号链接丢了（uv 重建 venv 后必现）→ 重跑 restyle。
- **面板有标题栏/被裁剪/不置顶**：Tk 9 无边框回归——本 fork 源码已修（MacWindowStyle），
  如果出现说明装的不是本仓库版本。
- **hook 不触发**：优先怀疑命令路径（必须绝对路径）；`echo '{}' | <hook命令>` 手测；
  settings.json 是否合法 JSON。
- **面板行"消失"**：done/idle 按 TTL 自动过期，是设计行为。
- **某会话不显示**：先确认它真的在本机执行（`~/.claude/projects/` 有转录）。
  Cowork 走桥接（近似信号）；云端会话无解。
- **rootfs.img / rpm/manifest.json 频繁变动**：Cowork VM 热备噪声，桥接已过滤，不要加回监控。

## 11. 仓库怎么搬

任选：`git bundle create vibesignal.bundle --all` 后拷走（新机 `git clone vibesignal.bundle`）；
或整个目录拷贝；或推到私有远端后 clone。搬完后第 2 步的 `git+file://` 指向新位置即可。
与上游同步：`git fetch upstream && git rebase upstream/main`（remote `upstream` 已配好）。
