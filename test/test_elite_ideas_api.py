"""
测试 Elite Ideas API 接口
"""
import requests

# API 地址
API_URL = "http://127.0.0.1:8001/extract_elite_ideas"

# 要测试的 PDF 文件路径
PDF_FILE_PATH = "./data/test/test_of_note.pdf"

def test_elite_ideas_api():
    """测试 Elite Ideas 提取接口"""
    print(f"正在上传文件: {PDF_FILE_PATH}")
    print("="*60)
    
    try:
        # 打开并上传文件
        with open(PDF_FILE_PATH, "rb") as f:
            files = {"file": (PDF_FILE_PATH.split("/")[-1], f, "application/pdf")}
            response = requests.post(API_URL, files=files)
        
        # 检查响应状态
        if response.status_code == 200:
            result = response.json()
            print("✓ 请求成功！\n")
            print(f"文件名: {result.get('filename')}")
            print(f"文本长度: {result.get('text_length')} 字符")
            print(f"处理耗时: {result.get('elapsed_time')} 秒")
            print(f"输出文件: {result.get('output_path')}")
            print("\n" + "="*60)
            print("Elite Ideas 提取结果:")
            print("="*60)
            print(result.get('elite_ideas'))
        else:
            print(f"✗ 请求失败！状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except FileNotFoundError:
        print(f"✗ 文件不存在: {PDF_FILE_PATH}")
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务器，请确保服务器正在运行")
        print("   启动命令: python run/server.py")
    except Exception as e:
        print(f"✗ 发生错误: {str(e)}")


if __name__ == "__main__":
    print("Elite Ideas API 测试")
    print("="*60)
    test_elite_ideas_api()
