import asyncio
import os
import random
import sys
import json
from typing import Optional
import httpx

from qqmusic_api import login, user, song, songlist
from qqmusic_api.login import QR, QRLoginType, QRCodeLoginEvents
from qqmusic_api.song import SongFileType
from qqmusic_api.utils.credential import Credential
from qqmusic_api.utils.qimei import get_qimei
from qqmusic_api.utils.session import Session, set_session
from utils import load_credentials, save_credentials, check_login_status as check_credential_status

# --- 全局状态和会话 ---
login_qr: Optional[QR] = None
auth_completed = asyncio.Event()

# 创建一个全局的、可复用的 Session 实例
# 我们将在应用启动时初始化它，在关闭时销毁它
global_session: Optional[Session] = None

def get_credential() -> Optional[Credential]:
    """从文件加载凭证，这是唯一可靠的状态来源"""
    return load_credentials()

def is_login_valid() -> bool:
    """检查登录是否有效"""
    cred = get_credential()
    return cred is not None and cred.encrypt_uin is not None

def initialize_qqmusic_session(cred: Optional[Credential] = None):
    """
    创建并设置全局的 qqmusic-api 会话。
    如果提供了凭证对象，则直接使用它；否则，从文件加载。
    """
    global global_session
    credential = cred if cred else get_credential()
    
    # 始终创建一个新的会话实例
    global_session = Session(timeout=30, credential=credential)
    
    # 强制使用更新的客户端版本，因为库的默认版本可能已被服务器阻止
    new_version = "19.5.0.0"
    new_version_code = 19050000
    global_session.api_config["version"] = new_version
    global_session.api_config["version_code"] = new_version_code

    # 检查凭证中是否已有 qimei，以确保在整个应用生命周期中的一致性
    if credential and hasattr(credential, 'qimei') and credential.qimei:
        # 如果存在，则使用持久化的 qimei
        global_session.qimei = credential.qimei
        print(f"已设置 API 版本 {new_version} 并应用持久化的 qimei: {credential.qimei}")
    else:
        # 如果不存在（例如首次运行或新的登录），则生成一个新的 qimei
        new_qimei = get_qimei(new_version)["q36"]
        global_session.qimei = new_qimei
        print(f"已设置 API 版本 {new_version} 并生成新的 qimei: {new_qimei}")
        # 将新生成的 qimei 附加到凭证对象上，以便可以保存
        if credential:
            credential.qimei = new_qimei
            
    set_session(global_session)

async def close_qqmusic_session():
    """关闭全局会话"""
    global global_session
    if global_session:
        await global_session.aclose()
        global_session = None

# --- 音质配置 ---
QUALITY_MAP = {
    SongFileType.MASTER: (".flac", "臻品母带"),
    SongFileType.ATMOS_51: (".flac", "臻品全景声 (5.1)"),
    SongFileType.ATMOS_2: (".flac", "臻品全景声 (Stereo)"),
    SongFileType.FLAC: (".flac", "无损音质"),
    SongFileType.OGG_640: (".ogg", "极高音质"),
    SongFileType.OGG_320: (".ogg", "高品音质"),
    SongFileType.MP3_320: (".mp3", "较高音质"),
    SongFileType.ACC_192: (".m4a", "较高音质"),
    SongFileType.OGG_192: (".ogg", "标准音质"),
    SongFileType.MP3_128: (".mp3", "标准音质"),
    SongFileType.ACC_96: (".m4a", "流畅音质"),
    SongFileType.OGG_96: (".ogg", "流畅音质"),
    SongFileType.ACC_48: (".m4a", "超低音质"),
}
QUALITY_ORDER = list(QUALITY_MAP.keys())

# --- 核心函数 ---

async def initialize_from_cookie():
    """从 cookie 文件加载并验证凭证，并设置认证完成事件"""
    try:
        cred = get_credential()
        initialize_qqmusic_session(cred)  # 使用加载的凭证初始化
        if cred:
            print("已从文件加载凭证，正在验证有效性...")
            is_valid, message = await check_credential_status(cred)
            if is_valid:
                print(message)
                try:
                    print("凭证有效，尝试刷新 Cookie 以确保会话最新...")
                    await login.refresh_cookies(cred)
                    # The new qimei has already been attached to cred and will be saved here.
                    save_credentials(cred)
                    # Re-initializing the session here is not only unnecessary but also creates
                    # an inconsistent qimei state. The existing global_session is fine.
                    print("Cookie 刷新成功。")
                except Exception as e:
                    print(f"刷新 Cookie 失败: {e}。将继续使用现有凭证，但这可能导致认证问题。")

                if not cred.encrypt_uin:
                    try:
                        cred.encrypt_uin = await user.get_euin(cred.musicid)
                        save_credentials(cred)
                        # Session does not need to be re-initialized here either. The cred object
                        # is shared with the existing session.
                    except Exception as e:
                        print(f"从 cookie 初始化时获取 euin 失败: {e}")
                        if os.path.exists("qq_cookie.json"):
                            os.remove("qq_cookie.json")
                        initialize_qqmusic_session()
            else:
                print(message)
                if os.path.exists("qq_cookie.json"):
                    os.remove("qq_cookie.json")
                initialize_qqmusic_session()
        else:
            print("未找到本地凭证文件。")
    except Exception as e:
        print(f"初始化凭证时发生错误: {e}")
    finally:
        auth_completed.set()

async def get_login_qrcode():
    """获取登录二维码"""
    global login_qr
    initialize_qqmusic_session() # 确保会话存在
    login_qr = await login.get_qrcode(QRLoginType.QQ)
    return login_qr.data

