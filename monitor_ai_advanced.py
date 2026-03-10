#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宿迁教育局公告监控系统 - AI智能高级版
功能：
- AI智能标题生成（大师级prompt）
- 智能emoji匹配
- AI故障自动切换本地算法
- 本地算法自学习优化
- 关键词即时推送
- 高性能异步处理
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
import hashlib
import random
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import sqlite3

# 北京时区配置
from datetime import timezone


class BeijingTimezone:
    """北京时区 (UTC+8)"""
    offset = timedelta(hours=8)
    
    @classmethod
    def now(cls) -> datetime:
        """获取当前北京时间"""
        return datetime.now(timezone.utc).astimezone(timezone(cls.offset))
    
    @classmethod
    def strftime(cls, fmt: str) -> str:
        """获取当前北京时间的格式化字符串"""
        return cls.now().strftime(fmt)


# 便捷函数
def beijing_now() -> datetime:
    """获取当前北京时间"""
    return BeijingTimezone.now()


def beijing_strftime(fmt: str) -> str:
    """获取当前北京时间的格式化字符串"""
    return BeijingTimezone.strftime(fmt)


# ===================== 配置区域 =====================
SMTP_USER = os.getenv("SMTP_USER", "1142573554@qq.com")
SMTP_PASS = os.getenv("SMTP_PASS", "fizuanrgvwokbadb")
SMTP_NAME = os.getenv("SMTP_NAME", "宿迁通告监控小助手")
TO_EMAILS = os.getenv("TO_EMAILS", "3282510774@qq.com,space621@qq.com,2011261581@qq.com").split(",")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
MONITOR_URL = os.getenv("MONITOR_URL", "https://jyj.suqian.gov.cn/sjyj/tzgg/list.shtml")

# 时间配置（秒）
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))
REPORT_INTERVAL = int(os.getenv("REPORT_INTERVAL", "10800"))
URGENT_KEYWORDS_INTERVAL = 60  # 紧急关键词检查间隔1分钟

# 运行时间配置
RUN_START_HOUR = int(os.getenv("RUN_START_HOUR", "6"))
RUN_END_HOUR = int(os.getenv("RUN_END_HOUR", "22"))

# 文件路径
DATA_FILE = Path(os.getenv("DATA_FILE", "/home/azureuser/monitor/monitor_records.json"))
LOG_FILE = Path(os.getenv("LOG_FILE", "/home/azureuser/monitor/logs/monitor.log"))
ATTACHMENTS_DIR = Path(os.getenv("ATTACHMENTS_DIR", "/home/azureuser/monitor/attachments"))
LEARNING_DB = Path("/home/azureuser/monitor/learning.db")

# 日志配置
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

# 硅基流动 AI 配置
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-ugbzeiqbbibjfhhtpdsqfajevuwlcagljpkydhorkokkuzaq")
SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
SILICONFLOW_MODEL = "deepseek-ai/DeepSeek-V3.2"
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_TIMEOUT = 10  # AI请求超时时间（秒）

# 紧急关键词配置（立即推送）
URGENT_KEYWORDS = {
    "体检": {"emoji": "🏥", "priority": 1, "desc": "体检通知"},
    "拟招聘": {"emoji": "👔", "priority": 1, "desc": "拟聘用公示"},
    "宿迁市市直教育系统": {"emoji": "🏫", "priority": 1, "desc": "市直教育系统"},
    "面试": {"emoji": "🎤", "priority": 2, "desc": "面试通知"},
    "笔试": {"emoji": "✏️", "priority": 2, "desc": "笔试通知"},
    "成绩": {"emoji": "📊", "priority": 2, "desc": "成绩公布"},
    "录用": {"emoji": "🎉", "priority": 1, "desc": "录用通知"},
    "公示": {"emoji": "📢", "priority": 2, "desc": "公示信息"},
    "递补": {"emoji": "🔄", "priority": 2, "desc": "递补通知"},
    "资格复审": {"emoji": "📋", "priority": 2, "desc": "资格复审"},
}

