"""对话管理模块
管理用户与 AI 的对话，维护对话历史和上下文记忆。

可选降级：
- 设置环境变量 `CHAT_DISABLE_LLM=1`：不调用外部 LLM，直接返回规则化回复（方便离线/测试）。
- 设置环境变量 `CHAT_FALLBACK_ON_LLM_ERROR=1`：LLM 调用失败时不抛异常，返回降级回复。
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from openai import OpenAI
from skill.config import (
    ZHIZENGZENG_BASE_URL,
    ZHIZENGZENG_API_KEY,
    MODEL_NAME,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
)

def _select_provider() -> str:
    """选择聊天模型提供方。

    优先级：
    1) 环境变量 CHAT_PROVIDER=zhizengzeng|deepseek
    2) 若配置了 ZHIZENGZENG_API_KEY，则默认用 zhizengzeng
    3) 否则用 deepseek
    """
    forced = (os.getenv("CHAT_PROVIDER") or "").strip().lower()
    if forced in {"zhizengzeng", "deepseek"}:
        return forced
    if (ZHIZENGZENG_API_KEY or "").strip():
        return "zhizengzeng"
    return "deepseek"


def _create_client_and_model(provider: str) -> tuple[OpenAI, str]:
    if provider == "zhizengzeng":
        if not (ZHIZENGZENG_API_KEY or "").strip():
            raise RuntimeError("Missing ZHIZENGZENG_API_KEY")
        return OpenAI(api_key=ZHIZENGZENG_API_KEY, base_url=ZHIZENGZENG_BASE_URL), MODEL_NAME

    # deepseek
    if not (DEEPSEEK_API_KEY or "").strip():
        raise RuntimeError("Missing DEEPSEEK_API_KEY")
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL), DEEPSEEK_MODEL

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
        def _fallback_reply() -> str:
            # 尽量短且稳定，避免污染后续摘要
            return (
                "（当前未启用大模型或大模型不可用）\n"
                f"我已收到你的问题：{user_message}\n"
                "你可以继续追问；待 LLM 恢复后我会给出更完整的回答。"
            )

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
        
        assistant_message: Optional[str] = None
        provider: Optional[str] = None
        model: Optional[str] = None
        try:
            if os.getenv("CHAT_DISABLE_LLM") == "1":
                assistant_message = _fallback_reply()
            else:
                provider = _select_provider()
                client, model = _create_client_and_model(provider)

                response = client.chat.completions.create(
                    model=model,
                    messages=api_messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                assistant_message = response.choices[0].message.content

        except Exception as e:
            provider_hint = f"provider={provider or 'unknown'}, model={model or 'unknown'}"
            error_msg = f"对话失败({provider_hint}): {str(e)}"
            print(error_msg)
            if os.getenv("CHAT_FALLBACK_ON_LLM_ERROR") == "1":
                assistant_message = _fallback_reply()
            else:
                # 移除刚才添加的用户消息（因为对话失败了）
                self.messages.pop()
                raise Exception(error_msg)

        # 添加 AI 回复到历史
        self.messages.append({
            "role": "assistant",
            "content": assistant_message or "",
            "timestamp": datetime.now().isoformat()
        })

        # 保存历史
        self._save_history()

        return assistant_message or ""
    
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
