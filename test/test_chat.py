"""
测试 AI 对话接口
演示如何使用带上下文记忆的对话功能
"""

import requests
import json

# 服务器地址
BASE_URL = "http://localhost:8001"

def test_chat():
    """测试对话功能"""
    
    # 用户ID（每个用户有独立的对话历史）
    user_id = "user_test_001"
    
    print("=" * 60)
    print("测试 AI 对话接口（带上下文记忆）")
    print("=" * 60)
    
    # 第一轮对话
    print("\n【第一轮对话】")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "user_id": user_id,
            "message": "你好！我想了解一下北京邮电大学的信息工程专业。"
        }
    )
    result = response.json()
    print(f"用户: {result['user_message']}")
    print(f"AI: {result['ai_response']}")
    
    # 第二轮对话（测试上下文记忆）
    print("\n【第二轮对话】")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "user_id": user_id,
            "message": "这个专业的就业前景怎么样？"  # AI 应该知道"这个专业"指的是信息工程
        }
    )
    result = response.json()
    print(f"用户: {result['user_message']}")
    print(f"AI: {result['ai_response']}")
    
    # 第三轮对话
    print("\n【第三轮对话】")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "user_id": user_id,
            "message": "需要学习哪些课程？"
        }
    )
    result = response.json()
    print(f"用户: {result['user_message']}")
    print(f"AI: {result['ai_response']}")
    
    # 查看对话历史
    print("\n【查看对话历史】")
    response = requests.post(
        f"{BASE_URL}/chat/history",
        json={
            "user_id": user_id,
            "limit": 10  # 最近10条消息
        }
    )
    history_result = response.json()
    print(f"总共 {history_result['total_messages']} 条消息")
    for i, msg in enumerate(history_result['history'], 1):
        print(f"{i}. [{msg['role']}]: {msg['content'][:50]}...")


def test_chat_with_system_prompt():
    """测试带自定义系统提示词的对话"""
    
    user_id = "user_test_002"
    
    print("\n" + "=" * 60)
    print("测试自定义 AI 角色")
    print("=" * 60)
    
    # 使用系统提示词定制 AI 行为
    system_prompt = "你是一位资深的教育咨询专家，专门帮助学生选择专业和规划学业。请用友好、专业的语气回答问题。"
    
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "user_id": user_id,
            "message": "我对计算机和通信都感兴趣，该选什么专业？",
            "system_prompt": system_prompt
        }
    )
    result = response.json()
    print(f"用户: {result['user_message']}")
    print(f"AI: {result['ai_response']}")


def test_clear_history():
    """测试清空对话历史"""
    
    user_id = "user_test_001"
    
    print("\n" + "=" * 60)
    print("测试清空对话历史")
    print("=" * 60)
    
    response = requests.post(
        f"{BASE_URL}/chat/clear",
        json={
            "user_id": user_id
        }
    )
    result = response.json()
    print(f"结果: {result['message']}")
    
    # 验证历史已清空
    response = requests.post(
        f"{BASE_URL}/chat/history",
        json={
            "user_id": user_id
        }
    )
    history_result = response.json()
    print(f"清空后的消息数: {history_result['total_messages']}")


if __name__ == "__main__":
    try:
        # 运行测试
        test_chat()
        test_chat_with_system_prompt()
        test_clear_history()
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("错误: 无法连接到服务器，请先启动服务器:")
        print("  cd /Users/xwj/Desktop/oppo_edu_app")
        print("  python run/server.py")
    except Exception as e:
        print(f"测试失败: {e}")
