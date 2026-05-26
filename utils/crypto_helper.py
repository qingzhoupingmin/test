"""加解密工具 — 基于 pycryptodome 的 AES 对称加密"""
import base64
import hashlib
from typing import Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class CryptoHelper:
    """AES 加解密工具，支持 CBC 模式"""

    DEFAULT_IV: bytes = b"0123456789abcdef"  # 16 字节 IV
    BLOCK_SIZE: int = AES.block_size  # 16

    @classmethod
    def _derive_key(cls, password: str) -> bytes:
        """将密码字符串派生为 32 字节 AES-256 密钥"""
        return hashlib.sha256(password.encode("utf-8")).digest()

    @classmethod
    def encrypt(cls, plain_text: str, password: str, iv: Optional[bytes] = None) -> str:
        """AES-CBC 加密，返回 Base64 字符串

        Args:
            plain_text: 明文
            password: 加密密码
            iv: 初始化向量，默认 DEFAULT_IV
        """
        key = cls._derive_key(password)
        _iv = iv or cls.DEFAULT_IV
        cipher = AES.new(key, AES.MODE_CBC, _iv)
        padded = pad(plain_text.encode("utf-8"), cls.BLOCK_SIZE)
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted).decode("utf-8")

    @classmethod
    def decrypt(cls, cipher_text: str, password: str, iv: Optional[bytes] = None) -> str:
        """AES-CBC 解密

        Args:
            cipher_text: Base64 密文
            password: 解密密码
            iv: 初始化向量，默认 DEFAULT_IV
        """
        key = cls._derive_key(password)
        _iv = iv or cls.DEFAULT_IV
        cipher = AES.new(key, AES.MODE_CBC, _iv)
        encrypted = base64.b64decode(cipher_text)
        decrypted = unpad(cipher.decrypt(encrypted), cls.BLOCK_SIZE)
        return decrypted.decode("utf-8")

    @classmethod
    def md5(cls, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    @classmethod
    def sha256(cls, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()