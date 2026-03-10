#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宿迁教育局公告监控系统 - Azure Ubuntu 服务器版
功能：
- 运行时间：早6:00 - 晚22:00
- 多线程架构（检查/邮件/附件下载分离）
- 日志轮转
- 守护线程监控
"""

import urllib.request
import urllib.error
import re
import ssl
import smtplib
import json
import os
import time
import threading
import queue
import logging
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum
import sys


# ===================== 配置区域 =====================
# 从环境变量读取配置（Azure服务器上通过export设置）
SMTP_USER = os.getenv("SMTP_USER", "1142573554@qq.com")
SMTP_PASS = os.getenv("SMTP_PASS", "fizuanrgvwokbadb")
SMTP_NAME = os.getenv("SMTP_NAME", "宿迁通告监控小助手")
TO_EMAILS = os.getenv("TO_EMAILS", "3282510774@qq.com,space621@qq.com,2011261581@qq.com").split(",")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
MONITOR_URL = os.getenv("MONITOR_URL", "https://jyj.suqian.gov.cn/sjyj/tzgg/list.shtml")

# 时间配置（秒）
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # 10分钟
REPORT_INTERVAL = int(os.getenv("REPORT_INTERVAL", "3600"))  # 1小时

# 运行时间配置
RUN_START_HOUR = int(os.getenv("RUN_START_HOUR", "6"))   # 早6点
RUN_END_HOUR = int(os.getenv("RUN_END_HOUR", "22"))      # 晚22点

# 文件路径（Azure Ubuntu路径）
DATA_FILE = Path(os.getenv("DATA_FILE", "/home/azureuser/monitor/monitor_records.json"))
LOG_FILE = Path(os.getenv("LOG_FILE", "/home/azureuser/monitor/monitor.log"))
ATTACHMENTS_DIR = Path(os.getenv("ATTACHMENTS_DIR", "/home/azureuser/monitor/attachments"))

# 日志配置
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

# 特殊关键词配置
SPECIAL_KEYWORDS = ["宿迁市市直教育系统", "体检", "拟招聘"]
# ===================================================


class EmailType(Enum):
    """邮件类型"""
    NEWS = "news"
    REPORT = "report"
    TEST = "test"


@dataclass
class NewsItem:
    """新闻条目"""
    date: str
    title: str
    url: str
    first_seen: str = ""
    notified: bool = False
    is_special: bool = False
    attachments: List[dict] = None
    attachments_downloaded: bool = False
    
    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
    
    def to_dict(self) -> dict:
        return {
            'date': self.date,
            'title': self.title,
            'url': self.url,
            'first_seen': self.first_seen,
            'notified': self.notified,
            'is_special': self.is_special,
            'attachments': self.attachments,
            'attachments_downloaded': self.attachments_downloaded
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'NewsItem':
        return cls(
            date=data['date'],
            title=data['title'],
            url=data['url'],
            first_seen=data.get('first_seen', ''),
            notified=data.get('notified', False),
            is_special=data.get('is_special', False),
            attachments=data.get('attachments', []),
            attachments_downloaded=data.get('attachments_downloaded', False)
        )
    
    def __hash__(self):
        return hash((self.date, self.title))
    
    def __eq__(self, other):
        if isinstance(other, NewsItem):
            return self.date == other.date and self.title == other.title
        return False


@dataclass
class EmailTask:
    """邮件任务"""
    email_type: EmailType
    subject: str = ""
    content: str = ""
    news_items: Optional[List[NewsItem]] = None


@dataclass
class DownloadTask:
    """下载任务"""
    item: NewsItem


class LoggerManager:
    """日志管理器 - 支持日志轮转"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 确保日志目录存在
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger('monitor')
        self.logger.setLevel(logging.INFO)
        
        self.logger.handlers.clear()
        
        file_handler = RotatingFileHandler(
            LOG_FILE, 
            maxBytes=LOG_MAX_BYTES, 
            backupCount=LOG_BACKUP_COUNT, 
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self._initialized = True
    
    def info(self, msg: str):
        self.logger.info(msg)
    
    def error(self, msg: str):
        self.logger.error(msg)
    
    def warning(self, msg: str):
        self.logger.warning(msg)
    
    def debug(self, msg: str):
        self.logger.debug(msg)


class DataStore:
    """数据存储管理 - 线程安全"""
    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.all_news: Dict[str, NewsItem] = {}
        self.check_count = 0
        self.last_check_time: Optional[str] = None
        self.start_time = datetime.now().isoformat()
        self._lock = threading.Lock()
        
        # 确保数据目录存在
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.load()
    
    def _make_key(self, item: NewsItem) -> str:
        return f"{item.date}|{item.title}"
    
    def load(self):
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.all_news = {
                        k: NewsItem.from_dict(v)
                        for k, v in data.get('all_news', {}).items()
                    }
                    self.check_count = data.get('check_count', 0)
                    self.last_check_time = data.get('last_check_time')
                    self.start_time = data.get('start_time', self.start_time)
                print(f"📂 已加载 {len(self.all_news)} 条历史记录")
            except Exception as e:
                print(f"⚠️ 加载数据失败: {e}")
    
    def save(self):
        with self._lock:
            try:
                data = {
                    'all_news': {k: v.to_dict() for k, v in self.all_news.items()},
                    'check_count': self.check_count,
                    'last_check_time': self.last_check_time,
                    'start_time': self.start_time,
                    'save_time': datetime.now().isoformat()
                }
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 保存数据失败: {e}")
    
    def update_news(self, new_items: List[NewsItem]) -> List[NewsItem]:
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            truly_new = []
            
            for item in new_items:
                key = self._make_key(item)
                if key not in self.all_news:
                    item.first_seen = datetime.now().isoformat()
                    item.notified = False
                    self.all_news[key] = item
                    
                    if item.date == today:
                        truly_new.append(item)
                else:
                    existing = self.all_news[key]
                    existing.url = item.url
            
            self.check_count += 1
            self.last_check_time = datetime.now().isoformat()
        
        self.save()
        return truly_new
    
    def mark_notified(self, items: List[NewsItem]):
        with self._lock:
            for item in items:
                key = self._make_key(item)
                if key in self.all_news:
                    self.all_news[key].notified = True
        self.save()
    
    def mark_downloaded(self, item: NewsItem):
        with self._lock:
            key = self._make_key(item)
            if key in self.all_news:
                self.all_news[key].attachments_downloaded = True
        self.save()
    
    def get_today_stats(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        today_news = [v for v in self.all_news.values() if v.date == today]
        notified = sum(1 for v in today_news if v.notified)
        
        return {
            'total_today': len(today_news),
            'notified': notified,
            'pending': len(today_news) - notified
        }
    
    def get_stats(self) -> dict:
        today_stats = self.get_today_stats()
        return {
            'total_records': len(self.all_news),
            'check_count': self.check_count,
            'today': today_stats,
            'start_time': self.start_time,
            'last_check': self.last_check_time
        }


class NewsFetcher:
    """新闻抓取器"""
    def __init__(self):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
    
    def fetch(self) -> List[NewsItem]:
        try:
            req = urllib.request.Request(MONITOR_URL, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=30) as response:
                html = response.read().decode('utf-8')
            
            pattern = r'<a[^>]+href="([^"]+)"[^>]+title=\'([^\']+)\'[^>]*>[^<]*</a>\s*<span>\[(\d{4}-\d{2}-\d{2})\]</span>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            
            news_items = []
            for url, title, date in matches:
                title = (title
                    .replace('&quot;', '"')
                    .replace('&amp;', '&')
                    .replace('&lt;', '<')
                    .replace('&gt;', '>')
                    .replace('&nbsp;', ' ')
                    .replace('&#39;', "'")
                    .strip()
                )
                
                is_special = any(keyword in title for keyword in SPECIAL_KEYWORDS)
                item = NewsItem(date=date, title=title, url=url, is_special=is_special)
                
                if is_special:
                    item.attachments = self._fetch_detail_attachments(url)
                
                news_items.append(item)
            
            return news_items
        except Exception as e:
            return []
    
    def _fetch_detail_attachments(self, url: str) -> List[dict]:
        try:
            if url.startswith('/'):
                full_url = f"https://jyj.suqian.gov.cn{url}"
            elif url.startswith('http'):
                full_url = url
            else:
                full_url = f"https://jyj.suqian.gov.cn/sjyj/tzgg/{url}"
            
            req = urllib.request.Request(full_url, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=30) as response:
                html = response.read().decode('utf-8')
            
            attachments = []
            
            pattern1 = r'<a[^>]+href="([^"]+files[^"]+\.(?:pdf|doc|docx|xls|xlsx|zip|rar))"[^>]*>([^<]+)</a>'
            matches1 = re.findall(pattern1, html, re.IGNORECASE)
            
            for href, name in matches1:
                if href.startswith('/'):
                    attach_url = f"https://jyj.suqian.gov.cn{href}"
                elif href.startswith('http'):
                    attach_url = href
                else:
                    base_url = full_url.rsplit('/', 1)[0]
                    attach_url = f"{base_url}/{href}"
                
                attachments.append({
                    'name': name.strip(),
                    'url': attach_url
                })
            
            return attachments
        except Exception as e:
            return []


class AttachmentDownloader(threading.Thread):
    """附件下载线程"""
    def __init__(self, download_queue: queue.Queue, data_store: DataStore, logger: LoggerManager):
        super().__init__(daemon=True)
        self.download_queue = download_queue
        self.data_store = data_store
        self.logger = logger
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.running = True
        
        # 确保附件目录存在
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    def run(self):
        self.logger.info("📥 附件下载线程已启动")
        while self.running:
            try:
                task = self.download_queue.get(timeout=1)
                if task is None:
                    break
                
                self._download_attachments(task.item)
                self.download_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"❌ 下载线程异常: {e}")
    
    def _download_attachments(self, item: NewsItem):
        if not item.attachments or item.attachments_downloaded:
            return
        
        self.logger.info(f"📥 开始下载附件: {item.title[:30]}...")
        
        # 创建安全目录名
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in item.title[:50])
        item_dir = ATTACHMENTS_DIR / f"{item.date}_{safe_title}"
        item_dir.mkdir(exist_ok=True)
        
        downloaded_count = 0
        for attach in item.attachments:
            try:
                filename = attach['name'].replace('/', '_').replace('\\', '_')
                filepath = item_dir / filename
                
                if filepath.exists():
                    self.logger.info(f"  ⏭️  已存在: {filename}")
                    downloaded_count += 1
                    continue
                
                req = urllib.request.Request(attach['url'])
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as response:
                    with open(filepath, 'wb') as f:
                        f.write(response.read())
                
                self.logger.info(f"  ✅ 下载完成: {filename}")
                downloaded_count += 1
            except Exception as e:
                self.logger.error(f"  ❌ 下载失败 {attach['name']}: {e}")
        
        if downloaded_count == len(item.attachments):
            self.data_store.mark_downloaded(item)
            self.logger.info(f"✅ 所有附件下载完成 ({downloaded_count}/{len(item.attachments)})")
        else:
            self.logger.warning(f"⚠️ 部分附件下载失败 ({downloaded_count}/{len(item.attachments)})")
    
    def stop(self):
        self.running = False


