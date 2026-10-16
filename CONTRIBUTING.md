# 参与贡献

欢迎提交 Bug、文档修正和有测试依据的改动。请先阅读 [README](README.md) 与 [隐私说明](docs/PRIVACY.md)。

1. Fork 仓库，在独立分支上修改。
2. 使用合成数据或临时目录复现问题；不要上传自己的 `data/`、账号配置、上传附件或真实对话。
3. 用 `python -m pip install -r requirements-dev.txt` 安装完整测试依赖，再运行 Python 测试、JavaScript 测试与隐私扫描，命令见 README。
4. Pull Request 说明触发条件、修改后行为、验证范围及仍未覆盖的情况。

默认测试不能依赖真实模型、扣费请求、SSH 或外部设备。需要人工推理验证时应单独说明，并使用自己的账号明确执行。

提交补丁表示你有权按本项目 MIT 许可证提供该部分贡献。请保留第三方版权与许可声明。
