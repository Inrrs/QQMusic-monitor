import asyncio
import os

import aiofiles
import httpx
import orjson as json

import qq_music
from shared_state import download_tasks
from utils import save_credentials

# --- 配置 ---
DATA_DIR = "data"
TASKS_FILE = os.path.join(DATA_DIR, "download_tasks.json")

# 从配置管理模块获取配置
from config import config
MAX_CONCURRENT_DOWNLOADS = config.get("download.max_concurrent", 5)
RETRY_INTERVAL_SECONDS = config.get("download.retry_interval_seconds", 24 * 3600)  # 默认24小时

# 确保数据目录在启动时存在
os.makedirs(DATA_DIR, exist_ok=True)

# --- 生产者-消费者 队列 ---
# 这是所有待处理下载任务的中央缓冲池
song_queue = asyncio.Queue()

# --- 任务管理 ---

async def load_download_tasks():
    """从文件加载下载任务，并将中断的任务标记为失败"""
    if not os.path.exists(TASKS_FILE):
        download_tasks.clear()
        return
    try:
        async with aiofiles.open(TASKS_FILE, "rb") as f:
            content = await f.read()
            if not content.strip():
                download_tasks.clear()
                return
            persisted_tasks = json.loads(content)

        for mid, task in persisted_tasks.items():
            if task.get("status") in ["downloading", "queued"]:
                persisted_tasks[mid]["status"] = "failed"
                persisted_tasks[mid]["error"] = "程序重启导致中断"

        download_tasks.clear()
        download_tasks.update(persisted_tasks)
        print(f"已从文件加载 {len(download_tasks)} 条任务历史。")
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载下载任务失败: {e}")
        download_tasks.clear()

async def _save_download_tasks():
    """将当前下载任务列表保存到文件"""
    try:
        # 使用 orjson 进行高效的 JSON 序列化
        json_data = json.dumps(download_tasks, option=json.OPT_INDENT_2)
        async with aiofiles.open(TASKS_FILE, "wb") as f:
            await f.write(json_data)
    except IOError as e:
        print(f"错误：无法保存下载任务文件: {e}")

async def _execute_download(song_mid: str, song_name: str):
    """实际执行下载的核心逻辑"""
    import time
    
    cred = qq_music.get_credential()
    if not cred:
        print("错误：无法执行下载，因为用户凭证未加载。")
        download_tasks[song_mid].update({"status": "failed", "error": "用户未登录"})
        await _save_download_tasks()
        return

    # 从凭证中获取特定于该用户的冷却时间
    cooldown_until = getattr(cred, 'cooldown_until', 0)

    print(f"开始处理: {song_name}")
    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)

    # 关键改动：总是先尝试获取下载链接
    url_info = await qq_music.get_song_download_url(song_mid)

    if url_info and url_info.get("url"):
        # 如果成功获取链接，说明限制已解除
        if cooldown_until > 0:
            print("下载链接获取成功，重置该账号的API冷却计时器。")
            cred.cooldown_until = 0
            save_credentials(cred)
        
        url = url_info["url"]
        quality = url_info["quality"]
        file_extension = url_info["extension"]
        import re
        safe_song_name = re.sub(r'[\\/*?:"<>|]', "", song_name).rstrip()
        file_path = os.path.join(download_dir, f"{safe_song_name}{file_extension}")

        download_tasks[song_mid].update({"status": "downloading", "quality": quality})
        await _save_download_tasks()

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", url, timeout=300.0) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("Content-Length", 0))
                    downloaded_size = 0

                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            downloaded_size += len(chunk)
                            if total_size > 0:
                                progress = int((downloaded_size / total_size) * 100)
                                if download_tasks[song_mid].get("progress") != progress:
                                    download_tasks[song_mid]["progress"] = progress

            download_tasks[song_mid].update(
                {
                "status": "completed",
                "progress": 100,
                "file_path": file_path,
                "url": f"/downloads/{os.path.basename(file_path)}"
            })
            print(f"下载完成: {song_name}")
            
            # 发送下载完成通知
            from notification import notification_manager
            await notification_manager.send_download_complete_notification(song_name, quality)
        except httpx.HTTPStatusError as e:
            error_message = f"HTTP 错误: {e.response.status_code} {e.response.reason_phrase}"
            download_tasks[song_mid].update({"status": "failed", "error": error_message})
            print(f"下载失败: {song_name}, 原因: {error_message}")
        except Exception as e:
            download_tasks[song_mid].update({"status": "failed", "error": f"下载时发生未知错误: {e}"})
            print(f"下载失败: {song_name}, 原因: {e}")

    else:
        # 如果获取链接失败，我们假设是API限制
        error_msg = "无法获取下载链接 (可能是API限制)"
        
        current_time = int(time.time())
        if current_time >= cooldown_until:
            cooldown_duration = RETRY_INTERVAL_SECONDS
            new_cooldown_until = current_time + cooldown_duration
            cred.cooldown_until = new_cooldown_until
            print(f"触发API限制，该账号冷却至: {time.ctime(new_cooldown_until)}")
        else:
            new_cooldown_until = cooldown_until
            print(f"该账号仍处于冷却期，使用现有冷却时间: {time.ctime(new_cooldown_until)}")

        save_credentials(cred) # 保存更新后的冷却时间到文件

        download_tasks[song_mid].update({
            "status": "waiting_for_retry",
            "error": "账号超出下载限制",
            "retry_at": new_cooldown_until
        })
        
    await _save_download_tasks()

