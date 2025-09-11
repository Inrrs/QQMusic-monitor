import os
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.helpers import escape_markdown
from dotenv import load_dotenv
from functools import wraps
import io
import qrcode
import httpx

# 导入项目模块
import qq_music
import monitor

# 加载 .env 文件 (如果使用 .env 的话)
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
AUTHORIZED_USERS_STR = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(user_id.strip()) for user_id in AUTHORIZED_USERS_STR.split(',') if user_id.strip()]
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:6679")

# --- 授权装饰器 ---
def authorized_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text('抱歉，你没有权限使用此机器人。')
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- 命令列表 ---
bot_commands = [
    BotCommand("status", "查看QQ音乐登录状态"),
    BotCommand("login", "获取登录二维码"),
    BotCommand("monitor", "以交互方式管理歌单监控"),
    BotCommand("listmonitors", "查看监控列表"),
    BotCommand("downloading", "查看下载中任务"),
    BotCommand("completed", "查看已完成任务"),
    BotCommand("help", "获取帮助信息")
]

# --- 命令处理函数 ---

@authorized_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """发送欢迎消息和命令列表"""
    help_text = (
        "你好！我是QQ音乐下载机器人。\n\n"
        "可用命令:\n"
        "/status - 查看QQ音乐登录状态。\n"
        "/login - 获取登录二维码以登录QQ音乐。\n"
        "/monitor - 以交互方式管理歌单监控。\n"
        "/listmonitors - 查看正在监控的歌单列表。\n"
        "/downloading - 查看正在下载和排队的任务。\n"
        "/completed - 查看已完成的下载任务。\n"
        "/help - 显示此帮助信息。"
    )
    await update.message.reply_text(help_text)

@authorized_only
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """检查并回复QQ音乐的登录状态"""
    await qq_music.auth_completed.wait()
    if qq_music.is_login_valid():
        await update.message.reply_text('✅ QQ音乐已登录。')
    else:
        await update.message.reply_text('❌ QQ音乐未登录或登录已失效。请使用 /login 命令登录。')

@authorized_only
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """生成并发送QQ音乐登录二维码"""
    try:
        # get_login_qrcode() 直接返回二维码图片的 bytes 数据
        qr_image_data = await qq_music.get_login_qrcode()
        
        # 将 bytes 数据放入 BytesIO 对象中以便发送
        bio = io.BytesIO(qr_image_data)
        bio.seek(0)
        
        await update.message.reply_photo(
            photo=bio, 
            caption="请使用QQ扫描二维码登录。二维码将在2分钟后失效。"
        )
        
        # 启动轮询检查登录状态
        context.job_queue.run_once(
            check_login_callback, 
            5, 
            data={'chat_id': update.effective_chat.id}, 
            name=f"login_check_{update.effective_chat.id}"
        )
    except Exception as e:
        await update.message.reply_text(f"获取登录二维码失败: {e}")

