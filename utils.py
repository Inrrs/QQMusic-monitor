import os
import json
import httpx
from qqmusic_api import login
from qqmusic_api.utils.credential import Credential

# --- Define the data directory and the path for the credentials file ---
DATA_DIR = "data"
CREDENTIALS_FILE_PATH = os.path.join(DATA_DIR, "qq_cookie.json")

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

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
