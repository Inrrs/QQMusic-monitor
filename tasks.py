import asyncio
import os

import aiofiles
import httpx
import orjson as json

import qq_music
from shared_state import download_tasks

# --- 配置 ---
DATA_DIR = "data"
TASKS_FILE = os.path.join(DATA_DIR, "download_tasks.json")
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 5))
RETRY_INTERVAL_SECONDS = int(os.getenv("RETRY_INTERVAL_SECONDS", 24 * 3600))  # 默认24小时

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
    """将当前下载任务列表保存到文件，并清理旧的失败/取消任务以防止内存泄漏"""
    MAX_HISTORY_SIZE = 500  # 保留最近的500个失败/取消的任务记录

    # 只筛选出失败或取消的任务进行清理
    non_active_mids = [
        mid
        for mid, task in download_tasks.items()
        if task.get("status") in ["failed", "cancelled"]
    ]

    # 如果非活动任务的数量超过了历史记录上限
    if len(non_active_mids) > MAX_HISTORY_SIZE:
        # 计算需要移除的旧任务数量
        num_to_remove = len(non_active_mids) - MAX_HISTORY_SIZE
        # 获取最旧的那些任务的 mid
        mids_to_remove = non_active_mids[:num_to_remove]

        print(f"失败/取消的任务历史超过 {MAX_HISTORY_SIZE}，正在清理 {len(mids_to_remove)} 条最旧的记录...")
        for mid in mids_to_remove:
            if mid in download_tasks:
                del download_tasks[mid]

    try:
        # 使用 orjson 进行高效的 JSON 序列化
        json_data = json.dumps(download_tasks, option=json.OPT_INDENT_2)
        async with aiofiles.open(TASKS_FILE, "wb") as f:
            await f.write(json_data)
    except IOError as e:
        print(f"错误：无法保存下载任务文件: {e}")

async def _execute_download(song_mid: str, song_name: str):
    """实际执行下载的核心逻辑"""
    print(f"开始下载: {song_name}")
    download_dir = os.path.join(DATA_DIR, "downloads")
    os.makedirs(download_dir, exist_ok=True)
    url_info = await qq_music.get_song_download_url(song_mid)

    if not (url_info and url_info.get("url")):
        download_tasks[song_mid].update(
            {"status": "failed", "error": "无法获取下载链接 (可能是API限制)"}
        )
        await _save_download_tasks()
        return

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
    except Exception as e:
        download_tasks[song_mid].update({"status": "failed", "error": str(e)})
        print(f"下载失败: {song_name}, 原因: {e}")

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
    """后台任务：定期重试所有失败的下载"""
    while True:
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        print("开始执行定时重试任务，检查失败的下载...")
        
        # 创建一个失败任务的副本以安全迭代
        failed_tasks = {
            mid: task
            for mid, task in download_tasks.items()
            if task.get("status") == "failed"
        }
        
        if not failed_tasks:
            print("没有发现失败的任务，跳过本次重试。")
            continue

        print(f"发现 {len(failed_tasks)} 个失败的任务，正在将它们重新加入队列...")
        for mid, task in failed_tasks.items():
            song_name = task.get("song_name", "未知歌曲")
            # 重新加入队列会自动更新任务状态
            await add_song_to_queue(mid, song_name)
        
        print("所有失败的任务已重新加入下载队列。")

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