# 普通关键词emoji映射
KEYWORD_EMOJI_MAP = {
    "招聘": "💼",
    "教师": "👨‍🏫",
    "学校": "🏫",
    "教育": "📚",
    "考试": "📝",
    "报名": "📝",
    "公告": "📢",
    "通知": "📣",
    "结果": "✅",
    "公示": "📋",
    "体检": "🏥",
    "面试": "🎤",
    "笔试": "✏️",
    "成绩": "📊",
    "录用": "🎉",
    "聘用": "🤝",
    "资格": "📋",
    "复审": "🔍",
    "递补": "🔄",
    "调剂": "🔄",
    "考察": "🔎",
    "政审": "📄",
    "培训": "📖",
    "报到": "📍",
    "入职": "🆕",
    "岗位": "💺",
    "编制": "📎",
    "合同": "📄",
    "待遇": "💰",
    "工资": "💵",
    "福利": "🎁",
    "保险": "🛡️",
    "公积金": "🏦",
    "住房": "🏠",
    "补贴": "💸",
    "奖金": "🎯",
    "绩效": "📈",
    "考核": "📊",
    "晋升": "⬆️",
    "调动": "🔄",
    "辞职": "👋",
    "解聘": "❌",
    "退休": "🌅",
    "离职": "🚪",
    "请假": "🏖️",
    "休假": "🏝️",
    "加班": "⏰",
    "值班": "🌙",
    "出差": "✈️",
    "报销": "🧾",
    "采购": "🛒",
    "招标": "📮",
    "投标": "📨",
    "中标": "🎯",
    "成交": "🤝",
    "合同": "📄",
    "协议": "📃",
    "方案": "📑",
    "计划": "📅",
    "总结": "📊",
    "报告": "📈",
    "调研": "🔍",
    "评估": "⚖️",
    "验收": "✅",
    "审计": "🔎",
    "检查": "🔍",
    "督导": "👁️",
    "评估": "📊",
    "评比": "🏆",
    "表彰": "🎖️",
    "奖励": "🏅",
    "处分": "⚠️",
    "通报": "📢",
    "批评": "❌",
    "表扬": "👍",
    "先进": "⭐",
    "优秀": "🌟",
    "模范": "👑",
    "标兵": "🎖️",
    "能手": "🔧",
    "骨干": "🦴",
    "带头人": "🚀",
    "领军": "🦅",
    "名师": "👨‍🏫",
    "特级教师": "👨‍🎓",
    "高级教师": "👨‍💼",
    "一级教师": "👩‍💼",
    "二级教师": "👨‍💻",
    "三级教师": "👩‍💻",
    "正高级": "👨‍🎓",
    "副高级": "👨‍💼",
    "中级": "👩‍💼",
    "初级": "👨‍💻",
    "员级": "👩‍💻",
}

# ===================================================


class EmailType(Enum):
    """邮件类型"""
    NEWS = "news"
    REPORT = "report"
    TEST = "test"
    URGENT = "urgent"


@dataclass
class NewsItem:
    """新闻条目"""
    date: str
    title: str
    url: str
    first_seen: str = ""
    notified: bool = False
    is_special: bool = False
    is_urgent: bool = False
    attachments: List[dict] = None
    attachments_downloaded: bool = False
    ai_summary: str = ""
    ai_title: str = ""  # AI生成的标题
    emoji: str = "📢"  # 匹配的emoji
    priority: int = 3  # 优先级 1-5，1最高
    
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
            'is_urgent': self.is_urgent,
            'attachments': self.attachments,
            'attachments_downloaded': self.attachments_downloaded,
            'ai_summary': self.ai_summary,
            'ai_title': self.ai_title,
            'emoji': self.emoji,
            'priority': self.priority
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
            is_urgent=data.get('is_urgent', False),
            attachments=data.get('attachments', []),
            attachments_downloaded=data.get('attachments_downloaded', False),
            ai_summary=data.get('ai_summary', ''),
            ai_title=data.get('ai_title', ''),
            emoji=data.get('emoji', '📢'),
            priority=data.get('priority', 3)
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
        
        # 使用北京时间的日志格式器
        class BeijingFormatter(logging.Formatter):
            def formatTime(self, record, datefmt=None):
                beijing_time = datetime.fromtimestamp(record.created, timezone(timedelta(hours=8)))
                if datefmt:
                    return beijing_time.strftime(datefmt)
                return beijing_time.strftime('%Y-%m-%d %H:%M:%S')
        
        formatter = BeijingFormatter(
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


class LocalLearningDB:
    """本地学习数据库"""
    def __init__(self):
        self.db_path = LEARNING_DB
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建标题学习表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS title_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE,
                    emoji TEXT,
                    priority INTEGER,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建AI标题缓存表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_title_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_title TEXT UNIQUE,
                    ai_title TEXT,
                    emoji TEXT,
                    use_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def get_pattern(self, keyword: str) -> Optional[Dict]:
        """获取学习到的模式"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT emoji, priority, success_count FROM title_patterns WHERE keyword = ?",
                    (keyword,)
                )
                result = cursor.fetchone()
                if result:
                    return {
                        'emoji': result[0],
                        'priority': result[1],
                        'success_count': result[2]
                    }
                return None
    
    def save_pattern(self, keyword: str, emoji: str, priority: int):
        """保存学习到的模式"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO title_patterns (keyword, emoji, priority, success_count, last_used)
                    VALUES (?, ?, ?, COALESCE((SELECT success_count FROM title_patterns WHERE keyword = ?), 0) + 1, CURRENT_TIMESTAMP)
                ''', (keyword, emoji, priority, keyword))
                conn.commit()
    
    def get_cached_title(self, original_title: str) -> Optional[Dict]:
        """获取缓存的AI标题"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT ai_title, emoji FROM ai_title_cache WHERE original_title = ?",
                    (original_title,)
                )
                result = cursor.fetchone()
                if result:
                    # 更新使用次数
                    cursor.execute(
                        "UPDATE ai_title_cache SET use_count = use_count + 1 WHERE original_title = ?",
                        (original_title,)
                    )
                    conn.commit()
                    return {'ai_title': result[0], 'emoji': result[1]}
                return None
    
    def cache_title(self, original_title: str, ai_title: str, emoji: str):
        """缓存AI生成的标题"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO ai_title_cache (original_title, ai_title, emoji, use_count)
                    VALUES (?, ?, ?, COALESCE((SELECT use_count FROM ai_title_cache WHERE original_title = ?), 0) + 1)
                ''', (original_title, ai_title, emoji, original_title))
                conn.commit()


