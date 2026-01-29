import os
import json
import requests
from openai import OpenAI
from duckduckgo_search import DDGS
from datetime import datetime

# =================配置区域=================
# 1. DeepSeek API 配置
DEEPSEEK_API_KEY = "sk-d2c5fcabbec64ea19790f9c62d09473d"  # 【请在此处填入你的 DeepSeek Key】
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 2. GitHub 配置 (建议填写，否则每小时只能搜60次)
# 申请地址: https://github.com/settings/tokens (Classic Token 即可)
GITHUB_TOKEN = "" # 【可选：在此填入 GitHub Token】

# 3. 你的关键词库
KEYWORDS_DB = [
    {
        "topic": "Multi-Agent ",
        "query": "Multi-Agent",
        "type": "code" # 偏向找代码
    },
    {
        "topic": "RAG ",
        "query": "RAG",
        "type": "learning" # 偏向找教程
    },
    {
        "topic": "BUPT ",
        "query": "bupt",
        "type": "general"
    }
]
# =========================================

class SearchProvider:
    """负责从不同来源获取原始数据"""
    
    def __init__(self):
        self.ddgs = DDGS()
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {GITHUB_TOKEN}"

    def search_github(self, keyword, min_stars=50, limit=5):
        """搜索 GitHub 项目"""
        print(f"   [GitHub]正在搜索: {keyword}...")
        url = "https://api.github.com/search/repositories"
        # 构造查询：关键词 + 语言Python + Star数限制
        q = f"{keyword} language:python stars:>{min_stars}"
        params = {"q": q, "sort": "stars", "order": "desc", "per_page": limit}
        
        try:
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                results = []
                for item in items:
                    results.append({
                        "source": "GitHub",
                        "title": item['full_name'],
                        "url": item['html_url'],
                        "description": item['description'],
                        "stars": item['stargazers_count'],
                        "updated_at": item['updated_at'][:10]
                    })
                return results
            else:
                print(f"   [Error] GitHub API error: {resp.status_code}")
                return []
        except Exception as e:
            print(f"   [Error] GitHub connection failed: {e}")
            return []

    def search_web(self, keyword, limit=5):
        """搜索互联网 (DuckDuckGo)"""
        print(f"   [Web]正在搜索: {keyword}...")
        results = []
        try:
            # 使用 DDGS 进行文本搜索
            ddg_results = self.ddgs.text(keyword, max_results=limit)
            if ddg_results:
                for r in ddg_results:
                    results.append({
                        "source": "Web",
                        "title": r['title'],
                        "url": r['href'],
                        "description": r['body'],
                        "stars": "N/A",
                        "updated_at": "Unknown"
                    })
            return results
        except Exception as e:
            print(f"   [Error] Web search failed: {e}")
            return []

class DeepSeekAnalyst:
    """负责使用 LLM 清洗和总结数据"""
    
    def __init__(self, api_key, base_url):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def analyze_results(self, topic, raw_data):
        """将搜索结果喂给 DeepSeek 进行筛选和点评"""
        if not raw_data:
            return "未找到相关数据。"

        print(f"   [AI] DeepSeek 正在分析 {len(raw_data)} 条数据...")
        
        system_prompt = """
        你是一个高级技术研究员。你的任务是从搜索结果中筛选出最有价值的资源。
        请忽略 SEO 垃圾内容、过时的项目或低质量的教程。
        
        输出格式要求 (Markdown):
        
        ### 🏆 精选推荐
        1. **[项目/文章名称](URL)**
           - **类型**: [GitHub项目 / 教程 / 论文]
           - **推荐理由**: (用一句话概括它的核心价值，例如：使用了最新的 GraphRAG 技术)
           - **活跃度**: (如果有 Star 数或更新时间，请注明)
        
        ### 💡 总结
        (用简短的一段话总结该关键词目前的生态现状)
        """

        user_prompt = f"""
        关键词主题: {topic}
        
        以下是原始搜索数据 (JSON格式):
        {json.dumps(raw_data, ensure_ascii=False)}
        
        请根据上述数据生成一份调研简报。
        """

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"DeepSeek 分析失败: {e}"

def main():
    print("🚀 Deep Search Agent 启动中...\n")
    
    if "xx" in DEEPSEEK_API_KEY:
        print("❌ 错误: 请先在代码中填入你的 DeepSeek API Key")
        return

    provider = SearchProvider()
    analyst = DeepSeekAnalyst(DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL)
    
    final_report = f"# Deep Search Report\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    for item in KEYWORDS_DB:
        topic = item["topic"]
        query = item["query"]
        search_type = item.get("type", "general")
        
        print(f"🔍 正在处理主题: 【{topic}】")
        
        # 1. 获取数据
        raw_results = []
        
        # 如果是找代码，优先搜 GitHub
        if search_type == "code":
            raw_results.extend(provider.search_github(query))
            # 补充一点 web 搜索以防 GitHub 没搜到好的文档
            raw_results.extend(provider.search_web(f"{query} github best practices", limit=3))
        
        # 如果是找教程或通用，混合搜索
        else:
            raw_results.extend(provider.search_web(query, limit=6))
            raw_results.extend(provider.search_github(query, limit=2))

        # 2. 智能分析
        analysis = analyst.analyze_results(topic, raw_results)
        
        # 3. 写入报告
        section = f"## 📌 主题: {topic}\n> 搜索词: {query}\n\n{analysis}\n\n---\n\n"
        final_report += section
        print(f"✅ {topic} 处理完成。\n")

    # 4. 保存文件
    with open("deep_search_report.md", "w", encoding="utf-8") as f:
        f.write(final_report)
    
    print("🎉 所有任务完成！报告已生成: deep_search_report.md")

if __name__ == "__main__":
    main()