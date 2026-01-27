"""
Mem0 记忆管理模块
负责将知识卡片存储到 Mem0 长期记忆系统中
"""

import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional


# ===== Mem0 服务配置 =====
MEM0_BASE_URL = "http://localhost:8888"
DEFAULT_USER_ID = "user_bupt_01"


def upload_card_to_mem0(
    card_data: Dict[str, Any],
    user_id: str = DEFAULT_USER_ID,
    agent_id: str = "pdf_processor",
    run_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    将知识卡片上传到 Mem0
    
    Args:
        card_data: 卡片的 JSON 数据
        user_id: 用户ID，默认为 user_bupt_01
        agent_id: 代理ID，默认为 pdf_processor
        run_id: 运行ID，可选
        
    Returns:
        上传结果的响应数据，失败时返回 None
    """
    # 生成当前时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建简洁的学习内容描述（参考成功测试用例的格式）
    title = card_data.get("header", {}).get("title", "未命名笔记")
    category = card_data.get("meta", {}).get("category", "知识")
    summary = card_data.get("body", {}).get("summary", "")
    
    # 使用简洁格式，类似测试文件中的成功案例
    content = f"我今天学习了关于'{title}'的知识。分类：{category}。主要内容：{summary}"
    
    # 如果内容过长，截断到合理长度（避免处理时间过长）
    if len(content) > 500:
        content = content[:497] + "..."
    
    # 如果没有指定 run_id，使用时间戳
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d")
    
    # 构建上传数据
    payload = {
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ],
        "user_id": user_id,
        "agent_id": agent_id,
        "run_id": run_id,
        "metadata": {
            "timestamp": timestamp,
            "category": card_data.get("meta", {}).get("category", "未分类"),
            "title": card_data.get("header", {}).get("title", ""),
            "card_data": json.dumps(card_data, ensure_ascii=False)
        }
    }
    
    # 调试日志：显示即将上传的 user_id
    print(f"🔍 准备上传到 Mem0 - user_id: {user_id}, agent_id: {agent_id}")
    print(f"📦 Payload 中的 user_id: {payload.get('user_id')}")
    
    try:
        # Mem0 需要时间生成 embeddings 和知识图谱，参考成功测试用例使用 180 秒超时
        response = requests.post(
            f"{MEM0_BASE_URL}/memories",
            json=payload,
            timeout=180
        )
        
        if response.status_code == 200:
            print(f"✅ 卡片已上传到 Mem0 (user_id: {user_id})")
            return response.json()
        else:
            print(f"⚠️ Mem0 上传失败 (状态码: {response.status_code}): {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"⚠️ Mem0 上传超时，但数据可能已在后台处理中...")
        return None
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到 Mem0 服务 ({MEM0_BASE_URL})，请确保 Docker 容器正在运行")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Mem0 请求错误: {e}")
        return None
    except Exception as e:
        print(f"❌ Mem0 上传出错: {e}")
        return None


def search_cards_in_mem0(
    query: str,
    user_id: str = DEFAULT_USER_ID,
    agent_id: str = "pdf_processor",
    run_id: Optional[str] = None
) -> Optional[list]:
    """
    在 Mem0 中搜索相关卡片
    
    Args:
        query: 搜索查询
        user_id: 用户ID
        agent_id: 代理ID
        run_id: 运行ID，可选
        
    Returns:
        搜索结果列表，失败时返回 None
    """
    payload = {
        "query": query,
        "user_id": user_id,
        "agent_id": agent_id,
        "run_id": run_id or "",
        "filters": {}
    }
    
    try:
        response = requests.post(
            f"{MEM0_BASE_URL}/search",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ 搜索成功，找到相关记忆")
            return response.json()
        else:
            print(f"⚠️ Mem0 搜索失败 (状态码: {response.status_code})")
            return None
            
    except Exception as e:
        print(f"❌ Mem0 搜索出错: {e}")
        return None


def get_all_cards_for_user(
    user_id: str = DEFAULT_USER_ID,
    agent_id: str = "pdf_processor",
    run_id: Optional[str] = None
) -> Optional[list]:
    """
    获取用户的所有卡片记忆
    
    Args:
        user_id: 用户ID
        agent_id: 代理ID
        run_id: 运行ID，可选
        
    Returns:
        所有记忆列表，失败时返回 None
    """
    params = {
        "user_id": user_id,
        "agent_id": agent_id,
        "run_id": run_id or ""
    }
    
    try:
        response = requests.get(
            f"{MEM0_BASE_URL}/memories",
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ 获取用户记忆成功")
            return response.json()
        else:
            print(f"⚠️ 获取记忆失败 (状态码: {response.status_code})")
            return None
            
    except Exception as e:
        print(f"❌ 获取记忆出错: {e}")
        return None
