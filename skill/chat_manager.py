"""
对话管理模块
管理用户与 AI 的对话，维护对话历史和上下文记忆
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from openai import OpenAI
from skill.config import DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL


# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# 对话历史存储目录
CHAT_HISTORY_DIR = os.path.join("data", "chat_histories")
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


class ChatManager:
    """对话管理器，负责维护对话历史和生成回复"""
    
    def __init__(self, user_id: str):
        """
        初始化对话管理器
        
        Args:
            user_id: 用户ID，用于标识不同用户的对话历史
        """
        self.user_id = user_id
        self.history_file = os.path.join(CHAT_HISTORY_DIR, f"{user_id}_chat.json")
        self.messages = self._load_history()
    
    def _load_history(self) -> List[Dict[str, str]]:
        """从文件加载对话历史"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('messages', [])
            except Exception as e:
                print(f"加载对话历史失败: {e}")
                return []
        return []
    
    def _save_history(self):
        """保存对话历史到文件"""
        try:
            data = {
                'user_id': self.user_id,
                'last_updated': datetime.now().isoformat(),
                'messages': self.messages
            }
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存对话历史失败: {e}")
    
    def chat(self, user_message: str, system_prompt: Optional[str] = None) -> str:
        """
        发送用户消息并获取 AI 回复
        
        Args:
            user_message: 用户的消息内容
            system_prompt: 可选的系统提示词，用于定制 AI 行为
            
        Returns:
            AI 的回复内容
        """
        # 添加用户消息到历史
        self.messages.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        
        # 构建发送给 API 的消息列表
        api_messages = []
        
        # 如果有系统提示词，添加到开头
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        
        # 添加历史消息（最近20轮对话）
        for msg in self.messages[-40:]:  # 最多保留20轮对话（40条消息）
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        try:
            # 调用 DeepSeek API
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=api_messages,
                temperature=0.7,
                max_tokens=2000
            )
            
            assistant_message = response.choices[0].message.content
            
            # 添加 AI 回复到历史
            self.messages.append({
                "role": "assistant",
                "content": assistant_message,
                "timestamp": datetime.now().isoformat()
            })
            
            # 保存历史
            self._save_history()
            
            return assistant_message
            
        except Exception as e:
            error_msg = f"对话失败: {str(e)}"
            print(error_msg)
            # 移除刚才添加的用户消息（因为对话失败了）
            self.messages.pop()
            raise Exception(error_msg)
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """
        获取对话历史
        
        Args:
            limit: 限制返回的消息数量，None 表示返回全部
            
        Returns:
            对话历史列表
        """
        if limit:
            return self.messages[-limit:]
        return self.messages
    
    def clear_history(self):
        """清空对话历史"""
        self.messages = []
        self._save_history()
    
    def delete_last_messages(self, count: int = 2):
        """
        删除最后几条消息（用于撤回）
        
        Args:
            count: 要删除的消息数量，默认2（一问一答）
        """
        if len(self.messages) >= count:
            self.messages = self.messages[:-count]
            self._save_history()


def create_chat_session(user_id: str) -> ChatManager:
    """
    创建或获取用户的对话会话
    
    Args:
        user_id: 用户ID
        
    Returns:
        ChatManager 实例
    """
    return ChatManager(user_id)
