"""通知模块 — 多渠道测试结果通知（企业微信/钉钉/邮件）"""

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import requests
from loguru import logger


class BaseNotifier:
    """通知基类"""

    def send(self, title: str, content: str, **kwargs) -> bool:
        raise NotImplementedError


class WeComNotifier(BaseNotifier):
    """企业微信机器人通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title: str, content: str, **kwargs) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n{content}"
            }
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code == 200 and resp.json().get("errcode") == 0:
                logger.info("企业微信通知发送成功")
                return True
            logger.error("企业微信通知失败: {}", resp.text)
            return False
        except Exception as e:
            logger.error("企业微信通知异常: {}", e)
            return False


class DingTalkNotifier(BaseNotifier):
    """钉钉机器人通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title: str, content: str, **kwargs) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n{content}"
            }
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code == 200 and resp.json().get("errcode") == 0:
                logger.info("钉钉通知发送成功")
                return True
            logger.error("钉钉通知失败: {}", resp.text)
            return False
        except Exception as e:
            logger.error("钉钉通知异常: {}", e)
            return False


class EmailNotifier(BaseNotifier):
    """邮件通知"""

    def __init__(self, smtp_host: str, smtp_port: int, sender: str,
                 password: str, receivers: List[str], use_tls: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.receivers = receivers
        self.use_tls = use_tls

    def send(self, title: str, content: str, **kwargs) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = title
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.receivers)
            msg.attach(MIMEText(content, "html", "utf-8"))

            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            if self.use_tls:
                server.starttls()
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.receivers, msg.as_string())
            server.quit()
            logger.info("邮件通知发送成功")
            return True
        except Exception as e:
            logger.error("邮件通知异常: {}", e)
            return False


class Notifier:
    """通知管理器 — 统一调度多渠道通知"""

    def __init__(self):
        self._channels: Dict[str, BaseNotifier] = {}

    def register(self, name: str, notifier: BaseNotifier) -> None:
        self._channels[name] = notifier

    def send_all(self, title: str, content: str) -> Dict[str, bool]:
        """发送到所有已注册渠道"""
        results = {}
        for name, notifier in self._channels.items():
            results[name] = notifier.send(title, content)
        return results

    def send(self, channel: str, title: str, content: str) -> bool:
        notifier = self._channels.get(channel)
        if notifier:
            return notifier.send(title, content)
        logger.warning("通知渠道未注册: {}", channel)
        return False

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "Notifier":
        """从配置创建 Notifier"""
        manager = cls()
        channels = config.get("notify", {}).get("channels", {})

        # 企业微信
        wecom_cfg = channels.get("wecom", {})
        if wecom_cfg.get("enabled"):
            manager.register("wecom", WeComNotifier(wecom_cfg["webhook_url"]))

        # 钉钉
        dingtalk_cfg = channels.get("dingtalk", {})
        if dingtalk_cfg.get("enabled"):
            manager.register("dingtalk", DingTalkNotifier(dingtalk_cfg["webhook_url"]))

        # 邮件
        email_cfg = channels.get("email", {})
        if email_cfg.get("enabled"):
            manager.register("email", EmailNotifier(
                smtp_host=email_cfg["smtp_host"],
                smtp_port=email_cfg.get("smtp_port", 587),
                sender=email_cfg["sender"],
                password=email_cfg["password"],
                receivers=email_cfg.get("receivers", []),
                use_tls=email_cfg.get("use_tls", True),
            ))

        return manager


def build_report_content(results: List[Any], summary: Dict[str, Any]) -> str:
    """构建通知报告内容（Markdown 格式）"""
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    duration = summary.get("duration", 0)

    lines = [
        f"> 总计: {total} | ✅ 通过: {passed} | ❌ 失败: {failed} | ⏭ 跳过: {skipped}",
        f"> 耗时: {duration:.2f}s",
        "",
    ]

    # 失败用例明细
    failures = [r for r in results if not r.get("passed")]
    if failures:
        lines.append("**失败用例明细:**")
        for f in failures[:10]:  # 最多展示 10 条
            lines.append(f"- `{f.get('case_id')}` {f.get('case_name')}: {f.get('error_message', '')}")
        if len(failures) > 10:
            lines.append(f"- ... 及其他 {len(failures) - 10} 条")
    else:
        lines.append("🎉 全部用例通过！")

    return "\n".join(lines)