async def download_worker():
    """消费者：从队列中获取并处理下载任务"""
    while True:
        try:
            song_mid, song_name = await song_queue.get()

            task_state = download_tasks.get(song_mid)
            if not task_state or task_state.get("status") == "cancelled":
                print(f"任务 {song_name} 已被取消，跳过下载。")
                song_queue.task_done()
                continue

            await _execute_download(song_mid, song_name)
            song_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"下载工作者出错: {e}")

def start_download_workers():
    """启动指定数量的后台下载工作者并返回它们的任务对象"""
    tasks = []
    for i in range(MAX_CONCURRENT_DOWNLOADS):
        task = asyncio.create_task(download_worker())
        tasks.append(task)
    print(f"已启动 {MAX_CONCURRENT_DOWNLOADS} 个下载工作者。")
    return tasks

async def retry_failed_tasks_periodically():
    """后台任务：定期检查并重试等待中的任务"""
    while True:
        # 缩短检查周期，以便更及时地处理到期的重试任务
        await asyncio.sleep(60) 
        import time
        current_time = int(time.time())

        tasks_to_retry = {
            mid: task
            for mid, task in download_tasks.items()
            if task.get("status") == "waiting_for_retry" and current_time >= task.get("retry_at", float('inf'))
        }

        if not tasks_to_retry:
            continue

        print(f"发现 {len(tasks_to_retry)} 个到期的重试任务，正在将它们重新加入队列...")
        for mid, task in tasks_to_retry.items():
            song_name = task.get("song_name", "未知歌曲")
            await add_song_to_queue(mid, song_name)
        
        # 当任务到期时，我们不需要在这里做任何特殊操作
        # 工作线程将自动尝试下载并根据结果更新冷却时间
        print("所有到期的重试任务已重新加入下载队列。")

def start_retry_task():
    """在后台启动定时重试任务"""
    print(f"启动后台定时重试任务，检查间隔为 {RETRY_INTERVAL_SECONDS / 3600:.1f} 小时。")
    asyncio.create_task(retry_failed_tasks_periodically())

async def add_song_to_queue(song_mid: str, song_name: str):
    """生产者接口：将歌曲加入下载队列"""
    download_tasks[song_mid] = {
        "status": "queued",
        "song_name": song_name,
        "quality": "",
        "progress": 0,
        "error": None,
    }
    await _save_download_tasks()
    await song_queue.put((song_mid, song_name))
