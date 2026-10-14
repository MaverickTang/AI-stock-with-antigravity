"""
多渠道推送分发器 (WeChat PushPlus / ServerChan / Telegram)
"""
import requests
from typing import Dict, Any

class MessageNotifier:
    def __init__(self, delivery_cfg: Dict[str, Any]):
        self.cfg = delivery_cfg or {}
        self.pushplus_token = self.cfg.get("pushplus_token", "").strip()
        self.serverchan_sendkey = self.cfg.get("serverchan_sendkey", "").strip()
        self.tg_cfg = self.cfg.get("telegram", {})

    def send_pushplus(self, title: str, content_markdown: str) -> bool:
        """通过 PushPlus 推送至微信"""
        if not self.pushplus_token:
            return False
        url = "http://www.pushplus.plus/send"
        payload = {
            "token": self.pushplus_token,
            "title": title,
            "content": content_markdown,
            "template": "markdown"
        }
        try:
            resp = requests.post(url, json=payload, timeout=8)
            res = resp.json()
            if res.get("code") == 200:
                print("📲 [PushPlus] 微信研报推送成功！")
                return True
            else:
                print(f"⚠️ [PushPlus] 推送返回错误: {res.get('msg')}")
        except Exception as e:
            print(f"⚠️ [PushPlus] 发送异常: {e}")
        return False

    def send_serverchan(self, title: str, content_markdown: str) -> bool:
        """通过 Server酱 推送至微信"""
        if not self.serverchan_sendkey:
            return False
        url = f"https://sctapi.ftqq.com/{self.serverchan_sendkey}.send"
        payload = {
            "title": title,
            "desp": content_markdown
        }
        try:
            resp = requests.post(url, data=payload, timeout=8)
            res = resp.json()
            if res.get("code") == 0:
                print("📲 [Server酱] 微信研报推送成功！")
                return True
            else:
                print(f"⚠️ [Server酱] 推送返回错误: {res.get('message')}")
        except Exception as e:
            print(f"⚠️ [Server酱] 发送异常: {e}")
        return False

    def send_telegram(self, title: str, content_markdown: str) -> bool:
        """通过 Telegram Bot 推送"""
        bot_token = self.tg_cfg.get("bot_token", "").strip()
        chat_id = self.tg_cfg.get("chat_id", "").strip()
        if not bot_token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        text = f"*{title}*\n\n{content_markdown}"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                print("📲 [Telegram] 研报推送成功！")
                return True
            else:
                print(f"⚠️ [Telegram] 推送失败: {resp.text}")
        except Exception as e:
            print(f"⚠️ [Telegram] 发送异常: {e}")
        return False

    def dispatch_all(self, title: str, content_markdown: str):
        """统一向所有已配置的通道广播"""
        sent_any = False
        if self.pushplus_token:
            self.send_pushplus(title, content_markdown)
            sent_any = True
        if self.serverchan_sendkey:
            self.send_serverchan(title, content_markdown)
            sent_any = True
        if self.tg_cfg.get("bot_token") and self.tg_cfg.get("chat_id"):
            self.send_telegram(title, content_markdown)
            sent_any = True

        if not sent_any:
            print("💡 [推送提示] 未配置外部推送 Token (如需手机接收微信/TG消息，请在 config/settings.yaml 中填写)")
