import os
import shutil
from datetime import datetime
from config.settings import DATABASE_PATH


def backup_database() -> str:
    """将 data/app.db 复制到 data/backups/ 目录下，文件名带时间戳。

    Returns:
        str: 备份文件的完整路径
    """
    src = DATABASE_PATH
    if not os.path.exists(src):
        raise FileNotFoundError(f"数据库文件不存在: {src}")

    backups_dir = os.path.join(os.path.dirname(src), "backups")
    os.makedirs(backups_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backups_dir, f"app_backup_{timestamp}.db")

    shutil.copy2(src, dst)
    return dst


def list_backups() -> list:
    """列出所有备份文件，按时间倒序。"""
    backups_dir = os.path.join(os.path.dirname(DATABASE_PATH), "backups")
    if not os.path.exists(backups_dir):
        return []
    files = []
    for f in os.listdir(backups_dir):
        if f.startswith("app_backup_") and f.endswith(".db"):
            full_path = os.path.join(backups_dir, f)
            size = os.path.getsize(full_path)
            mtime = os.path.getmtime(full_path)
            files.append({"filename": f, "path": full_path, "size": size, "mtime": mtime})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files
