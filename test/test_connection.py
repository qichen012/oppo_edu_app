import requests
import json
import time

URL = "http://localhost:8888/memories"

content = {
  "domain": "计算成像 / Computational Imaging",
  "title": "编码孔径成像中的‘部分响应式’设计思想",
  "core_idea": "在光学成像中，不追求物理上消除模糊（如衍射、像差），而是主动引入已知的、结构化的模糊（如通过编码孔径或相位掩模），再通过算法（如反卷积）进行逆向重建。",
  "problem": "传统光学系统受限于物理瓶颈（如衍射极限、制造误差），难以获得高分辨率图像；直接提升硬件成本高且存在理论极限。",
  "solution_strategy": "将成像系统建模为一个‘已知模糊滤波器’（点扩散函数 PSF），在感知端故意设计特定模糊模式（相当于发送端预编码），在重建端用算法（如 Wiener 反卷积、Richardson-Lucy）进行均衡式补偿（相当于接收端解码）。",
  "analogy_to_communication": {
    "optical_system": "≈ 通信信道（引入失真）",
    "coded_aperture_or_phase_mask": "≈ 部分响应中的预编码（主动引入可控 ISI）",
    "blurred_image": "≈ 带 ISI 的接收信号",
    "deconvolution_algorithm": "≈ 自适应均衡器或 ISI 解码器"
  },
  "design_paradigm": "可控失真 + 逆向补偿范式（Controlled Distortion + Inverse Compensation）",
  "related_concepts": ["部分响应", "信道均衡", "反卷积", "编码孔径", "计算摄影", "系统协同设计", "结构化扰动"]
}


def final_test():
    # 1. 增加 timeout 到 30 秒，因为 LLM 提取比较慢
    payload = {
        "messages": [{"role": "user", "content": f"我今天学习了{content}"}],
        "user_id": "test_user_05"
    }
    
    print("⏳ 正在发送请求（包含 LLM 提取，可能较慢）...")
    try:
        start_time = time.time()
        # 调大 timeout
        resp = requests.post(URL, json=payload, timeout=300)
        end_time = time.time()
        
        print(f"✅ Docker 响应成功！耗时: {end_time - start_time:.2f}秒")
        print("响应内容:", resp.json())
        
        # 2. 紧接着做一个 GET 请求验证数据是否真的在里面了
        print("\n🔍 正在从 Docker 数据库检索刚才的记忆...")
        # 注意：根据文档，查询通常是 GET /memories?user_id=...
        get_resp = requests.get(f"{URL}?user_id=test_user_05", timeout=10)
        print("当前用户所有记忆:", json.dumps(get_resp.json(), indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ 还是出错了: {e}")

if __name__ == "__main__":
    final_test()