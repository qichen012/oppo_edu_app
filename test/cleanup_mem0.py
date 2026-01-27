"""
清理 Mem0 数据库，删除除了指定用户外的所有记忆
"""
import subprocess
import sys

# 保留的用户ID
KEEP_USER_ID = "user_bupt_01"

def get_all_users():
    """获取所有用户ID"""
    cmd = [
        "docker", "exec", "mem0-dev-postgres-1",
        "psql", "-U", "postgres", "-d", "postgres", "-t", "-c",
        "SELECT DISTINCT payload->>'user_id' as user_id FROM memories WHERE payload->>'user_id' IS NOT NULL;"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ 查询失败: {result.stderr}")
        return []
    
    users = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    return users


def count_memories(user_id=None):
    """统计记忆数量"""
    if user_id:
        sql = f"SELECT COUNT(*) FROM memories WHERE payload->>'user_id' = '{user_id}';"
    else:
        sql = "SELECT COUNT(*) FROM memories;"
    
    cmd = [
        "docker", "exec", "mem0-dev-postgres-1",
        "psql", "-U", "postgres", "-d", "postgres", "-t", "-c", sql
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return int(result.stdout.strip())
    return 0


def delete_user_memories(user_id):
    """删除指定用户的所有记忆"""
    sql = f"DELETE FROM memories WHERE payload->>'user_id' = '{user_id}';"
    
    cmd = [
        "docker", "exec", "mem0-dev-postgres-1",
        "psql", "-U", "postgres", "-d", "postgres", "-c", sql
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def main():
    print("🔍 正在查询所有用户...")
    users = get_all_users()
    
    if not users:
        print("❌ 没有找到任何用户")
        return
    
    print(f"\n📋 当前数据库中的用户: {users}")
    print(f"✅ 保留用户: {KEEP_USER_ID}")
    
    # 需要删除的用户
    users_to_delete = [u for u in users if u != KEEP_USER_ID]
    
    if not users_to_delete:
        print(f"\n✅ 没有需要删除的用户（只有 {KEEP_USER_ID}）")
        return
    
    print(f"\n⚠️  将要删除以下用户的所有记忆:")
    for user in users_to_delete:
        count = count_memories(user)
        print(f"  - {user}: {count} 条记忆")
    
    # 确认
    total_before = count_memories()
    keep_count = count_memories(KEEP_USER_ID)
    
    print(f"\n📊 删除前统计:")
    print(f"  总记忆数: {total_before}")
    print(f"  {KEEP_USER_ID} 的记忆: {keep_count}")
    print(f"  将删除: {total_before - keep_count} 条")
    
    confirm = input(f"\n⚠️  确认删除？(yes/no): ")
    
    if confirm.lower() != 'yes':
        print("❌ 操作已取消")
        return
    
    # 执行删除
    print("\n🗑️  开始删除...")
    for user in users_to_delete:
        print(f"  删除 {user} 的记忆...", end=" ")
        if delete_user_memories(user):
            print("✅")
        else:
            print("❌")
    
    # 验证结果
    print("\n📊 删除后统计:")
    remaining_users = get_all_users()
    total_after = count_memories()
    
    print(f"  剩余用户: {remaining_users}")
    print(f"  剩余记忆总数: {total_after}")
    print(f"  {KEEP_USER_ID} 的记忆: {count_memories(KEEP_USER_ID)}")
    
    print("\n✅ 清理完成！")


if __name__ == "__main__":
    main()
