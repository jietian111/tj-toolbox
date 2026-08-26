---
name: codex-proxy-launcher
description: Create or repair a full-featured Windows desktop launcher that forces the Codex or ChatGPT app through a user-specified local HTTP proxy and survives AppX updates. Use for reconnecting problems, stale executable paths, proxy launch shortcuts, or broken shortcut icons on Windows.
---

# Codex Proxy Launcher

Create the working launcher and verify it. Do not stop at instructions.

## Required Input

Obtain the user's local HTTP proxy port before changing files. If absent, ask one concise question in the user's language: `你的本地 HTTP 代理端口是多少？只需要给我数字，例如 7897。`

Accept an integer from 1 through 65535. Default to loopback host `127.0.0.1`; ask for a host only when the user explicitly needs a non-loopback proxy.

## Install Or Repair

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\install_codex_proxy_launcher.ps1" -ProxyPort <port>
```

The installer creates a self-contained launcher folder on the desktop and `Codex.lnk`. It may replace its own prior launcher files and shortcut when repairing or changing the port. Never remove unrelated desktop files.

Preserve all packaged behavior: standard proxy environment variables, Chromium proxy arguments, dynamic AppX/Manifest entrypoint discovery, `ChatGPT.exe` and `Codex.exe` compatibility, shortcut icon refresh after app updates, child-process tool PATH repair, `--check`, and `--env-check`.

## Verify

Run the generated CMD with `--check`. Report the exact proxy URL, resolved app path, launcher folder, shortcut path, and proxy-port state. Run `--env-check` when the user asks about bundled command-line tools.

A closed proxy port does not prevent installation. Clearly tell the user to start their local proxy before opening Codex.

For isolated testing, pass both `-OutputDirectory` and `-ShortcutPath` with temporary paths.
