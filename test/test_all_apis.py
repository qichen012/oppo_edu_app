"""
测试所有 API 接口（除了 PDF 处理）
包括：截图分析、用户画像分析、推荐系统、会议转录
"""
import requests
import json
import os

# API 基础地址
BASE_URL = "http://127.0.0.1:8001"

# 测试数据路径
SCREENSHOT_PATH = "./data/data_screenshot/images/test01.jpg"
# 如果有音频文件可以用于测试会议转录，在这里指定
AUDIO_PATH = "./data/meeting_data/mac_recording.wav"  # 如果没有可以设为 None


def print_section(title):
    """打印测试部分标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_analyze_screenshot():
    """测试截图分析接口"""
    print_section("1. 测试截图分析 API - /analyze_screenshot")
    
    if not os.path.exists(SCREENSHOT_PATH):
        print(f"❌ 截图文件不存在: {SCREENSHOT_PATH}")
        return False
    
    try:
        with open(SCREENSHOT_PATH, 'rb') as f:
            files = {'file': ('screenshot.jpg', f, 'image/jpeg')}
            response = requests.post(f"{BASE_URL}/analyze_screenshot", files=files, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 截图分析成功!")
            print(f"\n📊 返回结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ 请求失败 (状态码: {response.status_code})")
            print(f"错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_analyze_profile():
    """测试用户画像分析接口"""
    print_section("2. 测试用户画像分析 API - /analyze_profile")
    
    # 构造测试数据
    test_data = {
        "user_history": [
            {
                "title": "深度学习入门教程",
                "clicks": 15,
                "duration": 3600.5,
                "tags": ["机器学习", "深度学习", "AI"]
            },
            {
                "title": "Python数据分析实战",
                "clicks": 8,
                "duration": 2400.0,
                "tags": ["Python", "数据分析", "pandas"]
            },
            {
                "title": "自然语言处理基础",
                "clicks": 12,
                "duration": 3000.0,
                "tags": ["NLP", "机器学习", "文本处理"]
            },
            {
                "title": "计算机视觉应用",
                "clicks": 6,
                "duration": 1800.0,
                "tags": ["计算机视觉", "深度学习", "图像处理"]
            },
            {
                "title": "强化学习算法详解",
                "clicks": 10,
                "duration": 2700.0,
                "tags": ["强化学习", "机器学习", "AI"]
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/analyze_profile",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 用户画像分析成功!")
            print(f"\n📊 用户画像:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ 请求失败 (状态码: {response.status_code})")
            print(f"错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_recommend():
    """测试推荐系统接口"""
    print_section("3. 测试推荐系统 API - /recommend")
    
    # 构造测试数据
    test_data = {
        "user_history": [
            {
                "title": "机器学习基础知识",
                "clicks": 20,
                "duration": 4500.0,
                "tags": ["机器学习", "AI", "算法"]
            },
            {
                "title": "神经网络原理",
                "clicks": 15,
                "duration": 3600.0,
                "tags": ["深度学习", "神经网络", "AI"]
            },
            {
                "title": "数据挖掘技术",
                "clicks": 10,
                "duration": 2400.0,
                "tags": ["数据挖掘", "大数据", "分析"]
            }
        ],
        "source": "rss",  # 或 'ddgs'
        "limit": 5,
        "epsilon": 0.1
    }
    
    try:
        print(f"📤 请求参数: source={test_data['source']}, limit={test_data['limit']}, epsilon={test_data['epsilon']}")
        
        response = requests.post(
            f"{BASE_URL}/recommend",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=60  # 推荐可能需要更多时间
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 推荐内容生成成功!")
            print(f"\n📚 推荐结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ 请求失败 (状态码: {response.status_code})")
            print(f"错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_meeting_transcribe():
    """测试会议转录接口"""
    print_section("4. 测试会议转录 API - /meeting_transcribe")
    
    if AUDIO_PATH is None or not os.path.exists(AUDIO_PATH):
        print(f"⚠️  跳过测试: 音频文件未配置或不存在")
        print(f"   如需测试，请在脚本中设置 AUDIO_PATH 变量")
        return None
    
    try:
        with open(AUDIO_PATH, 'rb') as f:
            files = {'file': (os.path.basename(AUDIO_PATH), f, 'audio/m4a')}
            response = requests.post(
                f"{BASE_URL}/meeting_transcribe",
                files=files,
                timeout=120  # 转录可能需要较长时间
            )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 会议转录成功!")
            print(f"\n📝 转录结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ 请求失败 (状态码: {response.status_code})")
            print(f"错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "🚀" * 40)
    print("开始测试所有 API 接口...")
    print("🚀" * 40)
    
    results = {
        "截图分析": test_analyze_screenshot(),
        "用户画像分析": test_analyze_profile(),
        "推荐系统": test_recommend(),
        "会议转录": test_meeting_transcribe()
    }
    
    # 打印测试总结
    print("\n" + "=" * 80)
    print("  测试总结")
    print("=" * 80)
    
    success_count = sum(1 for v in results.values() if v is True)
    failed_count = sum(1 for v in results.values() if v is False)
    skipped_count = sum(1 for v in results.values() if v is None)
    
    for test_name, result in results.items():
        if result is True:
            status = "✅ 通过"
        elif result is False:
            status = "❌ 失败"
        else:
            status = "⚠️  跳过"
        print(f"{status}  {test_name}")
    
    print(f"\n📊 总计: {success_count} 通过, {failed_count} 失败, {skipped_count} 跳过")
    
    if failed_count == 0 and success_count > 0:
        print("\n🎉 所有可用接口测试通过！")
    elif failed_count > 0:
        print(f"\n⚠️  有 {failed_count} 个接口测试失败，请检查")


if __name__ == "__main__":
    main()
