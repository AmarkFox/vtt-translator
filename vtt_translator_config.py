"""
配置模块，提供系统配置参数和配置加载功能
"""

import os
import json

# 默认配置
DEFAULT_CONFIG = {
    # 目录配置
    "input_dir": "../vtt",
    "output_dir": "../vtt/zh",
    "done_dir": "../vtt/done",
    "log_dir": "../logs",
    
    # API配置
    "aws_region": "us-west-2",
    "model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    
    # 翻译配置
    "max_retries": 5,
    "retry_delay": 2,
    "api_sleep_time": 5,
    
    # 批处理配置
    "min_sleep_time": 180,
    "max_sleep_time": 300
}

def load_config(config_path=None):
    """
    加载配置文件，如果文件不存在则使用默认配置
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认配置
        
    Returns:
        config: 配置字典
    """
    config = DEFAULT_CONFIG.copy()
    
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"加载配置文件失败: {str(e)}，将使用默认配置")
    
    # 确保所有路径都是绝对路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for key in ["input_dir", "output_dir", "done_dir", "log_dir"]:
        if not os.path.isabs(config[key]):
            config[key] = os.path.abspath(os.path.join(base_dir, config[key]))
    
    return config

def save_config(config, config_path):
    """
    保存配置到文件
    
    Args:
        config: 配置字典
        config_path: 配置文件路径
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        return True
    except Exception as e:
        print(f"保存配置文件失败: {str(e)}")
        return False