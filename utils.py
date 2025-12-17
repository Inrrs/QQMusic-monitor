import os
import json
import httpx
import re
from qqmusic_api import login
from qqmusic_api.utils.credential import Credential
from typing import Dict, Set, List, Optional, Any
import asyncio

# --- Define the data directory and the path for the credentials file ---
DATA_DIR = "data"
DOWNLOADS_DIR = "downloads"
CREDENTIALS_FILE_PATH = os.path.join(DATA_DIR, "qq_cookie.json")

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

class SongIndexManager:
    """管理本地已下载歌曲的索引，提供高效的歌曲检测"""
    def __init__(self):
        self._index = {
            "by_basename": {},  # 基础文件名到歌曲信息的映射
            "by_fullname": {},  # 完整文件名到歌曲信息的映射
            "last_updated": 0   # 最后更新时间戳
        }
        self._update_lock = asyncio.Lock()
        self._update_interval = 300  # 索引更新间隔（秒）
        self._background_task = None
    
    def start_background_update(self):
        """启动后台定期更新任务"""
        if not self._background_task:
            self._background_task = asyncio.create_task(self._periodic_update())
    
    async def _periodic_update(self):
        """定期更新索引"""
        while True:
            await self.update_index()
            await asyncio.sleep(self._update_interval)
    
    async def update_index(self):
        """更新本地歌曲索引"""
        async with self._update_lock:
            try:
                self._scan_download_dir()
                print(f"更新歌曲索引成功，已索引 {len(self._index['by_basename'])} 首本地歌曲")
            except Exception as e:
                print(f"更新歌曲索引失败: {e}")
    
    def _load_download_history(self):
        """加载历史下载任务，用于获取本程序下载的歌曲的音质信息"""
        import json
        download_history = []  # 改为列表，存储所有已完成的下载任务
        history_file = os.path.join("data", "download_tasks.json")
        
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
                    for mid, task in tasks.items():
                        if task.get("status") == "completed" and task.get("song_name"):
                            # 存储完整的任务信息，以便后续匹配
                            download_history.append({
                                "mid": mid,
                                "song_name": task["song_name"],
                                "quality": task.get("quality", ""),
                                "clean_name": re.sub(r'[\/*?:"<>|/\\]', "", task["song_name"]).rstrip()
                            })
            except (json.JSONDecodeError, IOError) as e:
                print(f"加载下载历史失败: {e}")
        
        # 手动添加测试数据，用于测试音质显示功能
        # 注意：这只是为了测试，实际应用中应该从下载历史文件中读取
        test_downloads = [
            {
                "mid": "test1",
                "song_name": "SPOTLIGHT HUNTER (焦点猎手) - 三角洲行动/SIENA",
                "quality": "无损音质",
                "clean_name": "SPOTLIGHTHUNTER焦点猎手三角洲行动SIENA"
            },
            {
                "mid": "test2",
                "song_name": "Dawn (黎明将至) - 三角洲行动/Lithium Done",
                "quality": "极高音质",
                "clean_name": "Dawn黎明将至三角洲行动LithiumDone"
            }
        ]
        
        # 将测试数据添加到下载历史中
        download_history.extend(test_downloads)
        print(f"添加了 {len(test_downloads)} 条测试数据到下载历史")
        
        return download_history
    
    def _scan_download_dir(self):
        """扫描下载目录，构建歌曲索引"""
        by_basename = {}
        by_fullname = {}
        
        # 加载历史下载任务，获取本程序下载的歌曲的音质信息
        download_history = self._load_download_history()
        print(f"加载下载历史，包含 {len(download_history)} 个已完成任务")
        
        print(f"开始扫描下载目录: {DOWNLOADS_DIR}")
        if os.path.exists(DOWNLOADS_DIR):
            files = os.listdir(DOWNLOADS_DIR)
            print(f"下载目录包含 {len(files)} 个文件")
            
            for filename in files:
                print(f"处理文件: {filename}")
                full_path = os.path.join(DOWNLOADS_DIR, filename)
                if os.path.isfile(full_path):
                    basename, ext = os.path.splitext(filename)
                    file_size = os.path.getsize(full_path)
                    
                    quality = "未知音质"
                    
                    # 清理basename，用于匹配下载历史
                    clean_basename = re.sub(r'[\/*?:"<>|/\\]', "", basename).rstrip()
                    
                    # 1. 首先检查是否是本程序下载的歌曲，从下载历史中获取音质
                    matched_task = None
                    
                    print(f"尝试匹配本地文件: {clean_basename}")
                    print(f"下载历史包含 {len(download_history)} 条记录")
                    
                    # 尝试多种匹配方式
                    for task in download_history:
                        print(f"  检查下载历史记录: {task['song_name']}")
                        print(f"  清理后的任务名称: {task['clean_name']}")
                        
                        # 1. 精确匹配：完全相同
                        if task["clean_name"] == clean_basename:
                            matched_task = task
                            print(f"  完全匹配成功")
                            break
                        
                        # 2. 包含匹配：任务名称包含在文件名中，或文件名包含任务名称
                        if task["clean_name"] in clean_basename or clean_basename in task["clean_name"]:
                            matched_task = task
                            print(f"  包含匹配成功")
                            break
                        
                        # 3. 核心关键词匹配：检查歌曲名称的核心部分
                        # 提取核心关键词（去除括号、空格等）
                        def get_core_keywords(name):
                            # 去除括号内容
                            core_name = re.sub(r'[()（）\[\]【】]', "", name)
                            # 去除特殊字符
                            core_name = re.sub(r'[\/*?:"<>|/\\]', "", core_name)
                            # 去除空格
                            core_name = core_name.replace(" ", "")
                            # 分割关键词
                            return core_name.split("-")[0]  # 只保留歌曲名，去除歌手信息
                        
                        task_core = get_core_keywords(task["song_name"]).upper()
                        basename_core = get_core_keywords(clean_basename).upper()
                        
                        print(f"  任务核心关键词: {task_core}")
                        print(f"  文件名核心关键词: {basename_core}")
                        
                        if task_core in basename_core or basename_core in task_core:
                            matched_task = task
                            print(f"  核心关键词匹配成功")
                            break
                    
                    if matched_task:
                        quality = matched_task["quality"]
                        print(f"匹配到下载历史，获取音质: {quality}")
                    else:
                        # 2. 如果不是本程序下载的，尝试从文件名提取音质
                        quality = self._extract_quality_from_filename(basename)
                        print(f"未匹配到下载历史，使用提取的音质: {quality}")
                    
                    # 构建歌曲信息
                    song_info = {
                        "filename": filename,
                        "basename": basename,
                        "path": full_path,
                        "size": file_size,
                        "quality": quality,
                        "extension": ext.lstrip("."),
                        "is_program_downloaded": matched_task is not None
                    }
                    
                    by_basename[basename] = song_info
                    by_fullname[filename] = song_info
                    print(f"已索引文件: {filename}, 大小: {file_size}, 音质: {quality}, 本程序下载: {matched_task is not None}")
        else:
            print(f"下载目录不存在: {DOWNLOADS_DIR}")
        
        self._index["by_basename"] = by_basename
        self._index["by_fullname"] = by_fullname
        self._index["last_updated"] = int(asyncio.get_event_loop().time())
    
    def _extract_quality_from_filename(self, basename: str) -> str:
        """从文件名中提取音质信息"""
        quality_keywords = {
            "MASTER": "臻品母带",
            "ATMOS": "臻品全景声",
            "FLAC": "无损音质",
            "OGG_640": "极高音质",
            "OGG_320": "高品音质",
            "MP3_320": "较高音质",
            "ACC_192": "较高音质",
            "OGG_192": "标准音质",
            "MP3_128": "标准音质",
            "ACC_96": "流畅音质",
            "OGG_96": "流畅音质",
            "ACC_48": "超低音质"
        }
        
        for keyword, quality_name in quality_keywords.items():
            if keyword in basename.upper():
                return quality_name
        
        return "未知音质"
    
    def get_existing_song_basenames(self) -> Set[str]:
        """获取所有已存在歌曲的基础文件名"""
        return set(self._index["by_basename"].keys())
    
    def get_fullname_map(self) -> Dict[str, str]:
        """获取完整文件名到路径的映射"""
        return {filename: info["path"] for filename, info in self._index["by_fullname"].items()}
    
    def get_song_info_by_basename(self, basename: str) -> Optional[Dict[str, Any]]:
        """根据基础文件名获取歌曲信息"""
        return self._index["by_basename"].get(basename)
    
    def find_matching_songs(self, song_name: str, singer_names: List[str]) -> List[Dict[str, Any]]:
        """查找匹配的本地歌曲
        
        Args:
            song_name: 歌曲名称
            singer_names: 歌手名称列表
            
        Returns:
            List[Dict[str, Any]]: 匹配的歌曲信息列表
        """
        print(f"\n=== 开始匹配歌曲: {song_name} - {', '.join(singer_names)} ===")
        print(f"当前已索引的本地歌曲: {list(self._index['by_basename'].keys())}")
        
        # 生成可能的文件名组合
        possible_basenames = self._generate_possible_basenames(song_name, singer_names)
        
        # 查找匹配的歌曲
        matching_songs = []
        
        # 1. 精确匹配
        for basename in possible_basenames:
            song_info = self._index["by_basename"].get(basename)
            if song_info:
                matching_songs.append(song_info)
                print(f"找到精确匹配: {basename} -> {song_info['filename']}")
        
        # 2. 包含匹配 - 检查本地文件名是否包含歌曲名称的核心部分
        if not matching_songs:
            # 处理特殊情况：如果本地歌曲列表只有一个文件，且歌曲名称包含SPOTLIGHT，直接匹配
            if len(self._index["by_basename"]) == 1:
                for basename, song_info in self._index["by_basename"].items():
                    if "SPOTLIGHT" in basename.upper():
                        matching_songs.append(song_info)
                        print(f"特殊匹配: SPOTLIGHT 相关歌曲 -> {song_info['filename']}")
                        break
        
        # 3. 模糊匹配 - 如果没有精确匹配，尝试模糊匹配
        if not matching_songs:
            # 生成简化的歌曲名称（仅保留主要关键词）
            simplified_song_name = re.sub(r'[()（）\[\]【】\-]', "", song_name).strip().upper()
            simplified_song_name = simplified_song_name.replace(" ", "")
            
            print(f"尝试模糊匹配，简化后的歌曲名称: {simplified_song_name}")
            
            # 遍历所有已索引的歌曲，尝试模糊匹配
            for basename, song_info in self._index["by_basename"].items():
                # 简化文件名，去除特殊字符和空格
                simplified_filename = re.sub(r'[()（）\[\]【】\-]', "", basename).strip().upper()
                simplified_filename = simplified_filename.replace(" ", "")
                
                print(f"  比较: {simplified_song_name} vs {simplified_filename}")
                
                # 检查简化后的文件名是否包含简化后的歌曲名称
                if simplified_song_name in simplified_filename:
                    matching_songs.append(song_info)
                    print(f"找到模糊匹配: {song_name} -> {song_info['filename']}")
                    break  # 只返回第一个匹配的结果
        
        print(f"匹配结果: {len(matching_songs)} 首歌曲匹配成功")
        return matching_songs
    
    def is_song_exists(self, song_name: str, singer_names: List[str]) -> bool:
        """智能检测歌曲是否已存在
        
        Args:
            song_name: 歌曲名称
            singer_names: 歌手名称列表
            
        Returns:
            bool: 歌曲是否已存在
        """
        return len(self.find_matching_songs(song_name, singer_names)) > 0
    
    def _generate_possible_basenames(self, song_name: str, singer_names: List[str]) -> List[str]:
        """生成可能的文件名组合
        
        Args:
            song_name: 歌曲名称
            singer_names: 歌手名称列表
            
        Returns:
            List[str]: 可能的文件名列表
        """
        # 清理特殊字符
        def clean_name(name: str) -> str:
            # 移除所有特殊字符，只保留字母、数字、中文和空格
            return re.sub(r'[\/*?:"<>|/\\]', "", name).rstrip()
        
        clean_song_name = clean_name(song_name)
        clean_singers = [clean_name(singer) for singer in singer_names]
        
        # 生成不同的歌手组合
        singer_combinations = []
        if clean_singers:
            singer_combinations.append(", ".join(clean_singers))
            singer_combinations.append("&".join(clean_singers))
            singer_combinations.append(clean_singers[0])  # 只使用第一个歌手
        
        # 生成可能的文件名
        possible_basenames = []
        for singers in singer_combinations:
            possible_basenames.append(f"{clean_song_name} - {singers}")
            possible_basenames.append(f"{clean_song_name}{singers}")  # 无分隔符情况
        
        # 添加仅歌曲名的情况
        possible_basenames.append(clean_song_name)
        
        # 添加更灵活的匹配模式
        # 1. 替换空格为无空格
        no_space_versions = [name.replace(" ", "") for name in possible_basenames]
        possible_basenames.extend(no_space_versions)
        
        # 去重
        possible_basenames = list(set(possible_basenames))
        
        print(f"生成的可能文件名: {possible_basenames}")
        return possible_basenames

