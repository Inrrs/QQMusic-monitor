# QQMusic-monitor

这是一个功能强大的QQ音乐下载和歌单监控工具，提供Web界面，为您提供无缝的音乐管理体验。

## ✨ 功能特性

- **Web界面**:
  - 多种登录方式：QQ扫码登录、微信扫码登录、手机号登录。
  - 浏览您的自建歌单和收藏歌单。
  - 查看歌单内的所有歌曲。
  - 智能检测本地已下载歌曲，显示音质和文件大小。
  - 点击按钮即可下载单曲或整个歌单。
  - 实时查看下载任务的状态（排队中、下载中、已完成、失败）。
  - 管理下载任务（重试、取消、移除）。
  - 监控您喜欢的歌单，当歌单有更新时自动下载新增歌曲。
  - 网页端配置管理，支持修改下载、监控和通知设置。

- **通知系统**:
  - Webhook通知：支持自定义Webhook URL。
  - Bark通知：支持Bark推送通知，兼容iOS和Android设备。

- **核心优势**:
  - **多任务并行下载**: 支持多个任务同时下载，可配置并行数量。
  - **断点续传**: 程序重启后，未完成的任务会自动标记为失败，方便重试。
  - **状态持久化**: 所有下载任务的状态都会被保存，即使重启程序也不会丢失。
  - **灵活部署**: 提供 `Dockerfile` 和 `docker-compose.yml`，方便容器化部署。
  - **本地歌曲索引**: 智能扫描本地歌曲，高效匹配本地文件。

## ⚠️ 注意事项

- **API 限制**: 经作者测试，QQ音乐的API对单个账号的下载量似乎有限制，一天大约在 **190首** 左右。如果在确定登录账号及权限没问题的时候遇到大量下载失败，请考虑是否触发了此限制。
- **Bug反馈**: 如果您在使用过程中遇到任何问题或发现Bug，欢迎通过 [提交 Issues](https://github.com/Inrrs/QQMusic-monitor/issues) 的方式进行反馈。

## 🚀 部署与使用

### 使用 Docker Compose (推荐)

1.  **准备目录**:
    创建一个用于存放 `docker-compose.yml` 和下载文件的目录。
    ```bash
    mkdir qqmusic-monitor
    cd qqmusic-monitor
    ```

2.  **创建 `docker-compose.yml` 文件**:
    在 `qqmusic-monitor` 目录下，创建一个 `docker-compose.yml` 文件，内容如下：
    ```yml
    services:
      app:
        image: cinrrs/qqmusic-monitor:latest
        container_name: QQMusic-monitor
        ports:
          - "6696:6696"
        network_mode: bridge
        volumes:
          - ./data:/app/data
          - ./downloads:/app/downloads
        restart: always
    ```

3.  **启动服务**:
    ```bash
    docker-compose up -d
    ```

4.  **访问与交互**:
    - Web界面: 打开浏览器，访问 `http://localhost:6696`。

### 使用 `docker run`

如果您不想使用 `docker-compose`，也可以直接使用 `docker run` 命令。

1.  **拉取镜像**:
    ```bash
    docker pull cinrrs/qqmusic-monitor:latest
    ```

2.  **运行容器**:
    请将下面的命令中的环境变量替换为您自己的值。
    ```bash
    docker run -d \
      --name QQMusic-monitor \
      --restart always \
      -p 6696:6696 \
      -v $(pwd)/data:/app/data \
      -v $(pwd)/downloads:/app/downloads \
      cinrrs/qqmusic-monitor:latest
    ```

### 手动运行

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **启动服务**:
    ```bash
    ./start.sh
    ```

3.  **访问与交互**:
    - Web界面: 打开浏览器，访问 `http://localhost:6696`。
    - 在网页端完成配置：进入"配置"页面，设置下载、监控和通知参数。

## 🙏 致谢

本项目的核心功能严重依赖于 [luren-dc/QQMusicApi](https://github.com/luren-dc/QQMusicApi) 这个出色的库。没有它，这个项目不可能实现。在此表示衷心的感谢！
