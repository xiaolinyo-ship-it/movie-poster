# Movie Poster

中文名称：电影搜刮器

ROLE=OPEN_SOURCE_PROJECT

## 功能

- 本地 NAS 影视媒体扫描
- 电影 / 电视剧识别与统计
- 豆瓣与 TMDB 元数据处理
- 海报、背景图与关系数据管理
- Jellyfin 风格首页与详情页展示
- 收藏、观看状态、搜索与 Next Up
- 调用 Windows PotPlayer 播放本地媒体

## 位置

CURRENT_RUNTIME_LOCATION=
`%USERPROFILE%\AppData\Local\MoviePoster`

GITHUB_SOURCE_LOCATION=
`xiaolinyo-ship-it/movie-poster`

CURRENT_RUNTIME_CUTOVER=NO

本次 GitHub 纳仓只建立源码副本，不改变当前运行目录、数据库、媒体目录或播放配置。

## 开发说明

- 技术栈：Python + PySide6 + SQLite
- 入口文件：`main.py`
- 主界面：`app/ui.py`
- 数据访问：`app/store.py`
- 依赖清单：`requirements.txt`
- 运行脚本：`run.bat`

本仓库副本不包含运行数据库、缓存、浏览器运行数据、媒体文件、海报缓存或敏感配置。
