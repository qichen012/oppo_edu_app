import requests
import json
import os

# ================= 配置区 =================
# 服务地址 (如果是本机运行，用 127.0.0.1 即可)
API_URL = "http://127.0.0.1:8001/analyze_screenshot"

# 测试用截图路径（请修改为本地的测试图片路径）
SCREENSHOT_PATH = "./data/data_screenshot/test01.jpg"
# =======================================

def run_test():
    # 1. 检查文件是否存在
    if not os.path.exists(SCREENSHOT_PATH):
        print(f"❌ 错误：找不到文件 '{SCREENSHOT_PATH}'")
        print("请修改代码中的 SCREENSHOT_PATH 变量为真实的图片路径。")
        return

    print(f"🚀 正在上传截图 [{SCREENSHOT_PATH}] 进行关联分析...")

    try:
        # 2. 发送请求
        with open(SCREENSHOT_PATH, 'rb') as f:
            files = {'file': f}
            # 注意：这个接口比较慢，因为 GPT-4o 要读图+读所有笔记，可能需要 10-20 秒
            response = requests.post(API_URL, files=files, timeout=60)

        # 3. 处理结果
        if response.status_code == 200:
            resp_json = response.json()
            
            # 打印原始 JSON (方便调试)
            # print(json.dumps(resp_json, indent=4, ensure_ascii=False))

            data = resp_json.get('data', {})
            
            print("\n" + "="*40)
            print("🤖 AI 分析结果报告")
            print("="*40)
            
            # 3.1 截图内容分析
            print(f"\n📸 [截图识别]:\n{data.get('screenshot_analysis', '无内容')}")
            
            # 3.2 最佳匹配笔记
            best_match = data.get('best_match')
            
            print("\n🔗 [关联匹配]:")
            if best_match:
                print(f"   ✅ 命中笔记: 《{best_match.get('note_title')}》")
                print(f"   📄 文件名: {best_match.get('related_note_filename')}")
                print(f"   💡 关联理由: {best_match.get('reason')}")
            else:
                print("   🤷‍♂️ 未在现有笔记库中找到强关联内容。")
                print("   (可能是笔记库太少，或者截图内容确实没关系)")
                
        else:
            print(f"❌ 请求失败 (状态码 {response.status_code}):")
            print(response.text)

    except requests.exceptions.Timeout:
        print("❌ 请求超时！可能是 GPT-4o 分析时间过长，请检查网络或增加 timeout 设置。")
    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    run_test()