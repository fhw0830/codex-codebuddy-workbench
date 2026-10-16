# 开发说明

```text
server.py             回环 HTTP、写请求校验、SSE、静态资源
backend/service.py    对话任务、调用调度、交接、上下文和归档
backend/agents.py     Codex app-server / CodeBuddy CLI 适配
backend/store.py      SQLite 记录及基础文本清理
backend/resource_*    当前进程内共享资源协调及子进程钩子
backend/user_questions.py / question_mcp.py
                      人工问答与 CLI 桥接
web/                  原生浏览器界面、增量渲染与本地第三方资源
prompts/              通用接力流程
tests/                临时数据和模拟适配器回归
```

一个任务的双方按顺序执行。不同对话可在工作池中并行；对同一代码根目录或远端设备的写入会申请协调。协调作用于本应用进程，不覆盖其他应用、独立 CLI 或多个服务实例。

运行数据默认在自身 `data/` 内。初始化通过 `Service(..., connect=False)` 可在测试中禁用 CLI 发现。`server.py --offline` 同样不启动代理，但仍是可交互的本地应用，不能当成只读静态站点。

两款 CLI 的协议与版本变化可能影响模型发现、用量、问答或工具事件。修改适配器时先添加合成协议样例，避免在普通单元测试中启动真实模型。完整推理验收须使用自己的账号另外执行。