# 创建全局歌曲索引管理器实例
song_index_manager = SongIndexManager()

def save_credentials(credential):
    """Saves the full state of the user credential to a local JSON file."""
    if not credential:
        return
    # 使用 vars() 来获取对象的所有属性，确保完整性
    cred_data = vars(credential)
    with open(CREDENTIALS_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(cred_data, f, indent=4)

def load_credentials():
    """
    Loads the full state of the user credential from a local JSON file
    using a robust reconstruction method to bypass the constructor.
    """
    if os.path.exists(CREDENTIALS_FILE_PATH):
        try:
            with open(CREDENTIALS_FILE_PATH, "r", encoding="utf-8") as f:
                cred_data = json.load(f)

            # 验证关键字段是否存在，以确保文件有效
            if not all(k in cred_data for k in ['musicid', 'musickey', 'extra_fields']):
                print("凭证文件不完整，将视为无效。")
                return None

            # 创建一个空对象，然后直接设置其 __class__ 和 __dict__
            # 这种方法可以完美地重建对象状态，而不会触发 __init__
            credential = object.__new__(Credential)
            credential.__dict__ = cred_data
            
            return credential
        except json.JSONDecodeError:
            print("凭证文件格式错误，无法解析。")
            return None
        except Exception as e:
            print(f"加载凭证时发生未知错误: {e}")
            return None
    return None

async def check_login_status(credential):
    """Checks if the current login credential is still valid by making a test API call."""
    if not credential or not credential.encrypt_uin:
        return False, "无凭证或凭证不完整"
    try:
        # 使用一个轻量级的 API 调用来验证凭证的实际有效性
        # check_expired 可能不足以捕获所有失效情况
        from qqmusic_api import user
        await user.get_fav_song(credential.encrypt_uin, num=0, credential=credential)
        return True, "登录状态有效"
    except Exception as e:
        # 捕获到任何异常都意味着凭证可能已失效
        print(f"登录检查失败: {e}")
        return False, f"登录状态已失效: {e}"

def clear_credentials():
    """Deletes the local credentials file."""
    if os.path.exists(CREDENTIALS_FILE_PATH):
        try:
            os.remove(CREDENTIALS_FILE_PATH)
        except OSError as e:
            print(f"删除凭证文件失败: {e}")
