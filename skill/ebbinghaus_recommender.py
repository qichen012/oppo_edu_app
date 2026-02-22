import math
import time
from typing import List, Dict, Any

def recommend_ebbinghaus_brief(user_history: List[Dict[str, Any]], total_briefs: int, top_k: int = 1) -> List[int]:
    """
    基于改进版艾宾浩斯遗忘曲线的简报推荐算法（引入间隔重复机制）。
    
    Args:
        user_history: 用户历史列表，例如 [{"brief_id": 1, "last_view_time": 1670000000}]
        total_briefs: 简报总数（用于圈定推荐池范围）
        top_k: 返回的推荐数量
    Returns:
        推荐的简报编号列表（按推荐程度从高到低排序）
    """
    now = time.time()
    
    # 1. 聚合用户历史数据：记录每个简报的最后访问时间和复习次数
    brief_stats = {}
    for item in user_history:
        b_id = item.get("brief_id")
        v_time = item.get("last_view_time")
        if b_id is not None and v_time is not None:
            if b_id not in brief_stats:
                brief_stats[b_id] = {"last_view_time": v_time, "review_count": 1}
            else:
                # 更新为最近的一次访问时间，并累加复习次数
                if v_time > brief_stats[b_id]["last_view_time"]:
                    brief_stats[b_id]["last_view_time"] = v_time
                brief_stats[b_id]["review_count"] += 1

    scores = []
    
    # 2. 计算每个简报的推荐分数
    for brief_id in range(total_briefs):
        if brief_id in brief_stats:
            stats = brief_stats[brief_id]
            # 距离上次复习经过的小时数
            t_hours = max(0, (now - stats["last_view_time"]) / 3600.0)
            review_count = stats["review_count"]
            
            # 改进点A：记忆强度 S 随复习次数增加而增大
            # 初始记忆强度为 24（小时），每次复习记忆强度增加 1.5 倍
            base_memory_strength = 24.0 
            memory_strength = base_memory_strength * (1.5 ** (review_count - 1))
            
            # 改进点B：遗忘曲线公式 R = exp(-t / S)
            retention = math.exp(-t_hours / memory_strength)
            
            # 推荐分数：越容易遗忘（保持率越低），越需要复习，分数越高
            need_review_score = 1.0 - retention
            scores.append((brief_id, need_review_score))
        else:
            # 改进点C：对未看过的简报给予一个基础的“探索分数”
            # 设为 0.6，意味着优先推荐遗忘率超过 60% 的已学内容，其次推荐新内容
            exploration_score = 0.6
            scores.append((brief_id, exploration_score))
            
    # 3. 按分数降序排序，取 Top-K
    scores.sort(key=lambda x: x[1], reverse=True)
    recommended_ids = [item[0] for item in scores[:top_k]]
    
    return recommended_ids
