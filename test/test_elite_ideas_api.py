"""测试 Elite Ideas API 接口。

当前接口不再上传 PDF，而是从 data/handouts/ 读取讲义（默认最新）。
"""
import requests

# API 地址
API_URL = "http://127.0.0.1:8001/extract_elite_ideas"

# 可选：指定讲义文件名（不填则默认取最新 *_handout.json）
HANDOUT_FILENAME = None  # e.g. "upload_handout.json"

def test_elite_ideas_api():
    """测试 Elite Ideas 提取接口（从讲义提取）。"""
    print("正在从已落盘讲义提取 Elite Ideas")
    print("="*60)
    
    try:
        data = {}
        if HANDOUT_FILENAME:
            data["handout_filename"] = HANDOUT_FILENAME

        response = requests.post(API_URL, data=data)
        
        # 检查响应状态
        if response.status_code == 204:
            print("✓ 请求成功（已落盘，无返回体）")
        else:
            print(f"✗ 请求失败！状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务器，请确保服务器正在运行")
        print("   启动命令: python run/server.py")
    except Exception as e:
        print(f"✗ 发生错误: {str(e)}")


if __name__ == "__main__":
    print("Elite Ideas API 测试")
    print("="*60)
    test_elite_ideas_api()
