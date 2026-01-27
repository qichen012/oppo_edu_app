import pandas as pd
import numpy as np
import random
import time
import feedparser
import requests
from ddgs import DDGS


# ===========================
# 1. 核心评分配置
# ===========================
WEIGHT_CLICK = 0.7
WEIGHT_TIME = 0.3
MAX_DURATION = 300.0  # 秒


def score_sigmoid(clicks, duration, w_click=0.6, w_time=0.4):
    """
    使用 Sigmoid 函数计算用户行为得分
    特点：非线性极强，自动过滤短时误触，自动平滑长时挂机
    """
    # 点击权重：渐进公式 1 - 1/(1+x)
    click_norm = 1 - (1 / (1 + clicks))
    
    # 时间权重：Sigmoid S型曲线
    midpoint = 60.0  # 60秒作为中心点
    slope = 0.05     # 曲线陡峭程度
    time_norm = 1 / (1 + np.exp(-slope * (duration - midpoint)))
    
    # 综合打分
    final_score = (w_click * click_norm + w_time * time_norm) * 100
    return round(final_score, 2)


def generate_user_keywords(user_history):
    """
    根据用户历史行为生成关键词画像
    输入格式: [{'title': 'xxx', 'clicks': 3, 'duration': 300, 'tags': ['Python', 'Tech']}]
    """
    if not user_history:
        return []
    
    df_logs = pd.DataFrame(user_history)
    
    # 计算每条内容的得分
    df_logs['score'] = df_logs.apply(
        lambda row: score_sigmoid(row['clicks'], row['duration']), axis=1
    )
    
    # 聚合到标签
    tag_scores = {}
    for _, row in df_logs.iterrows():
        score = row['score']
        tags = row['tags']
        
        for tag in tags:
            if tag in tag_scores:
                tag_scores[tag] += score
            else:
                tag_scores[tag] = score
    
    # 按分数排序
    sorted_keywords = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_keywords


def select_keywords_with_randomness(user_profile, limit=3, epsilon=0.1):
    """
    从用户画像中选择关键词，带有随机性避免推荐单一化
    """
    if not user_profile:
        return []
    
    selected = [user_profile[0][0]]  # 永远保留第一名
    pool = user_profile[1:]  # 剩下的池子
    
    while len(selected) < limit and pool:
        if random.random() < epsilon:
            # 随机选择
            choice = random.choice(pool)
        else:
            # 选分数最高的
            choice = pool[0]
        
        selected.append(choice[0])
        pool.remove(choice)
    
    return selected


# ===========================
# 2. 搜索引擎模块
# ===========================

def search_ddgs(keywords, limit=3):
    """
    使用 DuckDuckGo 搜索
    """
    print(f"📡 [DuckDuckGo] 收到关键词列表: {keywords}")
    results = []
    
    try:
        with DDGS(timeout=20) as ddgs:
            for key in keywords:
                if len(results) >= limit:
                    break
                
                print(f"   -> 正在搜索: '{key}' ...", end=" ")
                
                try:
                    gen = ddgs.text(
                        key,
                        region='zh-CN',
                        max_results=3,
                        backend='html',
                        timelimit='w'
                    )
                    
                    found_items = list(gen)
                    
                    if found_items:
                        print(f"✅ 获取到 {len(found_items)} 条")
                        for res in found_items:
                            results.append({
                                "title": res['title'],
                                "url": res['href'],
                                "snippet": res['body']
                            })
                            if len(results) >= limit:
                                break
                    else:
                        print("⚠️ 无结果")
                
                except Exception as inner_e:
                    print(f"⚠️ 跳过 (原因: {inner_e})")
                
                time.sleep(1)  # 防止请求过快
                
    except Exception as e:
        print(f"❌ 搜索错误: {e}")
        return [
            {"title": "本地保底数据：Python 学习路线", "url": "#", "snippet": "网络不可用..."},
            {"title": "本地保底数据：2026 科技趋势", "url": "#", "snippet": "网络不可用..."}
        ]
    
    return results


