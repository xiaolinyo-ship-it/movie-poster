# MoviePoster

MoviePoster（电影搜刮器）是一个面向 Windows 的本地优先影视媒体库桌面应用，使用 Python、PySide6 和 SQLite 构建。它用于扫描本地磁盘或 NAS 上的电影/电视剧，整理元数据与海报，并在桌面端浏览、搜索和播放媒体。

## Features（主要功能）

- 扫描本地目录或 NAS/UNC 共享中的电影和电视剧
- 识别并统计电影 / 电视剧媒体
- 处理豆瓣与 TMDB 元数据
- 管理海报、背景图与人物/类型关系数据
- Jellyfin 风格的首页与详情页展示
- 保留“我的媒体”首页，将“接下来”替换为“我的订阅”；该行读取 dyjie.net 订阅页的“最近更新的影视”，其他首页栏目保持完整媒体库
- 收藏、观看状态、搜索与 Next Up（继续观看）
- 调用 Windows PotPlayer 播放本地媒体
- SQLite 本地数据库，媒体文件和数据库默认不上传到任何服务

## Requirements（运行要求）

- Windows 10/11
- Python 3.11+（源码运行）
- PotPlayer（可选；仅用于外部播放）
- TMDB API Key（可选；用于 TMDB 补充元数据）

## Run from source（源码运行）

```powershell
git clone https://github.com/xiaolinyo-ship-it/movie-poster.git
cd movie-poster
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

首次运行后，在应用设置中配置电影/电视剧目录。仓库不会包含维护者的 NAS 地址、数据库、缓存、媒体文件或 API Key。

在左上角菜单选择“同步我的订阅”后，首次需要在应用内登录 dyjie.net；MoviePoster 使用独立的 QtWebEngine 会话保存登录状态，不会把密码、Cookie 或令牌写入 `config.json`。同步结果只保存标题、更新时间和链接，用于填充“我的订阅”行与限定自动更新范围。

## Build（构建 Windows 版本）

```bat
build.bat
```

构建产物位于 `dist\MoviePoster\MoviePoster.exe`。`config.json`、SQLite 数据库、缓存和本地媒体不会被打包进公开构建。

## Configuration（配置）

MoviePoster 会在运行目录创建本地 `config.json`。TMDB API Key 仅保存在你的本机配置中。请不要把真实配置文件提交到 Git。

## Data sources（数据来源）

TMDB 支持为可选功能。使用者需要自行取得并遵守 TMDB 的 API 使用条款。豆瓣相关功能仅用于获取媒体展示所需的公开元数据信息；使用者应自行遵守相应网站和地区的适用规则。

MoviePoster 与 TMDB、豆瓣、Jellyfin 或 PotPlayer 均无官方隶属或背书关系。

## Privacy（隐私）

MoviePoster 是 local-first（本地优先）桌面工具。媒体库数据库、缓存、观看状态和本地路径默认保存在用户自己的设备上。

## Contributing（参与贡献）

欢迎提交真实的 Bug（缺陷）报告、改进建议和 Pull Request（拉取请求）。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按照 [SECURITY.md](SECURITY.md) 私下报告。

## License（许可证）

本项目源代码以 MIT License 发布，详见 [LICENSE](LICENSE)。第三方服务、商标、元数据与图片仍受各自权利人的许可和条款约束。
