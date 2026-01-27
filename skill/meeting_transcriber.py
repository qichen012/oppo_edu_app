"""
会议纪要转录模块
负责将音频文件转发到转录服务器并返回处理结果
"""

import os
import time
import requests
from typing import Dict, Any
from skill.config import TRANSCRIBE_SERVER_IP, TRANSCRIBE_SERVER_PORT


# ===== 转录服务配置 =====
REQUEST_TIMEOUT = 300  # 5分钟超时


def transcribe_audio_file(audio_file_path: str) -> Dict[str, Any]:
    """
    将音频文件发送到转录服务器进行处理
    
    Args:
        audio_file_path: 音频文件的本地路径
        
    Returns:
        包含转录结果的字典
        
    Raises:
        Exception: 当转录失败时抛出异常
    """
    start_time = time.time()
    transcribe_url = f"http://{TRANSCRIBE_SERVER_IP}:{TRANSCRIBE_SERVER_PORT}/transcribe"
    
    try:
        with open(audio_file_path, 'rb') as audio_file:
            files = {'file': audio_file}
            response = requests.post(
                transcribe_url, 
                files=files, 
                timeout=REQUEST_TIMEOUT
            )
        
        if response.status_code == 200:
            result = response.json()
            processing_time = time.time() - start_time
            
            return {
                "status": "success",
                "minutes": result.get("minutes", ""),
                "processing_time": round(processing_time, 2),
                "transcribe_server": f"{TRANSCRIBE_SERVER_IP}:{TRANSCRIBE_SERVER_PORT}",
                "audio_file": os.path.basename(audio_file_path)
            }
        else:
            raise Exception(f"转录服务器错误 {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"无法连接到转录服务器 {TRANSCRIBE_SERVER_IP}:{TRANSCRIBE_SERVER_PORT}: {e}")
    except Exception as e:
        raise Exception(f"转录处理失败: {e}")


def update_transcribe_server(ip: str, port: str = "8000"):
    """
    更新转录服务器配置
    
    Args:
        ip: 服务器IP地址
        port: 服务器端口，默认8000
    """
    global TRANSCRIBE_SERVER_IP, TRANSCRIBE_SERVER_PORT
    TRANSCRIBE_SERVER_IP = ip
    TRANSCRIBE_SERVER_PORT = port
    print(f"转录服务器已更新为: {ip}:{port}")


def get_transcribe_server_info() -> Dict[str, str]:
    """
    获取当前转录服务器配置信息
    
    Returns:
        包含服务器信息的字典
    """
    return {
        "ip": TRANSCRIBE_SERVER_IP,
        "port": TRANSCRIBE_SERVER_PORT,
        "url": f"http://{TRANSCRIBE_SERVER_IP}:{TRANSCRIBE_SERVER_PORT}/transcribe"
    }