class SmartTitleGenerator:
    """智能标题生成器 - AI + 本地算法"""
    def __init__(self, logger: LoggerManager):
        self.logger = logger
        self.api_key = SILICONFLOW_API_KEY
        self.api_url = SILICONFLOW_API_URL
        self.model = SILICONFLOW_MODEL
        self.enabled = AI_ENABLED
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.learning_db = LocalLearningDB()
        self.ai_fail_count = 0
        self.ai_fail_threshold = 3  # AI连续失败3次后切换到本地
        self._executor = ThreadPoolExecutor(max_workers=3)
    
    def generate_title(self, item: NewsItem) -> Tuple[str, str]:
        """生成智能标题和emoji，返回 (标题, emoji)"""
        # 1. 检查缓存
        cached = self.learning_db.get_cached_title(item.title)
        if cached:
            self.logger.info(f"💾 使用缓存标题: {cached['ai_title'][:30]}...")
            return cached['ai_title'], cached['emoji']
        
        # 2. 检查紧急关键词（最高优先级）
        for keyword, config in URGENT_KEYWORDS.items():
            if keyword in item.title:
                item.is_urgent = True
                item.priority = config['priority']
                # 使用AI优化标题，但保留紧急标记
                if self.enabled and self.ai_fail_count < self.ai_fail_threshold:
                    ai_title = self._ai_generate_title(item.title, urgent=True)
                    if ai_title:
                        title = f"{config['emoji']} {ai_title}"
                        self.learning_db.cache_title(item.title, title, config['emoji'])
                        return title, config['emoji']
                # AI失败使用本地算法
                local_title = self._local_generate_title(item.title)
                title = f"{config['emoji']} {local_title}"
                self.learning_db.cache_title(item.title, title, config['emoji'])
                return title, config['emoji']
        
        # 3. 普通公告 - 尝试AI生成
        if self.enabled and self.ai_fail_count < self.ai_fail_threshold:
            ai_result = self._ai_generate_title_with_emoji(item.title)
            if ai_result:
                title, emoji = ai_result
                self.learning_db.cache_title(item.title, title, emoji)
                # 学习这个模式
                self._learn_pattern(item.title, emoji)
                return title, emoji
            else:
                self.ai_fail_count += 1
                self.logger.warning(f"⚠️ AI生成失败({self.ai_fail_count}/{self.ai_fail_threshold})，切换到本地算法")
        
        # 4. 使用本地算法
        local_title, emoji = self._local_generate_title_with_emoji(item.title)
        full_title = f"{emoji} {local_title}"
        self.learning_db.cache_title(item.title, full_title, emoji)
        return full_title, emoji
    
    def _ai_generate_title(self, title: str, urgent: bool = False) -> Optional[str]:
        """使用AI生成标题"""
        try:
            urgency_hint = "【紧急】" if urgent else ""
            
            prompt = f"""你是一位专业的教育新闻标题优化大师。请将以下公告标题优化得更简洁、更有吸引力，要求：

原标题：{title}

优化要求：
1. 保留核心信息（单位、事项、批次/时间）
2. 字数控制在25字以内
3. 去除冗余词汇（如"关于"、"的"、"进行"等）
4. 使用简洁有力的表达
5. 直接输出优化后的标题，不要加任何前缀或解释

示例：
原标题：江苏省宿迁市教育局直属学校面向2026年师范类毕业生公开招聘优秀教育人才（第二批）公告
优化后：宿迁市教育局直属学校招聘2026届师范生（第二批）

请直接输出优化后的标题："""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一位专业的教育新闻标题优化专家，擅长将冗长的公告标题优化为简洁有力的短标题。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 100,
                "temperature": 0.3,
                "top_p": 0.7
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            # 设置超时
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=AI_TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            optimized_title = result['choices'][0]['message']['content'].strip()
            
            # 清理标题
            optimized_title = optimized_title.replace('优化后：', '').replace('标题：', '').strip()
            
            # 重置失败计数
            self.ai_fail_count = 0
            
            self.logger.info(f"🤖 AI标题生成成功: {optimized_title[:40]}...")
            return optimized_title
            
        except Exception as e:
            self.logger.error(f"❌ AI标题生成失败: {e}")
            return None
    
    def _ai_generate_title_with_emoji(self, title: str) -> Optional[Tuple[str, str]]:
        """使用AI生成标题和emoji"""
        try:
            prompt = f"""你是一位专业的教育新闻编辑。请为以下公告标题：
1. 优化标题（简洁有力，25字以内）
2. 选择一个最合适的emoji（如💼招聘、🏫学校、📢公告、📝考试等）

原标题：{title}

请按以下格式输出：
标题：[优化后的标题]
Emoji：[emoji]

示例输出：
标题：宿迁市教育局招聘2026届师范生
Emoji：💼"""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一位专业的教育新闻编辑，擅长标题优化和视觉设计。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.3,
                "top_p": 0.7
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=AI_TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            response_text = result['choices'][0]['message']['content'].strip()
            
            # 解析标题和emoji
            title_match = re.search(r'标题[：:]\s*(.+)', response_text)
            emoji_match = re.search(r'Emoji[：:]\s*(.+)', response_text)
            
            if title_match:
                optimized_title = title_match.group(1).strip()
                emoji = emoji_match.group(1).strip() if emoji_match else "📢"
                
                # 重置失败计数
                self.ai_fail_count = 0
                
                self.logger.info(f"🤖 AI标题+Emoji生成成功: {emoji} {optimized_title[:40]}...")
                return optimized_title, emoji
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ AI标题+Emoji生成失败: {e}")
            return None
    
    def _local_generate_title(self, title: str) -> str:
        """本地算法生成标题"""
        # 1. 去除常见冗余词
        redundant_words = ['关于', '的', '进行', '开展', '实施', '组织', '做好', '加强', '进一步', '有关']
        result = title
        for word in redundant_words:
            result = result.replace(word, '')
        
        # 2. 简化单位名称
        result = result.replace('江苏省宿迁市', '宿迁')
        result = result.replace('宿迁市', '宿迁')
        result = result.replace('教育局直属学校', '市直学校')
        result = result.replace('教育局', '教委')
        
        # 3. 简化年份表达
        result = result.replace('面向2026年', '2026届')
        result = result.replace('2026年', '2026')
        result = result.replace('2025年', '2025')
        
        # 4. 简化常用词
        result = result.replace('公开招聘', '招聘')
        result = result.replace('优秀教育人才', '教师')
        result = result.replace('师范类毕业生', '师范生')
        result = result.replace('拟聘用人员', '拟聘人员')
        result = result.replace('名单公示', '公示')
        
        # 5. 去除末尾的"公告"、"通知"等
        result = re.sub(r'(公告|通知|公示)$', '', result)
        
        # 6. 限制长度
        if len(result) > 30:
            result = result[:27] + '...'
        
        return result.strip()
    
    def _local_generate_title_with_emoji(self, title: str) -> Tuple[str, str]:
        """本地算法生成标题和emoji"""
        # 生成标题
        optimized_title = self._local_generate_title(title)
        
        # 匹配emoji
        emoji = self._match_emoji(title)
        
        return optimized_title, emoji
    
    def _match_emoji(self, title: str) -> str:
        """根据关键词匹配emoji"""
        # 1. 检查学习数据库
        for keyword in KEYWORD_EMOJI_MAP.keys():
            if keyword in title:
                pattern = self.learning_db.get_pattern(keyword)
                if pattern:
                    return pattern['emoji']
                return KEYWORD_EMOJI_MAP[keyword]
        
        # 2. 默认emoji
        return "📢"
    
    def _learn_pattern(self, title: str, emoji: str):
        """学习标题模式"""
        # 提取关键词并学习
        for keyword in KEYWORD_EMOJI_MAP.keys():
            if keyword in title:
                self.learning_db.save_pattern(keyword, emoji, 2)
                break


