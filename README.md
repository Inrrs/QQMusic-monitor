# QQMusic-monitor

这是一个功能强大的QQ音乐下载和歌单监控工具，结合了Web界面和Telegram机器人，为您提供无缝的音乐管理体验。

## ✨ 功能特性

- **Web界面**:
  - 扫码登录您的QQ音乐账户。
  - 浏览您的自建歌单和收藏歌单。
  - 查看歌单内的所有歌曲。
  - 点击按钮即可下载单曲或整个歌单。
  - 实时查看下载任务的状态（排队中、下载中、已完成、失败）。
  - 管理下载任务（重试、取消、移除）。
  - 监控您喜欢的歌单，当歌单有更新时自动下载新增歌曲。

- **Telegram Bot**:
  - 获取QQ音乐登录二维码。
  - 查看登录状态。
  - 以交互方式管理歌单监控。
  - 查看正在下载和已完成的任务列表。
  - 机器人启动/重启时自动发送通知。

- **核心优势**:
  - **多任务并行下载**: 支持多个任务同时下载，可配置并行数量。
  - **断点续传**: 程序重启后，未完成的任务会自动标记为失败，方便重试。
  - **状态持久化**: 所有下载任务的状态都会被保存，即使重启程序也不会丢失。
  - **灵活部署**: 提供 `Dockerfile` 和 `docker-compose.yml`，方便容器化部署。

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
    version: '3.8'
    services:
      app:
        image: cinrrs/qqmusic-monitor:latest
        container_name: QQMusic-monitor
        ports:
          - "6679:6679"
        network_mode: bridge
        volumes:
          - ./downloads:/app/downloads
        restart: always
        environment:
          # 你的 Telegram Bot Token
          - TELEGRAM_TOKEN=
          # 授权用户的 Telegram ID，多个用户请用英文逗号分隔
          # 例如：AUTHORIZED_USERS=12345678,87654321
          - AUTHORIZED_USERS=
          # 代理地址，如果不需要请留空
          # 例如：PROXY_URL=http://127.0.0.1:7890
          - PROXY_URL=
          # --- 性能配置 ---
          # 最大并发下载数 (推荐 3-10)
          - MAX_CONCURRENT_DOWNLOADS=10
    ```
    **注意**: 请务必修改 `environment` 部分，填入你自己的 `TELEGRAM_TOKEN` 和 `AUTHORIZED_USERS`。

3.  **启动服务**:
    ```bash
    docker-compose up -d
    ```

4.  **访问与交互**:
    - Web界面: 打开浏览器，访问 `http://localhost:6679`。
    - Telegram Bot: 与您的机器人开始对话。

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
      -p 6679:6679 \
      -v $(pwd)/downloads:/app/downloads \
      -e TELEGRAM_TOKEN="YOUR_TELEGRAM_TOKEN" \
      -e AUTHORIZED_USERS="YOUR_TELEGRAM_USER_ID" \
      -e PROXY_URL="" \
      -e MAX_CONCURRENT_DOWNLOADS=10 \
      cinrrs/qqmusic-monitor:latest
    ```

### 手动运行

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **设置环境变量**:
    我们提供了一个环境变量示例文件 `.env.example`。您可以复制它来创建自己的 `.env` 文件：
    ```bash
    cp .env.example .env
    ```
    然后，编辑 `.env` 文件，填入您的配置信息，例如：
    ```dotenv
    # 你的 Telegram Bot Token
    TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
    
    # 授权用户的 Telegram ID
    AUTHORIZED_USERS=123456789
    
    # 代理地址，如果不需要请留空
    PROXY_URL=
    
    # 最大并发下载数
    MAX_CONCURRENT_DOWNLOADS=10
    ```
    程序启动时会自动加载 `.env` 文件中的环境变量。

3.  **启动服务**:
    ```bash
    ./start.sh
    ```
    这将同时启动Web服务器和Telegram Bot。

## 🙏 致谢

本项目的核心功能严重依赖于 [luren-dc/QQMusicApi](https://github.com/luren-dc/QQMusicApi) 这个出色的库。没有它，这个项目不可能实现。在此表示衷心的感谢！

---
*祝您使用愉快！*