async def check_login_status():
    """检查二维码扫描状态"""
    if not login_qr:
        return {"status": "error", "message": "请先获取二维码"}

    event, cred = await login.check_qrcode(login_qr)
    is_success = event == QRCodeLoginEvents.DONE and cred is not None

    if is_success:
        try:
            if not cred.encrypt_uin:
                # 必须先设置一个临时的 session 来获取 euin
                with set_session(Session(credential=cred)):
                    cred.encrypt_uin = await user.get_euin(cred.musicid)
            
            # 在保存凭证之前，将会话中的 qimei 附加到凭证对象上
            if global_session and hasattr(global_session, 'qimei'):
                cred.qimei = global_session.qimei
            
            save_credentials(cred)
            # 使用新鲜的、包含完整内存状态的凭证对象来重新初始化会话
            initialize_qqmusic_session(cred)
            print("登录成功，凭证已保存。")
        except Exception as e:
            print(f"关键步骤获取 euin 失败: {e}。登录被视为无效。")
            is_success = False
            if os.path.exists("qq_cookie.json"):
                os.remove("qq_cookie.json")
            initialize_qqmusic_session() # 清除无效凭证

    message_map = {
        QRCodeLoginEvents.SCAN: "等待扫描二维码",
        QRCodeLoginEvents.CONF: "已扫码，请在手机上确认登录",
        QRCodeLoginEvents.TIMEOUT: "二维码已过期",
        QRCodeLoginEvents.DONE: "登录成功",
        QRCodeLoginEvents.REFUSE: "您已拒绝登录",
    }

    return {
        "status": event.name.lower(),
        "message": message_map.get(event, "未知状态"),
        "is_success": is_success,
    }

async def get_user_playlists(user_id: int):
    """获取用户所有歌单，包括自建和收藏的"""
    cred = get_credential()
    if not cred or not cred.encrypt_uin:
        raise ValueError("用户未登录或凭证无效")
    
    euin = cred.encrypt_uin
    homepage_data = await user.get_homepage(euin, credential=cred)
    fav_song_data = await user.get_fav_song(euin, num=1, credential=cred)
    fav_songlists_data = await user.get_fav_songlist(euin, num=100, credential=cred)

    created_songlists = []
    if homepage_data:
        intro_tab_list = homepage_data.get('TabDetail', {}).get('IntroductionTab', {}).get('List', [])
        for item in intro_tab_list:
            if item.get('ItemType') == 10 and item.get('DissList'):
                for group in item.get('DissList', []):
                    if 'list' in group and isinstance(group['list'], list):
                        created_songlists.extend(group['list'])
                break
        
    favorite_songlists = fav_songlists_data.get('v_list', [])
    total_fav_songs = fav_song_data.get('total_song_num', 0)
    my_favorites_playlist = {
        "dissid": "201",
        "title": "我喜欢",
        "subtitle": f"{total_fav_songs}首",
        "picurl": "", 
        "dirid": 201
    }

    all_playlists = []
    my_favorites_playlist['type'] = 'favorite'
    all_playlists.append(my_favorites_playlist)

    for pl in created_songlists:
        pl['type'] = 'created'
        all_playlists.append(pl)

    for pl in favorite_songlists:
        transformed_pl = {
            'dissid': pl.get('tid'),
            'dirid': pl.get('dirId'),
            'picurl': pl.get('logo'),
            'title': pl.get('name'),
            'subtitle': f"{pl.get('songnum', 0)}首",
            'type': 'favorite'
        }
        all_playlists.append(transformed_pl)

    return all_playlists

async def search_song(keyword: str, page: int = 1, num: int = 10):
    """根据关键词搜索歌曲"""
    from qqmusic_api import search
    cred = get_credential()
    # 搜索可以不需要凭证
    result = await search.search_by_type(keyword, search.SearchType.SONG, page=page, num=num, credential=cred)
    return result

async def get_playlist_songs(playlist_id: int, no_cache: bool = False):
    """获取歌单中的歌曲，特殊处理'我喜欢'歌单"""
    cred = get_credential()
    if not cred:
        raise ValueError("用户未登录")
    
    if str(playlist_id) == "201":
        get_fav_song_req = user.get_fav_song.copy()
        if no_cache:
            get_fav_song_req.cacheable = False
        fav_song_data = await get_fav_song_req(
            cred.encrypt_uin, num=5000, credential=cred
        )
        return fav_song_data.get("songlist", [])
    else:
        get_detail_req = songlist.get_detail.copy()
        if no_cache:
            get_detail_req.cacheable = False
        songlist_detail = await get_detail_req(
            songlist_id=playlist_id, credential=cred
        )
        return songlist_detail.get("songlist", [])

async def get_song_download_url(song_mid: str):
    """按顺序获取最佳音质的歌曲下载URL"""
    cred = get_credential()
    if not cred:
        print("用户未登录或凭证无效，无法获取下载链接。")
        return None

    # The global_session should already be initialized, but this is a safeguard.
    if not global_session:
        initialize_qqmusic_session(cred)

    for quality_enum in QUALITY_ORDER:
        try:
            # 使用官方库函数，并传入凭证
            urls = await song.get_song_urls([song_mid], file_type=quality_enum, credential=cred)
            url = urls.get(song_mid)

            if url and url.startswith('http'):
                extension, quality_name = QUALITY_MAP[quality_enum]
                print(f"成功获取音质 {quality_name} 的链接。")
                return {
                    "url": url,
                    "quality": quality_name,
                    "extension": extension,
                    "enum_name": quality_enum.name,
                }
        except Exception as e:
            print(f"尝试获取音质 {quality_enum.name} 失败: {e}")
            continue
            
    print(f"未能获取歌曲 {song_mid} 的任何下载链接。")
    return None
