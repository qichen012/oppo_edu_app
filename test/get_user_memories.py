"""
获取指定用户的所有记忆和知识图谱
"""
import requests
import json
import os

# 禁用代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

USER_ID = "user_bupt_01"
AGENT_ID = "pdf_processor"
MEM0_BASE_URL = "http://localhost:8888"

# 创建禁用代理的 session
session = requests.Session()
session.trust_env = False

def get_all_memories():
    """通过 Mem0 API 获取所有记忆"""
    print(f"🔍 正在获取 {USER_ID} 的所有记忆...\n")
    
    try:
        response = session.get(
            f"{MEM0_BASE_URL}/memories",
            params={
                "user_id": USER_ID,
                "agent_id": AGENT_ID
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # 提取记忆列表
            memories = data.get('results', [])
            relations = data.get('relations', [])
            
            print(f"📚 找到 {len(memories)} 条记忆:\n")
            print("=" * 80)
            
            for i, mem in enumerate(memories, 1):
                memory_id = mem.get('id', 'N/A')
                memory_text = mem.get('memory', 'N/A')
                created_at = mem.get('created_at', 'N/A')
                
                print(f"\n记忆 #{i}")
                print(f"ID: {memory_id}")
                print(f"创建时间: {created_at}")
                print(f"内容: {memory_text}")
                print("-" * 80)
            
            # 显示知识图谱
            print(f"\n\n🕸️ 知识图谱关系 ({len(relations)} 条):\n")
            print("=" * 80)
            
            if relations:
                for rel in relations:
                    source = rel.get('source', 'N/A')
                    relationship = rel.get('relationship', 'N/A')
                    target = rel.get('target', 'N/A')
                    print(f"{source} --[{relationship}]--> {target}")
            else:
                print("暂无图谱关系")
            
            # 保存到文件
            output_file = f"data/user_memories/{USER_ID}_memories.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"\n\n💾 完整数据已保存到: {output_file}")
            
            return data
        else:
            print(f"❌ 请求失败 (状态码: {response.status_code})")
            print(f"响应: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 获取记忆出错: {e}")
        return None


def search_memories(query):
    """搜索相关记忆"""
    print(f"\n\n🔎 搜索查询: '{query}'\n")
    
    try:
        response = session.post(
            f"{MEM0_BASE_URL}/search",
            json={
                "query": query,
                "user_id": USER_ID,
                "agent_id": AGENT_ID,
                "limit": 50
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            memories = data.get('results', [])
            
            print(f"✅ 找到 {len(memories)} 条相关记忆:\n")
            for i, item in enumerate(memories, 1):
                content = item.get('memory', 'N/A')
                score = item.get('score', 0)
                print(f"{i}. [相似度: {score:.4f}] {content}")
            
            relations = data.get('relations', [])
            if relations:
                print(f"\n🕸️ 相关图谱关系:")
                for rel in relations:
                    s = rel.get('source', 'N/A')
                    r = rel.get('relationship', 'N/A')
                    d = rel.get('destination', 'N/A')
                    print(f"  {s} --({r})--> {d}")
            
            return data
        else:
            print(f"❌ 搜索失败 (状态码: {response.status_code})")
            return None
            
    except Exception as e:
        print(f"❌ 搜索出错: {e}")
        return None


if __name__ == "__main__":
    # 1. 获取所有记忆
    all_data = get_all_memories()
    
    # 2. 可选：执行搜索
    print("\n" + "=" * 80)
    search_query = input("\n输入搜索关键词（直接回车跳过）: ").strip()
    
    if search_query:
        search_memories(search_query)
