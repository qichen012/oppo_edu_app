import os

# ================= 配置区 =================
ZHIZENGZENG_BASE_URL = "https://api.zhizengzeng.com/v1"
# 注意：文件中保留了用户原先的 key（请根据实际情况改为环境变量或 secrets 管理）
ZHIZENGZENG_API_KEY = "sk-"
MODEL_NAME = "gpt-4o"
# DeepSeek API 配置
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY = "sk-"
DEEPSEEK_MODEL = "deepseek-chat"# 将运行时文件放在 data/ 下以便统一管理
UPLOAD_DIR = os.path.join("data", "uploads")
OUTPUT_DIR = os.path.join("data", "processed_notes")

# 转录服务配置
TRANSCRIBE_SERVER_IP = ""
TRANSCRIBE_SERVER_PORT = "8000"

# 确保目录存在（调用模块时通常已确保，但这里作为防御性措施）
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
