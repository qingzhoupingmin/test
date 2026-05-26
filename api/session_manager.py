"""API 会话管理器 — 统一管理 requests.Session，支持登录态保持、重试、超时"""
from typing import Any, Dict, Optional

import requests
from loguru import logger


class SessionManager:
    """管理 HTTP 请求会话，支持：
    - 全局 cookie/header 保持
    - 自动重试（适配网络波动）
    - 连接池复用
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        retry: int = 0,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry = retry
        self.retry_delay = retry_delay
        self.session = requests.Session()

    def request(
        self,
        method: str,
        url: str,
        params: Dict[str, Any] = None,
        data: Any = None,
        json: Any = None,
        headers: Dict[str, str] = None,
        files: Dict[str, Any] = None,
        timeout: int = None,
        **kwargs,
    ) -> requests.Response:
        """发送 HTTP 请求，支持重试

        Args:
            method: GET/POST/PUT/DELETE/PATCH
            url: 请求路径（相对路径自动拼接 base_url）
            params: URL 查询参数
            data: 表单/原始数据
            json: JSON 请求体
            headers: 额外请求头
            files: 上传文件
            timeout: 超时时间（秒），覆盖默认值
        """
        # URL 拼接
        full_url = url
        if self.base_url and not url.startswith("http"):
            full_url = f"{self.base_url}{url}" if url.startswith("/") else f"{self.base_url}/{url}"

        # 合并 Headers
        merged_headers = {}
        if self.session.headers:
            merged_headers.update(self.session.headers)
        if headers:
            merged_headers.update(headers)

        _timeout = timeout or self.timeout

        # 重试逻辑
        last_exception = None
        max_attempts = self.retry + 1
        for attempt in range(max_attempts):
            try:
                response = self.session.request(
                    method=method,
                    url=full_url,
                    params=params,
                    data=data,
                    json=json,
                    headers=merged_headers,
                    files=files,
                    timeout=_timeout,
                    **kwargs,
                )
                logger.info("{} {} → {}", method, full_url, response.status_code)
                return response
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exception = e
                if attempt < self.retry:
                    logger.warning("请求失败，第 {}/{} 次重试... | {}", attempt + 1, self.retry, e)
                    import time
                    time.sleep(self.retry_delay)

        raise last_exception

    # 便捷方法
    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        return self.request("DELETE", url, **kwargs)

    def patch(self, url: str, **kwargs) -> requests.Response:
        return self.request("PATCH", url, **kwargs)

    def set_headers(self, headers: Dict[str, str]) -> None:
        """设置全局请求头"""
        self.session.headers.update(headers)

    def set_auth_token(self, token: str, scheme: str = "Bearer") -> None:
        """设置 Authorization 头"""
        self.session.headers["Authorization"] = f"{scheme} {token}"

    def close(self) -> None:
        self.session.close()
        logger.debug("API Session 已关闭")