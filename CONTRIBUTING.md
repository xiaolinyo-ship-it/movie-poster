# Contributing to MoviePoster

感谢你参与 MoviePoster。

## Before opening an issue

请先确认问题可以在当前版本复现，并提供：

- Windows 版本
- Python 版本或 MoviePoster Release 版本
- 可复现步骤
- 预期行为与实际行为
- 必要的日志或截图（请先删除 API Key、本地用户名、NAS 地址、媒体文件名等私人信息）

## Pull requests

1. 从最新 `main` 创建分支。
2. 每个 Pull Request 只解决一个明确问题。
3. 不要提交 `config.json`、数据库、缓存、媒体文件、API Key、Cookie 或个人路径。
4. 修改后台线程、扫描、数据库或播放逻辑时，请说明回归测试范围。
5. 确保应用可以启动，并对改动涉及的主要路径做基本验证。

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Scope

MoviePoster 聚焦 Windows 本地/NAS 影视媒体库的扫描、元数据、展示和播放工作流。与此目标无关的大型功能建议请先通过 Issue 讨论。
