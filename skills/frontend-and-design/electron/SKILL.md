---
name: electron
description: Provides comprehensive guidance for Electron framework including main process, renderer process, IPC communication, window management, and desktop app development. Use when the user asks about Electron, needs to create desktop applications, implement Electron features, or build cross-platform desktop apps.
license: Complete terms in LICENSE.txt
---

## When to use this skill

Use this skill whenever the user wants to:
- Build cross-platform desktop applications with Electron
- Understand Electron architecture (main process, renderer process, preload)
- Implement IPC (Inter-Process Communication) between processes
- Create and manage BrowserWindow instances
- Implement menus, tray icons, and native features
- Package and distribute Electron applications
- Use Electron Forge for project scaffolding and building
- Debug and test Electron applications
- Implement security best practices
- Use Electron APIs (app, BrowserWindow, ipcMain, ipcRenderer, etc.)

## How to use this skill

This skill partially mirrors the Electron documentation structure. The local managed copy only routes to files that are actually present in this repository. For topics that are not covered by a local reference file, fall back to the official Electron docs linked below.

1. **Identify the topic** from the user's request:
   - Getting started/快速开始 -> `examples/getting-started/installation.md` or `examples/getting-started/quick-start.md`
   - Main process/主进程 -> `examples/processes/main-process.md`
   - IPC communication/IPC 通信 -> `examples/processes/ipc-communication.md`
   - BrowserWindow/窗口 -> `examples/api/browser-window.md`
   - Menu/菜单 -> `examples/api/menu.md`
   - Packaging/打包 -> `examples/advanced/packaging.md`
   - App lifecycle/app 模块 -> `api/app.md`
   - BrowserWindow API -> `api/browser-window.md`

2. **Load the appropriate local file first**:

   **Getting Started - `examples/getting-started/`**:
   - `examples/getting-started/installation.md` - Installing Electron and basic setup
   - `examples/getting-started/quick-start.md` - Quick start tutorial

   **Processes - `examples/processes/`**:
   - `examples/processes/main-process.md` - Main process concepts and usage
   - `examples/processes/ipc-communication.md` - IPC communication patterns

   **API Examples - `examples/api/`**:
   - `examples/api/browser-window.md` - BrowserWindow usage
   - `examples/api/menu.md` - Menu and context menu

   **Advanced - `examples/advanced/`**:
   - `examples/advanced/packaging.md` - Application packaging

   **API Reference - `api/`**:
   - `api/app.md` - app module API
   - `api/browser-window.md` - BrowserWindow API

   **Templates - `templates/`**:
   - `templates/main-process.md` - Main process template
   - `templates/preload-script.md` - Preload script template

3. **If the requested topic is not covered locally**, use the official Electron documentation for:
   - renderer process
   - preload patterns beyond the provided template
   - dialog, tray, ipcMain, ipcRenderer API details
   - security hardening
   - auto updates
   - native modules
   - Electron Forge and Electron Fiddle specifics

4. **Follow these operating rules while using the skill**:
   - Prefer the local example or template when it exists.
   - When a local reference does not exist, cite or align to the official Electron docs instead of inventing a repo-local file path.
   - Keep main, preload, and renderer responsibilities clearly separated.
   - Default to secure IPC and `contextBridge` patterns rather than direct Node exposure in the renderer.


### Doc mapping (one-to-one with official documentation)

- `examples/` → https://www.electronjs.org/zh/docs/latest/
- `api/` → https://www.electronjs.org/zh/docs/latest/api/app

## Examples and Templates

This skill includes a curated subset of local examples plus templates for common Electron entry points.

**To use examples:**
- Identify the topic from the user's request
- Load the appropriate local example file from the mapping above
- Follow the instructions, syntax, and best practices in that file
- If the topic is not covered locally, fall back to the official Electron docs linked in this file

**To use templates:**
- Reference templates in `templates/` directory for common scaffolding
- Adapt templates to your specific needs and coding style

## API Reference

Detailed API documentation is available in the `api/` directory, organized to match the official Electron API documentation structure:

### Core APIs (`api/`)
- `api/app.md` - app module API
- `api/browser-window.md` - BrowserWindow API

**To use API reference:**
1. Identify the API you need help with
2. Load the corresponding local API file from the `api/` directory when available
3. If a local API file is not present, use the official Electron API reference linked above
4. Find the API signature, parameters, return type, and examples
5. Cross-check with the local example files for implementation patterns when available

## Best Practices

1. **Security**: Never enable nodeIntegration in renderer process, use preload scripts
2. **Process separation**: Keep main and renderer processes separate
3. **IPC communication**: Use IPC for safe communication between processes
4. **Resource management**: Properly clean up resources (windows, listeners)
5. **Error handling**: Implement proper error handling and crash reporting
6. **Performance**: Optimize for performance, use webContents for debugging
7. **Packaging**: Use Electron Forge or electron-builder for packaging
8. **Auto updates**: Implement auto-updater for production apps
9. **Native modules**: Handle native module compatibility
10. **Cross-platform**: Test on all target platforms

## Resources

- **Official Website**: https://www.electronjs.org/zh/
- **Documentation**: https://www.electronjs.org/zh/docs/latest/
- **API Reference**: https://www.electronjs.org/zh/docs/latest/api/app
- **Electron Forge**: https://www.electronforge.io
- **Electron Fiddle**: https://www.electronjs.org/zh/fiddle
- **GitHub Repository**: https://github.com/electron/electron

## Keywords

Electron, desktop app, main process, renderer process, preload, IPC, BrowserWindow, Menu, Tray, Dialog, packaging, electron-builder, electron-forge, electron-fiddle, cross-platform, 桌面应用, 主进程, 渲染进程, IPC 通信, 窗口, 菜单, 托盘, 打包

## 能力边界

### ✅ 适用场景
- 当你需要使用此技能对应的技术栈时
- 当项目需要遵循最佳实践时
- 当需要快速上手或深入理解核心概念时

### ⚠️ 需要注意
- 复杂业务逻辑需要结合具体场景调整
- 性能优化需要根据实际数据量评估

### ❌ 不适用场景
- 不相关的技术栈或框架
- 需要完全自定义的特殊场景

## 常见陷阱 (Gotchas)

1. **版本兼容性**：注意框架版本与依赖库的兼容性，不同版本 API 可能有差异
2. **配置文件格式**：配置文件格式错误是最常见的问题，建议使用编辑器的语法检查
3. **环境变量**：确保所有必要的环境变量已正确设置，敏感信息不要硬编码
4. **依赖冲突**：多版本共存时注意依赖冲突，使用 lock 文件锁定版本
5. **性能陷阱**：大数据量场景下注意性能优化，避免 N+1 查询等常见问题

## 使用流程

### Step 1: 环境准备
确保开发环境已安装必要的依赖和工具。

### Step 2: 配置初始化
根据项目需求进行基础配置。

### Step 3: 核心功能使用
按照示例代码实现核心功能。

### Step 4: 测试验证
运行测试确保功能正常。

### Step 5: 部署上线
完成开发后进行部署和监控。

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: full-statck-skills/electron-skills
- upstream path: skills/electron
- pinned ref: 088a6d7ed27356a121730535abf76a35c70225a3
- source type: github
- source URL: https://github.com/full-statck-skills/electron-skills/tree/main/skills/electron
- imported at: 2026-06-14T14:30:00.404Z
- last verified ref: 088a6d7ed27356a121730535abf76a35c70225a3
- local modifications: true
<!-- skillctl:source-attribution:end -->
