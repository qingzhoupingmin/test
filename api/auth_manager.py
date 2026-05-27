"""鉴权抽象层 — 策略模式实现多认证方式"""

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from loguru import logger
from requests import Request


class AuthBase(ABC):
    """鉴权策略抽象基类，所有鉴权方式需继承此类"""

    @abstractmethod
    def apply(self, request: Request, context: Optional[Dict[str, Any]] = None) -> Request:
        """对请求对象应用鉴权，返回修改后的 Request"""
        ...


class NoAuth(AuthBase):
    """无鉴权"""
    def apply(self, request: Request, context=None) -> Request:
        return request


class BasicAuth(AuthBase):
    """HTTP Basic Authentication"""
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def apply(self, request: Request, context=None) -> Request:
        from requests.auth import HTTPBasicAuth
        request.auth = HTTPBasicAuth(self.username, self.password)
        return request


class BearerTokenAuth(AuthBase):
    """Bearer Token 认证（JWT 等）"""
    def __init__(self, token: str):
        self.token = token

    def apply(self, request: Request, context=None) -> Request:
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request


class HeaderAuth(AuthBase):
    """自定义 Header 鉴权（如 X-API-Key）"""
    def __init__(self, headers: Dict[str, str]):
        self.headers = headers

    def apply(self, request: Request, context=None) -> Request:
        request.headers.update(self.headers)
        return request


class SignatureAuth(AuthBase):
    """HMAC-SHA256 签名鉴权（常用于开放平台 API）"""
    def __init__(self, access_key: str, secret_key: str, sign_header: str = "X-Signature"):
        self.access_key = access_key
        self.secret_key = secret_key
        self.sign_header = sign_header

    def apply(self, request: Request, context=None) -> Request:
        timestamp = str(int(time.time()))
        nonce = hashlib.md5(timestamp.encode()).hexdigest()[:8]
        # 构造签名内容：method + path + timestamp + nonce + body
        body_str = ""
        if request.body:
            body_str = request.body.decode("utf-8") if isinstance(request.body, bytes) else str(request.body)
        sign_str = f"{request.method}&{request.path_url}&{timestamp}&{nonce}&{body_str}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        request.headers["X-Access-Key"] = self.access_key
        request.headers["X-Timestamp"] = timestamp
        request.headers["X-Nonce"] = nonce
        request.headers[self.sign_header] = signature
        return request


class OAuth2PasswordAuth(AuthBase):
    """OAuth2 密码模式 — 先请求 /token 端点获取 access_token"""
    def __init__(self, token_url: str, client_id: str, client_secret: str,
                 username: str, password: str, scope: str = ""):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.scope = scope
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def _fetch_token(self) -> str:
        import requests as req
        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
        }
        if self.scope:
            payload["scope"] = self.scope
        resp = req.post(self.token_url, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._expires_at = time.time() + data.get("expires_in", 3600) - 60  # 提前 60s 刷新
        self._token = data["access_token"]
        logger.info("OAuth2 token 获取成功，过期时间: {} 秒", data.get("expires_in", 3600))
        return self._token

    def apply(self, request: Request, context=None) -> Request:
        if self._token is None or time.time() > self._expires_at:
            self._fetch_token()
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request


class AuthManager:
    """鉴权管理器 — 根据配置创建鉴权策略并注入到 SessionManager

    用法:
        auth = AuthManager.create(config)
        session_manager.set_auth(auth)
    """

    @staticmethod
    def create(auth_config: Dict[str, Any]) -> AuthBase:
        """根据配置字典创建鉴权策略

        配置示例:
            # 无鉴权
            {"type": "none"}

            # Bearer Token
            {"type": "bearer", "token": "xxx"}

            # Basic Auth
            {"type": "basic", "username": "admin", "password": "123456"}

            # Header Auth
            {"type": "header", "headers": {"X-API-Key": "xxx"}}

            # HMAC 签名
            {"type": "signature", "access_key": "xxx", "secret_key": "xxx"}

            # OAuth2
            {"type": "oauth2", "token_url": "...", "client_id": "...",
             "client_secret": "...", "username": "...", "password": "..."}
        """
        auth_type = auth_config.get("type", "none").lower()

        if auth_type == "none":
            return NoAuth()

        elif auth_type == "basic":
            return BasicAuth(
                username=auth_config["username"],
                password=auth_config["password"],
            )

        elif auth_type == "bearer":
            return BearerTokenAuth(token=auth_config["token"])

        elif auth_type == "header":
            return HeaderAuth(headers=auth_config.get("headers", {}))

        elif auth_type == "signature":
            return SignatureAuth(
                access_key=auth_config["access_key"],
                secret_key=auth_config["secret_key"],
                sign_header=auth_config.get("sign_header", "X-Signature"),
            )

        elif auth_type == "oauth2":
            return OAuth2PasswordAuth(
                token_url=auth_config["token_url"],
                client_id=auth_config["client_id"],
                client_secret=auth_config["client_secret"],
                username=auth_config["username"],
                password=auth_config["password"],
                scope=auth_config.get("scope", ""),
            )

        else:
            logger.warning("未知鉴权类型: {}，回退为无鉴权", auth_type)
            return NoAuth()