class EmailSender:
    """邮件发送器"""
    def __init__(self):
        self.smtp_user = SMTP_USER
        self.smtp_pass = SMTP_PASS
        self.to_emails = TO_EMAILS
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
    
    def send(self, subject: str, html_content: str) -> bool:
        try:
            msg = MIMEMultipart()
            from_header = f"{Header(SMTP_NAME, 'utf-8').encode()} <{self.smtp_user}>"
            msg['From'] = from_header
            msg['To'] = ", ".join(self.to_emails)
            msg['Subject'] = Header(subject, 'utf-8').encode()
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.smtp_user, self.to_emails, msg.as_string())
            
            return True
        except Exception as e:
            print(f"邮件发送错误: {e}")
            return False
    
    def send_test_email(self) -> bool:
        """发送测试邮件"""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%H:%M:%S")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 20px 0;">
                <tr>
                    <td align="center">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 500px;">
                            <tr>
                                <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">✅ 测试邮件</h1>
                                    <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">系统运行正常</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 30px; text-align: center;">
                                    <p style="color: #666; font-size: 15px; line-height: 1.8;">
                                        这是来自 <strong>宿迁通告监控小助手</strong> 的测试邮件。<br>
                                        如果您收到此邮件，说明邮件发送功能正常。
                                    </p>
                                    <p style="color: #999; font-size: 13px; margin-top: 20px;">
                                        测试时间: {today} {now}
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【宿迁通告监控小助手】· 测试邮件 - 系统运行正常"
        return self.send(subject, html)
    
    def send_news_notification(self, news_items: List[NewsItem], has_new: bool = True) -> bool:
        """发送新公告通知 - 优化标题"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if not has_new:
            # 无新通知时的简洁邮件
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 20px 0;">
                    <tr>
                        <td align="center">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 500px;">
                                <tr>
                                    <td style="background: #95a5a6; padding: 30px; text-align: center;">
                                        <h1 style="margin: 0; color: #fff; font-size: 20px; font-weight: 600;">📭 无变化</h1>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 30px; text-align: center;">
                                        <p style="color: #666; font-size: 15px;">
                                            {today} 暂无新公告
                                        </p>
                                        <p style="color: #999; font-size: 12px; margin-top: 15px;">
                                            下次检查: 10分钟后
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """
            subject = f"【宿迁通告监控小助手】· 无变化"
            return self.send(subject, html)
        
        # 有新通知时的邮件
        news_cards = ""
        for i, item in enumerate(news_items, 1):
            full_url = f"https://jyj.suqian.gov.cn{item.url}" if not item.url.startswith('http') else item.url
            news_cards += f"""
            <div style="background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 15px; border: 1px solid #e8e8e8;">
                <div style="display: flex; align-items: center; margin-bottom: 12px;">
                    <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">{item.date}</span>
                    <span style="color: #999; font-size: 12px; margin-left: 10px;">#{i}</span>
                </div>
                <a href="{full_url}" style="color: #1a73e8; text-decoration: none; font-size: 16px; font-weight: 500; line-height: 1.6; display: block;">
                    {item.title}
                </a>
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 10px 0;">
                <tr>
                    <td align="center">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 600px;">
                            <tr>
                                <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 35px 25px; text-align: center;">
                                    <div style="margin-bottom: 12px;">
                                        <span style="display: inline-block; background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 11px; color: #fff;">新公告</span>
                                    </div>
                                    <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">🔔 重点提醒</h1>
                                    <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.85); font-size: 14px;">今日发布 {len(news_items)} 条通知</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 20px; background: #fafafa;">
                                    {news_cards}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【宿迁通告监控小助手】· 重点提醒 - 今日{len(news_items)}条新公告"
        return self.send(subject, html)
    
    def send_special_notification(self, item: NewsItem) -> bool:
        """发送特殊通知（含附件）"""
        if not item.is_special:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        full_url = f"https://jyj.suqian.gov.cn{item.url}" if not item.url.startswith('http') else item.url
        
        attachments_html = ""
        if item.attachments:
            attachments_html = """
            <div style="margin-top: 25px; padding: 20px; background: #f8f9fa; border-radius: 10px; border-left: 4px solid #e74c3c;">
                <h3 style="margin: 0 0 15px 0; color: #e74c3c; font-size: 16px; font-weight: 600;">
                    📎 附件列表
                </h3>
            """
            for i, attach in enumerate(item.attachments, 1):
                attachments_html += f"""
                <div style="margin-bottom: 12px; padding: 12px; background: #fff; border-radius: 8px; display: flex; align-items: center;">
                    <span style="background: #e74c3c; color: #fff; padding: 4px 10px; border-radius: 4px; font-size: 12px; margin-right: 12px;">附件{i}</span>
                    <a href="{attach['url']}" style="color: #1a73e8; text-decoration: none; font-size: 14px; flex: 1;">{attach['name']}</a>
                    <a href="{attach['url']}" style="background: #e74c3c; color: #fff; padding: 6px 14px; border-radius: 4px; font-size: 12px; text-decoration: none;">下载</a>
                </div>
                """
            attachments_html += "</div>"
        else:
            attachments_html = """
            <div style="margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 8px; color: #856404; font-size: 13px;">
                ⚠️ 该通知未检测到附件
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 10px 0;">
                <tr>
                    <td align="center">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 600px;">
                            <tr>
                                <td style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); padding: 35px 25px; text-align: center;">
                                    <div style="margin-bottom: 12px;">
                                        <span style="display: inline-block; background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 11px; color: #fff;">⚠️ 重点关注</span>
                                    </div>
                                    <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">特殊通知</h1>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 30px;">
                                    <div style="background: #fff; border-radius: 12px; padding: 25px; border: 2px solid #e74c3c;">
                                        <div style="display: flex; align-items: center; margin-bottom: 15px;">
                                            <span style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); color: #fff; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600;">{item.date}</span>
                                            <span style="color: #e74c3c; font-size: 13px; margin-left: 10px; font-weight: 500;">🔔 重点关注</span>
                                        </div>
                                        <h2 style="margin: 0 0 20px 0; color: #2c3e50; font-size: 18px; font-weight: 600; line-height: 1.6;">
                                            {item.title}
                                        </h2>
                                        <a href="{full_url}" style="display: inline-block; padding: 12px 30px; background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); color: #fff; text-decoration: none; border-radius: 25px; font-weight: 500; font-size: 14px;">
                                            查看详情 →
                                        </a>
                                    </div>
                                    {attachments_html}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【宿迁通告监控小助手】· 重点关注 - {item.title[:25]}..."
        return self.send(subject, html)
    
    def send_report(self, stats: dict) -> bool:
        """发送述职报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%H:%M:%S")
        
        try:
            start = datetime.fromisoformat(stats['start_time'])
            runtime = datetime.now() - start
            runtime_str = f"{runtime.days}天 {runtime.seconds//3600}小时 {(runtime.seconds//60)%60}分钟"
        except:
            runtime_str = "未知"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 10px 0;">
                <tr>
                    <td align="center">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 600px;">
                            <tr>
                                <td style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); padding: 35px 20px; text-align: center;">
                                    <div style="margin-bottom: 12px;">
                                        <span style="display: inline-block; background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 11px; color: #fff;">运行日报</span>
                                    </div>
                                    <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">系统述职报告</h1>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 20px;">
                                    <table width="100%" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td width="50%" style="padding: 8px;">
                                                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; text-align: center; color: #fff;">
                                                    <div style="font-size: 32px; font-weight: bold;">{stats['today']['total_today']}</div>
                                                    <div style="font-size: 12px; opacity: 0.9; margin-top: 5px;">今日公告</div>
                                                </div>
                                            </td>
                                            <td width="50%" style="padding: 8px;">
                                                <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; padding: 20px; text-align: center; color: #fff;">
                                                    <div style="font-size: 32px; font-weight: bold;">{stats['today']['notified']}</div>
                                                    <div style="font-size: 12px; opacity: 0.9; margin-top: 5px;">已推送</div>
                                                </div>
                                            </td>
                                        </tr>
                                    </table>
                                    <table width="100%" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td width="50%" style="padding: 8px;">
                                                <div style="background: #f8f9fa; border-radius: 12px; padding: 20px; text-align: center; border: 2px solid #e9ecef;">
                                                    <div style="font-size: 32px; font-weight: bold; color: #495057;">{stats['check_count']}</div>
                                                    <div style="font-size: 12px; color: #868e96; margin-top: 5px;">检查次数</div>
                                                </div>
                                            </td>
                                            <td width="50%" style="padding: 8px;">
                                                <div style="background: #f8f9fa; border-radius: 12px; padding: 20px; text-align: center; border: 2px solid #e9ecef;">
                                                    <div style="font-size: 32px; font-weight: bold; color: #495057;">{stats['total_records']}</div>
                                                    <div style="font-size: 12px; color: #868e96; margin-top: 5px;">历史记录</div>
                                                </div>
                                            </td>
                                        </tr>
                                    </table>
                                    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 15px; background: #f8f9fa; border-radius: 10px;">
                                        <tr>
                                            <td style="padding: 15px 20px; border-bottom: 1px solid #e9ecef;">
                                                <span style="color: #868e96; font-size: 13px;">⏱️ 运行时长</span>
                                                <span style="float: right; color: #495057; font-weight: 500; font-size: 14px;">{runtime_str}</span>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 15px 20px;">
                                                <span style="color: #868e96; font-size: 13px;">🚀 启动时间</span>
                                                <span style="float: right; color: #495057; font-weight: 500; font-size: 14px;">{stats['start_time'][:19].replace('T', ' ') if stats['start_time'] else '-'}</span>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 20px; background: #f8f9fa; text-align: center; color: #999; font-size: 12px;">
                                    <p style="margin: 0;">报告生成时间: {today} {now}</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【宿迁通告监控小助手】· 运行日报 - {today}"
        return self.send(subject, html)


class EmailWorker(threading.Thread):
    """邮件发送工作线程"""
    def __init__(self, email_queue: queue.Queue, data_store: DataStore, logger: LoggerManager):
        super().__init__(daemon=True)
        self.email_queue = email_queue
        self.data_store = data_store
        self.logger = logger
        self.sender = EmailSender()
        self.running = True
    
    def run(self):
        self.logger.info("📧 邮件发送线程已启动")
        while self.running:
            try:
                task = self.email_queue.get(timeout=1)
                if task is None:
                    break
                
                self._process_task(task)
                self.email_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"❌ 邮件线程异常: {e}")
    
    def _process_task(self, task: EmailTask):
        if task.email_type == EmailType.TEST:
            self.logger.info("📧 发送测试邮件...")
            if self.sender.send_test_email():
                self.logger.info("✅ 测试邮件发送成功")
            else:
                self.logger.error("❌ 测试邮件发送失败")
        
        elif task.email_type == EmailType.NEWS and task.news_items is not None:
            # 分离特殊通知和普通通知
            special_items = [item for item in task.news_items if item.is_special]
            normal_items = [item for item in task.news_items if not item.is_special]
            
            # 特殊通知单独发送
            for item in special_items:
                self.logger.info(f"🔔 发送特殊通知: {item.title[:30]}...")
                if self.sender.send_special_notification(item):
                    self.data_store.mark_notified([item])
                    self.logger.info(f"✅ 特殊通知邮件发送成功")
                else:
                    self.logger.error(f"❌ 特殊通知邮件发送失败")
            
            # 普通通知批量发送
            if normal_items:
                self.logger.info(f"📧 发送普通公告 ({len(normal_items)}条)...")
                if self.sender.send_news_notification(normal_items):
                    self.data_store.mark_notified(normal_items)
                    self.logger.info(f"✅ 普通公告邮件发送成功")
                else:
                    self.logger.error("❌ 普通公告邮件发送失败")
        
        elif task.email_type == EmailType.REPORT:
            self.logger.info("📧 发送述职报告...")
            stats = self.data_store.get_stats()
            if self.sender.send_report(stats):
                self.logger.info("✅ 述职报告发送成功")
            else:
                self.logger.error("❌ 述职报告发送失败")
    
    def stop(self):
        self.running = False


class MonitorThread(threading.Thread):
    """监控线程"""
    def __init__(self, data_store: DataStore, email_queue: queue.Queue, 
                 download_queue: queue.Queue, logger: LoggerManager):
        super().__init__(daemon=True)
        self.data_store = data_store
        self.email_queue = email_queue
        self.download_queue = download_queue
        self.logger = logger
        self.fetcher = NewsFetcher()
        self.running = True
        self.last_check_time = 0
        self.last_report_time = 0
    
    def _is_in_runtime(self) -> bool:
        """检查是否在运行时间内"""
        now = datetime.now()
        return RUN_START_HOUR <= now.hour < RUN_END_HOUR
    
    def run(self):
        self.logger.info("🔍 监控线程已启动")
        
        # 首次检查
        self._do_check()
        self._do_report()
        
        while self.running:
            current_time = time.time()
            
            # 检查是否在运行时间内
            if not self._is_in_runtime():
                next_start = datetime.now().replace(hour=RUN_START_HOUR, minute=0, second=0)
                if next_start < datetime.now():
                    next_start += timedelta(days=1)
                wait_seconds = (next_start - datetime.now()).total_seconds()
                self.logger.info(f"⏰ 非运行时间，等待至 {RUN_START_HOUR}:00 (约{wait_seconds/3600:.1f}小时)")
                time.sleep(min(wait_seconds, 3600))  # 最多等待1小时再检查
                continue
            
            # 执行检查
            if current_time - self.last_check_time >= CHECK_INTERVAL:
                self._do_check()
            
            # 发送报告
            if current_time - self.last_report_time >= REPORT_INTERVAL:
                self._do_report()
            
            time.sleep(1)
    
    def _do_check(self):
        self.logger.info("🔍 开始检查公告...")
        self.last_check_time = time.time()
        
        news = self.fetcher.fetch()
        if not news:
            self.logger.warning("❌ 抓取失败")
            return
        
        self.logger.info(f"📰 抓取到 {len(news)} 条公告")
        
        new_items = self.data_store.update_news(news)
        
        if new_items:
            self.logger.info(f"🆕 发现 {len(new_items)} 条新公告")
            # 提交邮件任务
            task = EmailTask(
                email_type=EmailType.NEWS,
                news_items=new_items
            )
            self.email_queue.put(task)
            
            # 提交附件下载任务（特殊通知）
            for item in new_items:
                if item.is_special and item.attachments:
                    download_task = DownloadTask(item=item)
                    self.download_queue.put(download_task)
        else:
            self.logger.info("📭 暂无新公告")
            # 可选：发送无变化通知（每小时一次）
            # task = EmailTask(email_type=EmailType.NEWS, news_items=[])
            # self.email_queue.put(task)
        
        self.data_store.save()
    
    def _do_report(self):
        self.logger.info("📊 准备发送述职报告...")
        self.last_report_time = time.time()
        
        task = EmailTask(email_type=EmailType.REPORT)
        self.email_queue.put(task)
    
    def stop(self):
        self.running = False


class WatchdogThread(threading.Thread):
    """守护线程"""
    def __init__(self, monitor_thread: MonitorThread, email_worker: EmailWorker,
                 download_worker: AttachmentDownloader, logger: LoggerManager):
        super().__init__(daemon=True)
        self.monitor_thread = monitor_thread
        self.email_worker = email_worker
        self.download_worker = download_worker
        self.logger = logger
        self.running = True
    
    def run(self):
        self.logger.info("🐕 守护线程已启动")
        while self.running:
            time.sleep(30)
            
            if not self.running:
                break
            
            # 检查各线程状态
            if not self.monitor_thread.is_alive():
                self.logger.error("⚠️ 监控线程停止")
            if not self.email_worker.is_alive():
                self.logger.error("⚠️ 邮件线程停止")
            if not self.download_worker.is_alive():
                self.logger.error("⚠️ 下载线程停止")
            
            self.logger.debug("💓 系统心跳正常")
    
    def stop(self):
        self.running = False


class Monitor:
    """监控主类"""
    def __init__(self):
        self.logger = LoggerManager()
        self.data_store = DataStore(DATA_FILE)
        self.email_queue = queue.Queue()
        self.download_queue = queue.Queue()
        
        # 创建工作线程
        self.email_worker = EmailWorker(self.email_queue, self.data_store, self.logger)
        self.download_worker = AttachmentDownloader(self.download_queue, self.data_store, self.logger)
        self.monitor_thread = MonitorThread(self.data_store, self.email_queue, self.download_queue, self.logger)
        self.watchdog = WatchdogThread(self.monitor_thread, self.email_worker, self.download_worker, self.logger)
        
        self.running = True
    
    def send_test_email(self):
        """发送测试邮件"""
        self.logger.info("📧 发送测试邮件...")
        task = EmailTask(email_type=EmailType.TEST)
        self.email_queue.put(task)
    
    def run(self):
        self.logger.info("=" * 60)
        self.logger.info("🚀 宿迁教育局公告监控系统 - Azure版 启动")
        self.logger.info(f"📍 监控地址: {MONITOR_URL}")
        self.logger.info(f"⏱️  运行时间: {RUN_START_HOUR}:00 - {RUN_END_HOUR}:00")
        self.logger.info(f"📊 检查间隔: {CHECK_INTERVAL//60}分钟")
        self.logger.info(f"📧 收件人: {len(TO_EMAILS)}个")
        self.logger.info("🔧 多线程 | 日志轮转 | 附件下载")
        self.logger.info("=" * 60)
        
        # 发送测试邮件
        self.send_test_email()
        
        # 启动工作线程
        self.email_worker.start()
        self.download_worker.start()
        self.monitor_thread.start()
        self.watchdog.start()
        
        self.logger.info("✅ 所有线程已启动")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("👋 用户中断，正在停止...")
            self.stop()
    
    def stop(self):
        self.running = False
        
        self.monitor_thread.stop()
        self.watchdog.stop()
        self.email_worker.stop()
        self.download_worker.stop()
        
        self.email_queue.put(None)
        self.download_queue.put(None)
        
        self.email_worker.join(timeout=5)
        self.download_worker.join(timeout=5)
        
        self.logger.info("✅ 系统已停止")


if __name__ == "__main__":
    monitor = Monitor()
    monitor.run()
