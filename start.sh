#!/bin/bash

# 启动 Uvicorn web 服务器 (后台运行)
echo "Starting Uvicorn server..."
uvicorn main:app --host 0.0.0.0 --port 6679 &

# 等待几秒钟，以确保 web 服务器已完全启动
echo "Waiting for server to start..."
sleep 5

# 启动 Telegram Bot (前台运行)
echo "Starting Telegram Bot..."
python telegram_bot.py
