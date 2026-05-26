"""数据库操作工具 — MySQL + Redis 连接与执行"""
from typing import Any, Dict, List, Optional

import pymysql
import redis
from loguru import logger


class MySQLHelper:
    """MySQL 连接与查询辅助类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._conn: Optional[pymysql.Connection] = None

    def connect(self) -> pymysql.Connection:
        if self._conn is None or not self._conn.open:
            self._conn = pymysql.connect(
                host=self.config.get("host", "localhost"),
                port=self.config.get("port", 3306),
                user=self.config.get("user", "root"),
                password=self.config.get("password", ""),
                database=self.config.get("database", ""),
                charset=self.config.get("charset", "utf8mb4"),
                cursorclass=pymysql.cursors.DictCursor,
            )
            logger.debug("MySQL 连接成功: {}", self.config.get("host"))
        return self._conn

    def execute(self, sql: str, params: tuple = None) -> int:
        """执行增删改，返回影响行数"""
        conn = self.connect()
        with conn.cursor() as cursor:
            rows = cursor.execute(sql, params)
            conn.commit()
            return rows

    def query_one(self, sql: str, params: tuple = None) -> Optional[Dict]:
        """查询单行"""
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def query_all(self, sql: str, params: tuple = None) -> List[Dict]:
        """查询多行"""
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def close(self) -> None:
        if self._conn and self._conn.open:
            self._conn.close()
            logger.debug("MySQL 连接已关闭")


class RedisHelper:
    """Redis 连接与操作辅助类"""

    def __init__(self, config: Dict[str, Any]):
        self._client: Optional[redis.Redis] = None
        self.config = config

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.get("host", "localhost"),
                port=self.config.get("port", 6379),
                password=self.config.get("password") or None,
                db=self.config.get("db", 0),
                decode_responses=self.config.get("decode_responses", True),
            )
            # 测试连接
            self._client.ping()
            logger.debug("Redis 连接成功: {}", self.config.get("host"))
        return self._client

    def set(self, key: str, value: str, ex: int = None) -> bool:
        return self.client.set(key, value, ex=ex)

    def get(self, key: str) -> Optional[str]:
        return self.client.get(key)

    def delete(self, *keys: str) -> int:
        return self.client.delete(*keys)

    def exists(self, key: str) -> bool:
        return self.client.exists(key) > 0

    def close(self) -> None:
        if self._client:
            self._client.close()
            logger.debug("Redis 连接已关闭")


class DBHelper:
    """统一数据库助手 — 封装 MySQL + Redis，conftest 通过此类注入"""

    def __init__(self, config: Dict[str, Any]):
        self.mysql_cfg = config.get("mysql", {})
        self.redis_cfg = config.get("redis", {})
        self._mysql: Optional[MySQLHelper] = None
        self._redis: Optional[RedisHelper] = None
        if self.mysql_cfg:
            self._mysql = MySQLHelper(self.mysql_cfg)
            self._mysql.connect()
            logger.info("DBHelper: MySQL 已连接")
        if self.redis_cfg:
            self._redis = RedisHelper(self.redis_cfg)
            # RedisHelper 构造时即 ping 验证
            logger.info("DBHelper: Redis 已连接")

    @property
    def mysql(self) -> Optional[MySQLHelper]:
        return self._mysql

    @property
    def redis(self) -> Optional[RedisHelper]:
        return self._redis

    def close(self) -> None:
        if self._mysql:
            self._mysql.close()
        if self._redis:
            self._redis.close()
        logger.info("DBHelper: 所有数据库连接已关闭")