class DataStore:
    """数据存储管理 - 线程安全"""
    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.all_news: Dict[str, NewsItem] = {}
        self.check_count = 0
        self.last_check_time: Optional[str] = None
        self.start_time = beijing_now().isoformat()
        self._lock = threading.Lock()
        
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
                    'save_time': beijing_now().isoformat()
                }
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 保存数据失败: {e}")
    
    def update_news(self, new_items: List[NewsItem]) -> List[NewsItem]:
        with self._lock:
            today = beijing_strftime("%Y-%m-%d")
            truly_new = []
            
            for item in new_items:
                key = self._make_key(item)
                if key not in self.all_news:
                    item.first_seen = beijing_now().isoformat()
                    item.notified = False
                    self.all_news[key] = item
                    
                    if item.date == today:
                        truly_new.append(item)
                else:
                    existing = self.all_news[key]
                    existing.url = item.url
            
            self.check_count += 1
            self.last_check_time = beijing_now().isoformat()
        
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
        today = beijing_strftime("%Y-%m-%d")
        today_news = [v for v in self.all_news.values() if v.date == today]
        notified = sum(1 for v in today_news if v.notified)
        urgent = sum(1 for v in today_news if v.is_urgent)
        
        return {
            'total_today': len(today_news),
            'notified': notified,
            'pending': len(today_news) - notified,
            'urgent': urgent
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
                
                # 检查紧急关键词
                is_urgent = False
                priority = 3
                emoji = "📢"
                
                for keyword, config in URGENT_KEYWORDS.items():
                    if keyword in title:
                        is_urgent = True
                        priority = config['priority']
                        emoji = config['emoji']
                        break
                
                # 如果不是紧急，检查普通关键词
                if not is_urgent:
                    for keyword, emj in KEYWORD_EMOJI_MAP.items():
                        if keyword in title:
                            emoji = emj
                            break
                
                item = NewsItem(
                    date=date, 
                    title=title, 
                    url=url, 
                    is_urgent=is_urgent,
                    priority=priority,
                    emoji=emoji
                )
                
                # 抓取附件（如果是紧急通知）
                if is_urgent:
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


class AISummarizer:
    """AI 摘要生成器"""
    def __init__(self, logger: LoggerManager):
        self.logger = logger
        self.api_key = SILICONFLOW_API_KEY
        self.api_url = SILICONFLOW_API_URL
        self.model = SILICONFLOW_MODEL
        self.enabled = AI_ENABLED
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    def summarize(self, title: str) -> str:
        if not self.enabled:
            return ""
        
        try:
            prompt = f"""请对以下教育类公告标题进行简要分析，提取关键信息（如招聘单位、岗位数量、截止时间等），用一句话总结核心内容，不超过50字：

公告标题：{title}

请直接输出总结，不要添加任何前缀或解释。"""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一位专业的教育招聘信息分析助手，擅长从公告标题中提取关键信息。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 200,
                "temperature": 0.3,
                "top_p": 0.7
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=AI_TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            summary = result['choices'][0]['message']['content'].strip()
            self.logger.info(f"🤖 AI摘要生成成功: {summary[:50]}...")
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ AI摘要生成失败: {e}")
            return ""


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
    
    def send(self, subject: str, html_content: str, text_content: str = None) -> bool:
        try:
            msg = MIMEMultipart('alternative')
            from_header = f"{Header(SMTP_NAME, 'utf-8').encode()} <{self.smtp_user}>"
            msg['From'] = from_header
            msg['To'] = ", ".join(self.to_emails)
            msg['Subject'] = Header(subject, 'utf-8').encode()
            
            if text_content:
                msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
            
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.smtp_user, self.to_emails, msg.as_string())
            
            return True
        except Exception as e:
            print(f"邮件发送错误: {e}")
            return False
    
    def send_test_email(self) -> bool:
        today = beijing_strftime("%Y-%m-%d")
        now = beijing_strftime("%H:%M:%S")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 20px 0;">
                <tr><td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 500px;">
                        <tr><td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
                            <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">✅ 测试邮件</h1>
                            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">系统运行正常</p>
                        </td></tr>
                        <tr><td style="padding: 30px; text-align: center;">
                            <p style="color: #666; font-size: 15px; line-height: 1.8;">
                                这是来自 <strong>宿迁通告监控小助手</strong> 的测试邮件。<br>
                                如果您收到此邮件，说明邮件发送功能正常。
                            </p>
                            <p style="color: #999; font-size: 13px; margin-top: 20px;">测试时间: {today} {now}</p>
                        </td></tr>
                    </table>
                </td></tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【测试邮件】系统运行正常"
        return self.send(subject, html)
    
    def send_urgent_notification(self, item: NewsItem) -> bool:
        """发送紧急通知（立即推送）"""
        today = beijing_strftime("%Y-%m-%d")
        full_url = f"https://jyj.suqian.gov.cn{item.url}" if not item.url.startswith('http') else item.url
        
        # 使用AI标题或原始标题
        display_title = item.ai_title if item.ai_title else item.title
        
        # 生成纯文本摘要
        text_summary = f"【紧急通知】{display_title}\n\n"
        text_summary += f"发布时间: {item.date}\n"
        text_summary += f"查看链接: {full_url}\n"
        if item.ai_summary:
            text_summary += f"\n📋 内容摘要: {item.ai_summary}\n"
        if item.attachments:
            text_summary += f"\n📎 附件数量: {len(item.attachments)}个"
        
        attachments_html = ""
        if item.attachments:
            attachments_html = """
            <div style="margin-top: 25px; padding: 20px; background: #f8f9fa; border-radius: 10px; border-left: 4px solid #e74c3c;">
                <h3 style="margin: 0 0 15px 0; color: #e74c3c; font-size: 16px; font-weight: 600;">📎 附件列表</h3>
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
        
        # AI摘要显示
        ai_summary_html = ""
        if item.ai_summary:
            ai_summary_html = f"""
            <div style="margin-top: 15px; padding: 15px; background: #f0f7ff; border-radius: 8px; border-left: 3px solid #667eea;">
                <span style="color: #667eea; font-size: 12px; font-weight: 600;">🤖 AI摘要:</span>
                <span style="color: #555; font-size: 14px; margin-left: 5px;">{item.ai_summary}</span>
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 10px 0;">
                <tr><td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 600px;">
                        <tr>
                            <td style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); padding: 35px 25px; text-align: center;">
                                <div style="margin-bottom: 12px;">
                                    <span style="display: inline-block; background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 11px; color: #fff;">🚨 紧急通知</span>
                                </div>
                                <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">立即查看</h1>
                                <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.85); font-size: 13px;">匹配重点关注关键词</p>
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
                                        {display_title}
                                    </h2>
                                    {ai_summary_html}
                                    <a href="{full_url}" style="display: inline-block; margin-top: 15px; padding: 12px 30px; background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); color: #fff; text-decoration: none; border-radius: 25px; font-weight: 500; font-size: 14px;">
                                        查看详情 →
                                    </a>
                                </div>
                                {attachments_html}
                            </td>
                        </tr>
                    </table>
                </td></tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"🚨 {display_title[:30]}..."
        return self.send(subject, html, text_summary)
    
    def send_news_notification(self, news_items: List[NewsItem], has_new: bool = True) -> bool:
        """发送新公告通知"""
        today = beijing_strftime("%Y-%m-%d")
        
        if not has_new:
            text_content = f"{today} 暂无新公告\n\n下次检查: 10分钟后"
            html = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 20px 0;">
                    <tr><td align="center">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 500px;">
                            <tr><td style="background: #95a5a6; padding: 30px; text-align: center;">
                                <h1 style="margin: 0; color: #fff; font-size: 20px; font-weight: 600;">📭 无变化</h1>
                            </td></tr>
                            <tr><td style="padding: 30px; text-align: center;">
                                <p style="color: #666; font-size: 15px;">{today} 暂无新公告</p>
                                <p style="color: #999; font-size: 12px; margin-top: 15px;">下次检查: 10分钟后</p>
                            </td></tr>
                        </table>
                    </td></tr>
                </table>
            </body>
            </html>
            """
            subject = f"【无新公告】{today}"
            return self.send(subject, html, text_content)
        
        # 生成纯文本摘要
        text_summary = f"今日 {len(news_items)} 条新公告:\n"
        for i, item in enumerate(news_items[:3], 1):
            display_title = item.ai_title if item.ai_title else item.title
            text_summary += f"{i}. {item.emoji} {display_title}\n"
        if len(news_items) > 3:
            text_summary += f"... 还有 {len(news_items)-3} 条\n"
        text_summary += f"\n查看详情: https://jyj.suqian.gov.cn/sjyj/tzgg/list.shtml"
        
        news_cards = ""
        for i, item in enumerate(news_items, 1):
            full_url = f"https://jyj.suqian.gov.cn{item.url}" if not item.url.startswith('http') else item.url
            display_title = item.ai_title if item.ai_title else item.title
            
            ai_summary_html = ""
            if item.ai_summary:
                ai_summary_html = f"""
                <div style="margin-top: 10px; padding: 10px; background: #f0f7ff; border-radius: 8px; border-left: 3px solid #667eea;">
                    <span style="color: #667eea; font-size: 12px; font-weight: 600;">🤖 AI摘要:</span>
                    <span style="color: #555; font-size: 13px; margin-left: 5px;">{item.ai_summary}</span>
                </div>
                """
            
            news_cards += f"""
            <div style="background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 15px; border: 1px solid #e8e8e8;">
                <div style="display: flex; align-items: center; margin-bottom: 12px;">
                    <span style="font-size: 20px; margin-right: 8px;">{item.emoji}</span>
                    <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">{item.date}</span>
                    <span style="color: #999; font-size: 12px; margin-left: 10px;">#{i}</span>
                </div>
                <a href="{full_url}" style="color: #1a73e8; text-decoration: none; font-size: 16px; font-weight: 500; line-height: 1.6; display: block;">
                    {display_title}
                </a>
                {ai_summary_html}
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 10px 0;">
                <tr><td align="center">
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
                        <tr><td style="padding: 20px; background: #fafafa;">{news_cards}</td></tr>
                    </table>
                </td></tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【新公告】今日{len(news_items)}条"
        return self.send(subject, html, text_summary)
    
    def send_report(self, stats: dict) -> bool:
        """发送述职报告"""
        today = beijing_strftime("%Y-%m-%d")
        now = beijing_strftime("%H:%M:%S")
        
        try:
            start = datetime.fromisoformat(stats['start_time'])
            runtime = beijing_now() - start
            runtime_str = f"{runtime.days}天{runtime.seconds//3600}小时{(runtime.seconds//60)%60}分"
        except:
            runtime_str = "未知"
        
        today_total = stats['today']['total_today']
        notified = stats['today']['notified']
        urgent = stats['today'].get('urgent', 0)
        
        text_summary = f"{today} 运行日报\n\n"
        text_summary += f"📊 今日公告: {today_total}条"
        if today_total > 0:
            text_summary += f" (已推送{notified}条)"
            if urgent > 0:
                text_summary += f" 紧急{urgent}条"
        text_summary += "\n"
        text_summary += f"⏱️ 运行时长: {runtime_str}\n"
        text_summary += f"✅ 系统运行正常"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 10px 0;">
                <tr><td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); max-width: 600px;">
                        <tr>
                            <td style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); padding: 35px 20px; text-align: center;">
                                <div style="margin-bottom: 12px;">
                                    <span style="display: inline-block; background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 11px; color: #fff;">运行日报</span>
                                </div>
                                <h1 style="margin: 0; color: #fff; font-size: 24px; font-weight: 600;">系统述职报告</h1>
                            </td>
                        </tr>
                        <tr><td style="padding: 20px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td width="50%" style="padding: 8px;">
                                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; text-align: center; color: #fff;">
                                            <div style="font-size: 32px; font-weight: bold;">{today_total}</div>
                                            <div style="font-size: 12px; opacity: 0.9; margin-top: 5px;">今日公告</div>
                                        </div>
                                    </td>
                                    <td width="50%" style="padding: 8px;">
                                        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; padding: 20px; text-align: center; color: #fff;">
                                            <div style="font-size: 32px; font-weight: bold;">{notified}</div>
                                            <div style="font-size: 12px; opacity: 0.9; margin-top: 5px;">已推送</div>
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
                        </td></tr>
                        <tr><td style="padding: 20px; background: #f8f9fa; text-align: center; color: #999; font-size: 12px;">
                            <p style="margin: 0;">报告生成时间: {today} {now}</p>
                        </td></tr>
                    </table>
                </td></tr>
            </table>
        </body>
        </html>
        """
        
        subject = f"【运行日报】{today} 公告{today_total}条"
        return self.send(subject, html, text_summary)


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
        
        elif task.email_type == EmailType.URGENT and task.news_items:
            # 紧急通知立即发送
            for item in task.news_items:
                self.logger.info(f"🚨 发送紧急通知: {item.title[:30]}...")
                if self.sender.send_urgent_notification(item):
                    self.data_store.mark_notified([item])
                    self.logger.info(f"✅ 紧急通知发送成功")
                else:
                    self.logger.error(f"❌ 紧急通知发送失败")
        
        elif task.email_type == EmailType.NEWS and task.news_items is not None:
            # 分离紧急、特殊和普通通知
            urgent_items = [item for item in task.news_items if item.is_urgent]
            special_items = [item for item in task.news_items if item.is_special and not item.is_urgent]
            normal_items = [item for item in task.news_items if not item.is_special and not item.is_urgent]
            
            # 紧急通知单独发送（已经在上面的URGENT类型中处理）
            
            # 特殊通知单独发送
            for item in special_items:
                self.logger.info(f"🔔 发送特殊通知: {item.title[:30]}...")
                if self.sender.send_urgent_notification(item):
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
        self.title_generator = SmartTitleGenerator(logger)
        self.ai_summarizer = AISummarizer(logger)
        self.running = True
        self.last_check_time = 0
        self.last_report_time = 0
        self.last_urgent_check = 0
        self._executor = ThreadPoolExecutor(max_workers=5)
    
    def _is_in_runtime(self) -> bool:
        now = beijing_now()
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
                next_start = beijing_now().replace(hour=RUN_START_HOUR, minute=0, second=0)
                if next_start < beijing_now():
                    next_start += timedelta(days=1)
                wait_seconds = (next_start - beijing_now()).total_seconds()
                self.logger.info(f"⏰ 非运行时间，等待至 {RUN_START_HOUR}:00 (约{wait_seconds/3600:.1f}小时)")
                time.sleep(min(wait_seconds, 3600))
                continue
            
            # 执行检查
            if current_time - self.last_check_time >= CHECK_INTERVAL:
                self._do_check()
            
            # 紧急关键词检查（每分钟）
            if current_time - self.last_urgent_check >= URGENT_KEYWORDS_INTERVAL:
                self._do_urgent_check()
            
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
            
            # 使用线程池并行处理AI生成
            futures = []
            for item in new_items:
                if not item.ai_title:  # 只对新公告生成
                    future = self._executor.submit(self._process_item_ai, item)
                    futures.append(future)
            
            # 等待所有AI处理完成
            for future in as_completed(futures):
                try:
                    future.result(timeout=30)
                except Exception as e:
                    self.logger.error(f"❌ AI处理失败: {e}")
            
            # 提交邮件任务
            task = EmailTask(
                email_type=EmailType.NEWS,
                news_items=new_items
            )
            self.email_queue.put(task)
            
            # 提交附件下载任务
            for item in new_items:
                if item.is_special and item.attachments:
                    download_task = DownloadTask(item=item)
                    self.download_queue.put(download_task)
        else:
            self.logger.info("📭 暂无新公告")
        
        self.data_store.save()
    
    def _process_item_ai(self, item: NewsItem):
        """处理单个公告的AI生成"""
        try:
            # 生成智能标题和emoji
            ai_title, emoji = self.title_generator.generate_title(item)
            item.ai_title = ai_title
            item.emoji = emoji
            
            # 生成AI摘要
            if AI_ENABLED and not item.ai_summary:
                summary = self.ai_summarizer.summarize(item.title)
                if summary:
                    item.ai_summary = summary
            
            # 更新数据存储
            self.data_store.save()
        except Exception as e:
            self.logger.error(f"❌ 处理公告AI失败: {e}")
    
    def _do_urgent_check(self):
        """紧急关键词检查"""
        self.last_urgent_check = time.time()
        
        try:
            news = self.fetcher.fetch()
            today = beijing_strftime("%Y-%m-%d")
            
            # 检查今日紧急公告
            urgent_items = []
            for item in news:
                if item.date == today and item.is_urgent:
                    # 检查是否已经通知过
                    key = f"{item.date}|{item.title}"
                    if key not in self.data_store.all_news or not self.data_store.all_news[key].notified:
                        urgent_items.append(item)
            
            if urgent_items:
                self.logger.info(f"🚨 发现 {len(urgent_items)} 条紧急公告，立即推送！")
                
                # 立即处理AI生成
                for item in urgent_items:
                    self._process_item_ai(item)
                
                # 立即发送邮件
                task = EmailTask(
                    email_type=EmailType.URGENT,
                    news_items=urgent_items
                )
                self.email_queue.put(task)
        except Exception as e:
            self.logger.error(f"❌ 紧急检查失败: {e}")
    
    def _do_report(self):
        self.logger.info("📊 准备发送述职报告...")
        self.last_report_time = time.time()
        
        task = EmailTask(email_type=EmailType.REPORT)
        self.email_queue.put(task)
    
    def stop(self):
        self.running = False
        self._executor.shutdown(wait=False)


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
        
        self.email_worker = EmailWorker(self.email_queue, self.data_store, self.logger)
        self.download_worker = AttachmentDownloader(self.download_queue, self.data_store, self.logger)
        self.monitor_thread = MonitorThread(self.data_store, self.email_queue, self.download_queue, self.logger)
        self.watchdog = WatchdogThread(self.monitor_thread, self.email_worker, self.download_worker, self.logger)
        
        self.running = True
    
    def send_test_email(self):
        self.logger.info("📧 发送测试邮件...")
        task = EmailTask(email_type=EmailType.TEST)
        self.email_queue.put(task)
    
    def run(self):
        self.logger.info("=" * 60)
        self.logger.info("🚀 宿迁教育局公告监控系统 - AI智能高级版 启动")
        self.logger.info(f"📍 监控地址: {MONITOR_URL}")
        self.logger.info(f"⏱️  运行时间: {RUN_START_HOUR}:00 - {RUN_END_HOUR}:00")
        self.logger.info(f"📊 检查间隔: {CHECK_INTERVAL//60}分钟")
        self.logger.info(f"🚨 紧急检查: {URGENT_KEYWORDS_INTERVAL}秒")
        self.logger.info(f"📧 收件人: {len(TO_EMAILS)}个")
        self.logger.info("🔧 AI智能标题 | 本地学习 | 紧急推送 | 高性能并发")
        self.logger.info("=" * 60)
        
        self.send_test_email()
        
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