def search_rss(keywords, limit=10):
    """
    使用 RSS 源搜索相关内容
    """
    print(f"📡 [RSS启动] 正在扫描: {keywords}")
    
    # 关键词映射表
    KEYWORD_MAP = {
        'Coding':   ['编程', '代码', '开发', '程序员', '源码', 'Coding'],
        'Python':   ['Python', '爬虫', '数据分析', 'Pandas', '自动化', '脚本'],
        'Java':     ['Java', 'Spring', 'JVM', '后端', '微服务', '并发'],
        'Go':       ['Go语言', 'Golang', '云原生', '微服务', 'Gin'],
        'Frontend': ['前端', 'Web', 'JavaScript', 'Vue', 'React', 'CSS', 'Node'],
        'Tech':     ['科技', '技术', '黑科技', '创新', 'Tech'],
        'AI':       ['AI', '人工智能', '大模型', 'ChatGPT', '生成式', 'AIGC', 'LLM'],
        'Hardware': ['硬件', '显卡', 'GPU', '芯片', '半导体', '处理器', 'Hardware'],
        'Mobile':   ['手机', '安卓', 'Android', 'iOS', '鸿蒙', 'App', '智能手机'],
        'Apple':    ['Apple', '苹果', 'iPhone', 'Mac', 'iPad', 'Vision Pro'],
        'Career':   ['职场', '面试', '招聘', '简历', '内推', '薪资', '大厂'],
        'Game':     ['游戏', '电竞', 'Steam', '原神', 'Switch', 'PS5', '黑神话'],
        'Music':    ['音乐', '歌曲', '演唱会', '专辑', 'Music'],
        'Jazz':     ['爵士', '蓝调', 'Jazz', '乐理']
    }
    
    # RSS 源列表
    rss_sources = [
        {"name": "OSChina", "url": "https://www.oschina.net/news/rss"},
        {"name": "InfoQ", "url": "https://feed.infoq.cn/"},
        {"name": "V2EX", "url": "https://www.v2ex.com/index.xml"},
        {"name": "Solidot", "url": "https://www.solidot.org/index.rss"},
        {"name": "IT之家", "url": "https://www.ithome.com/rss/"},
        {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
        {"name": "36氪", "url": "https://www.36kr.com/feed"},
        {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml"},
        {"name": "机核网", "url": "https://www.gcores.com/rss"},
        {"name": "少数派", "url": "https://sspai.com/feed"}
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    all_candidates = []
    
    for src in rss_sources:
        try:
            response = requests.get(src['url'], headers=headers, timeout=4)
            feed = feedparser.parse(response.text)
            
            if not feed.entries:
                continue
            
            count_per_source = 0
            
            for entry in feed.entries:
                title = entry.title
                
                # 关键词匹配
                is_match = False
                for user_key in keywords:
                    search_terms = KEYWORD_MAP.get(user_key, [user_key])
                    if any(term.lower() in title.lower() for term in search_terms):
                        is_match = True
                        break
                
                if is_match:
                    all_candidates.append({
                        "title": title,
                        "url": entry.link,
                        "source": src['name']
                    })
                    count_per_source += 1
                    
                    # 每个源最多贡献4条，防止某个源过于强势
                    if count_per_source >= 4:
                        break
                        
        except Exception as e:
            print(f"❌ {src['name']} 异常: {e}")
            continue
    
    print(f"📊 候选池共有 {len(all_candidates)} 条新闻")
    
    if not all_candidates:
        print("⚠️ 候选池为空，无法推荐")
        return []
    
    # 打乱顺序并返回结果
    random.shuffle(all_candidates)
    final_results = all_candidates[:limit]
    
    return final_results


# ===========================
# 3. 主要接口函数
# ===========================

def analyze_user_profile(user_history):
    """
    分析用户行为数据，生成用户画像
    """
    if not user_history:
        return {"status": "error", "message": "用户历史数据为空"}
    
    # 生成标签画像
    user_profile = generate_user_keywords(user_history)
    
    # 计算总体统计
    df_logs = pd.DataFrame(user_history)
    df_logs['score'] = df_logs.apply(
        lambda row: score_sigmoid(row['clicks'], row['duration']), axis=1
    )
    
    stats = {
        "total_interactions": len(user_history),
        "avg_score": round(df_logs['score'].mean(), 2),
        "avg_duration": round(df_logs['duration'].mean(), 2),
        "avg_clicks": round(df_logs['clicks'].mean(), 2),
        "top_score": round(df_logs['score'].max(), 2)
    }
    
    return {
        "status": "success",
        "user_profile": user_profile,
        "statistics": stats,
        "scored_content": df_logs[['title', 'score']].to_dict('records')
    }


def generate_recommendations(user_history, source='rss', limit=10, epsilon=0.1):
    """
    基于用户历史生成推荐内容
    """
    if not user_history:
        return {"status": "error", "message": "用户历史数据为空"}
    
    # 生成用户画像
    user_profile = generate_user_keywords(user_history)
    if not user_profile:
        return {"status": "error", "message": "无法生成用户画像"}
    
    # 选择关键词
    recommend_keywords = select_keywords_with_randomness(
        user_profile, limit=3, epsilon=epsilon
    )
    
    # 根据来源搜索
    if source == 'ddgs':
        results = search_ddgs(recommend_keywords, limit=limit)
    else:  # default to rss
        results = search_rss(recommend_keywords, limit=limit)
    
    return {
        "status": "success",
        "keywords_used": recommend_keywords,
        "user_profile_summary": user_profile[:5],  # 只返回前5个标签
        "recommendations": results,
        "source": source
    }