async def check_login_callback(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    try:
        status_result = await qq_music.check_login_status()
        if status_result.get("is_success"):
            await context.bot.send_message(chat_id, "✅ 登录成功！")
            return
        status_name = status_result.get("status", "unknown")
        if status_name in ["timeout", "refuse"]:
            await context.bot.send_message(chat_id, f"登录失败: {status_result.get('message')}")
            return
        context.job_queue.run_once(check_login_callback, 5, data={'chat_id': chat_id}, name=f"login_check_{chat_id}")
    except Exception as e:
        await context.bot.send_message(chat_id, f"检查登录状态时出错: {e}")

@authorized_only
async def monitor_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """以交互方式显示用户歌单列表以进行监控"""
    if not qq_music.is_login_valid():
        await update.message.reply_text('❌ QQ音乐未登录或登录已失效。请使用 /login 命令登录。')
        return
    try:
        await update.message.reply_text("正在获取您的歌单列表，请稍候...")
        cred = qq_music.get_credential()
        playlists = await qq_music.get_user_playlists(cred.musicid)
        if not playlists:
            await update.message.reply_text("无法找到您的任何歌单。")
            return

        monitored_ids = await monitor.get_monitored_playlist_ids()
        keyboard = []
        for pl in playlists:
            dissid = str(pl.get('dissid'))
            title = pl.get('title', '未知歌单')
            is_monitored = dissid in monitored_ids
            
            button_text = f"{'✅' if is_monitored else '☑️'} {title}"
            callback_data = f"monitor_toggle_{dissid}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('请选择要监控或取消监控的歌单:', reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"获取歌单列表失败: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理内联键盘按钮点击"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("monitor_toggle_"):
        playlist_id = data.split("_")[-1]
        try:
            await monitor.toggle_monitoring(playlist_id)
            cred = qq_music.get_credential()
            playlists = await qq_music.get_user_playlists(cred.musicid)
            monitored_ids = await monitor.get_monitored_playlist_ids()
            keyboard = []
            for pl in playlists:
                dissid = str(pl.get('dissid'))
                title = pl.get('title', '未知歌单')
                is_monitored_now = dissid in monitored_ids
                button_text = f"{'✅' if is_monitored_now else '☑️'} {title}"
                callback_data = f"monitor_toggle_{dissid}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text="操作成功！\n请选择要监控或取消监控的歌单:", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(text=f"操作失败: {e}")


@authorized_only
async def list_monitors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    monitored_ids = await monitor.get_monitored_playlist_ids()
    if not monitored_ids:
        await update.message.reply_text("目前没有正在监控的歌单。")
        return
    
    # Escape playlist IDs for MarkdownV2
    escaped_ids = [escape_markdown(pid, version=2) for pid in monitored_ids]
    # Note: The '-' in a list needs to be escaped with a preceding '\'
    message = "正在监控的歌单ID:\n" + "\n".join(f"\\- `{pid}`" for pid in escaped_ids)
    
    try:
        await update.message.reply_text(message, parse_mode='MarkdownV2')
    except Exception as e:
        # Fallback to plain text if MarkdownV2 fails for any reason
        print(f"MarkdownV2 parsing failed: {e}. Sending as plain text.")
        plain_message = "正在监控的歌单ID:\n" + "\n".join(f"- {pid}" for pid in monitored_ids)
        await update.message.reply_text(plain_message)

async def get_tasks_from_api():
    """通过API从主应用获取任务状态"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/api/download/status")
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        print(f"无法连接到主应用API: {e}")
        return None

@authorized_only
async def downloading_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    download_tasks = await get_tasks_from_api()
    if download_tasks is None:
        await update.message.reply_text("无法获取任务列表，请确保主应用正在运行。")
        return

    active_tasks = {mid: task for mid, task in download_tasks.items() if task.get('status') in ['downloading', 'queued']}
    if not active_tasks:
        await update.message.reply_text("当前没有正在下载或排队的任务。")
        return
    
    message = "正在进行中的任务:\n\n"
    # Sort tasks to show downloading ones first, then by original order
    sorted_tasks = sorted(active_tasks.items(), key=lambda item: (item[1].get('status') != 'downloading', list(download_tasks.keys()).index(item[0])))

    for mid, task in sorted_tasks:
        status_icon = "⬇️" if task.get('status') == 'downloading' else "🕒"
        # Escape parentheses for MarkdownV2
        progress = f"\\({task.get('progress', 0)}%\\)" if task.get('status') == 'downloading' else ""
        song_name = escape_markdown(task.get('song_name', '未知歌曲'), version=2)
        message += f"{status_icon} {song_name} {progress}\n"
        
    await update.message.reply_text(message, parse_mode='MarkdownV2')

@authorized_only
async def completed_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    download_tasks = await get_tasks_from_api()
    if download_tasks is None:
        await update.message.reply_text("无法获取任务列表，请确保主应用正在运行。")
        return

    completed_tasks = {mid: task for mid, task in download_tasks.items() if task.get('status') == 'completed'}
    if not completed_tasks:
        await update.message.reply_text("还没有已完成的下载任务。")
        return
        
    # Sort by original insertion order (approximated by key order), descending
    sorted_tasks = sorted(completed_tasks.items(), key=lambda item: list(download_tasks.keys()).index(item[0]), reverse=True)[:20]
    
    message = "最近完成的下载:\n\n"
    for mid, task in sorted_tasks:
        song_name = escape_markdown(task.get('song_name', '未知歌曲'), version=2)
        quality = escape_markdown(task.get('quality', ''), version=2)
        message += f"✅ {song_name} \\- {quality}\n"
        
    await update.message.reply_text(message, parse_mode='MarkdownV2')

async def post_init(application: ApplicationBuilder):
    """在应用启动后设置机器人命令并初始化QQ音乐登录"""
    print("正在初始化 QQ 音乐登录状态...")
    await qq_music.initialize_from_cookie()
    print("设置机器人命令...")
    await application.bot.set_my_commands(bot_commands)

    # 向所有授权用户发送启动消息
    if AUTHORIZED_USERS:
        help_text = (
            "机器人已启动/重启。\n\n"
            "可用命令:\n"
            "/status - 查看QQ音乐登录状态。\n"
            "/login - 获取登录二维码以登录QQ音乐。\n"
            "/monitor - 以交互方式管理歌单监控。\n"
            "/listmonitors - 查看正在监控的歌单列表。\n"
            "/downloading - 查看正在下载和排队的任务。\n"
            "/completed - 查看已完成的下载任务。\n"
            "/help - 显示此帮助信息。"
        )
        for user_id in AUTHORIZED_USERS:
            try:
                await application.bot.send_message(chat_id=user_id, text=help_text)
                print(f"已向用户 {user_id} 发送启动消息。")
            except Exception as e:
                print(f"向用户 {user_id} 发送启动消息失败: {e}")

# --- 主程序 ---
def run_bot():
    if not TELEGRAM_TOKEN:
        print("错误：未找到 TELEGRAM_TOKEN。")
        return
    
    builder = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init)
    
    if PROXY_URL:
        builder.proxy_url(PROXY_URL)

    application = builder.build()

    # 添加命令处理程序
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("monitor", monitor_command_handler))
    application.add_handler(CommandHandler("listmonitors", list_monitors))
    application.add_handler(CommandHandler("downloading", downloading_list))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("completed", completed_list))

    print("Telegram Bot 已启动...")
    application.run_polling()

if __name__ == '__main__':
    run_bot()
