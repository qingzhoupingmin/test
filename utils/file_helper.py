"""文件处理工具 — 上传/下载辅助"""
import os
from pathlib import Path
from typing import Dict, List, Optional


class FileHelper:
    """文件处理辅助类，支持文件路径解析、MIME 类型推断等"""

    MIME_TYPES: Dict[str, str] = {
        ".txt": "text/plain",
        ".json": "application/json",
        ".xml": "application/xml",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".zip": "application/zip",
    }

    @classmethod
    def get_mime_type(cls, file_path: str) -> str:
        """根据文件扩展名推断 MIME 类型"""
        ext = Path(file_path).suffix.lower()
        return cls.MIME_TYPES.get(ext, "application/octet-stream")

    @classmethod
    def build_file_payload(cls, file_field: str, file_path: str) -> Dict[str, tuple]:
        """构建 requests 上传文件参数字典

        Args:
            file_field: 表单字段名
            file_path: 本地文件路径
        Returns:
            files 参数字典，如 {'file': ('report.xlsx', <bytes>, 'application/...')}
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        mime = cls.get_mime_type(file_path)
        return {file_field: (path.name, open(path, "rb"), mime)}

    @classmethod
    def resolve_path(cls, base_dir: str, relative_path: str) -> str:
        """将相对路径解析为绝对路径"""
        return str(Path(base_dir) / relative_path)

    @classmethod
    def find_files(cls, directory: str, pattern: str = "*.xlsx") -> List[str]:
        """递归查找目录下匹配模式的文件"""
        matches = list(Path(directory).rglob(pattern))
        return [str(m) for m in matches]

    @classmethod
    def ensure_dir(cls, path: str) -> str:
        """确保目录存在，返回目录路径"""
        Path(path).mkdir(parents=True, exist_ok=True)
        return path