# 安装与配置

## 环境

- Windows 10/11 为首发主要环境；Python 3.12+、Node.js。其他平台使用直接 Python 入口，完整兼容性未验收。
- Codex CLI：按[官方安装说明](https://learn.chatgpt.com/docs/codex/cli)安装并 `codex login`。
- CodeBuddy Code：按[官方快速入门](https://www.codebuddy.cn/docs/cli/quickstart)完成自己的登录。项目适配的固定版本为 `2.164.0`，准备命令是 `python scripts/prepare_runtime.py`。
- 后端无必需 pip 依赖；可选 PDF、DOCX、XLSX 文字提取依赖：`python -m pip install -r requirements-optional.txt`。未安装时会提示缺少解析器。

Node.js 需满足所用 CLI 的要求。不要在仓库中复制 CLI 登录文件、API Key 或运行时缓存。默认测试与离线预览均不需要登录。

## 启动

```powershell
python server.py --open
```

`--port 8766` 指定起始端口；占用时尝试后续九个端口。`--data PATH` 改数据目录，`--archive PATH` 改资料/每日记录目录。默认两者分别是项目 `data/` 与其中的 `archive/`。

`--offline` 不启动双方 CLI，可用于检查网页。它仍创建独立的本地数据库；不要把该数据库提交或分享。

Windows 的 `Start-CodeDuo.cmd` 调用 `scripts/start.ps1`，在当前终端前台运行服务，按 Ctrl+C 停止。可使用 `-NoBrowser` 或 `-Offline`。它不安装系统服务、计划任务或登录启动项。

## 运行路径

复制 `config.example.json` 为被忽略的 `config.local.json`，按需填入自己的路径；空字符串表示自动发现：

| 字段 | 内容 |
| --- | --- |
| `node` | Node.js 可执行文件 |
| `codex` | Codex CLI 可执行入口 |
| `codebuddy` | CodeBuddy npm 包中的 `bin/codebuddy` JavaScript 文件；不要填安装目录或 `.cmd` 包装器 |

也可用 `CODEX_CLI_PATH`、`CODEBUDDY_CLI_PATH` 和 `NODE_PATH_EXECUTABLE` 配置；Windows 启动器接受 `CODEDUO_PYTHON`。

`prepare_runtime.py` 下载官方固定版本到用户缓存并校验 npm 元数据中的 SHA-512，同时准备图标。默认 Windows 缓存在 `%LOCALAPPDATA%/CodeDuo/runtime/`；其他平台使用用户缓存目录。生成的 `runtime-manifest.json` 含本机路径，已被 Git 忽略。

准备完成后，用它输出的入口启动 CodeBuddy CLI 登录，例如：

```powershell
node "$env:LOCALAPPDATA\CodeDuo\runtime\codebuddy\2.164.0\bin\codebuddy"
```

CLI 对登录、账号和计费的实际提示为准。本网页不代收账号密码或验证码。

## 第一次协作

1. 刷新连接，确认双方就绪，从各自实际模型列表中选择模型。
2. 新建对话，登记固定需求、任务与相关附件。新安装默认仅讨论。
3. 选择单方或一起讨论及轮数，发送明确问题；需要实施时才主动开启完全访问并选择自己的工程目录。
4. 提问出现后直接作答；中途补充以送达回执为准。停止不会撤销已完成的文件改动。
5. 在交接页导出记录；分享前重新脱敏。

完全访问下的资源协调依赖当前 CLI 的工具/钩子协议。若明确提示应用钩子未受信任，可检查 `python scripts/register_resource_hook.py` 的代码后手工运行；该脚本只登记精确应用钩子的哈希，会改动自己的 Codex 配置，不应不经检查自动运行。讨论和离线预览不需要运行它。

## 常见问题

- **Python 找不到**：安装 Python 3.12+ 并加入 PATH，或配置 `CODEDUO_PYTHON`。本项目不要求安装 Codex 桌面应用的私有运行环境。
- **某一方连接失败**：先在同一用户的终端中验证 CLI 入口和登录，再核对路径；不要用默认模型名冒充就绪。
- **账号能列模型但调用失败**：可选列表不代表当前模型权限、额度或协议均可用，查看实际错误。
- **网页刷新后数据仍在**：它保存在本机 SQLite。退出网页不会删除数据库；源码更新请保留自己的 `data/`。
- **后台完全退出后浏览器无法重连**：重新运行启动入口。普通网页不会启动本机 Python 进程。
