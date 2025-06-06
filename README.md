# VTT字幕翻译系统

一个用于将英文VTT字幕文件翻译成中文的工具，使用AWS Bedrock的Claude模型进行翻译。

## 功能特点

- 智能解析VTT字幕文件，支持带行号和不带行号的格式
- 将字幕分组为语义单元，提高翻译质量
- 使用AWS Bedrock的Claude模型进行高质量翻译
- 智能分配翻译结果，保持字幕的自然断句
- 支持单文件翻译和批量翻译
- 详细的日志记录，方便追踪处理过程
- 可配置的参数，适应不同的使用场景

## 安装

### 前置条件

- Python 3.7+
- AWS账号，并配置好AWS凭证
- AWS Bedrock访问权限，可以使用Claude模型

### 安装步骤

1. 克隆代码库：

```bash
git clone <repository-url>
cd vtt_translator
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 配置AWS凭证：

确保已经配置好AWS凭证，可以通过以下方式之一：
- 使用AWS CLI: `aws configure`
- 设置环境变量: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- 使用凭证文件: `~/.aws/credentials`

## 使用方法

### 命令行使用

#### 翻译单个文件

```bash
python -m vtt_translator.main translate input.vtt output.vtt
```

#### 批量翻译文件

```bash
python -m vtt_translator.main batch --input-dir /path/to/vtt --output-dir /path/to/output --done-dir /path/to/done
```

#### 生成配置文件

```bash
python -m vtt_translator.main config config.json
```

### 作为库使用

#### 翻译单个文件

```python
from vtt_translator import VttTranslator

translator = VttTranslator()
translator.translate_vtt('input.vtt', 'output.vtt')
```

#### 批量翻译文件

```python
from vtt_translator import VttTranslatorManager

manager = VttTranslatorManager()
manager.batch_process()
```

## 配置选项

可以通过配置文件或命令行参数设置以下选项：

- `input_dir`: 输入目录
- `output_dir`: 输出目录
- `done_dir`: 处理完成目录
- `log_dir`: 日志目录
- `aws_region`: AWS区域
- `model_id`: Claude模型ID
- `max_retries`: 最大重试次数
- `retry_delay`: 重试延迟时间
- `api_sleep_time`: API调用后休眠时间
- `min_sleep_time`: 批处理最小休眠时间
- `max_sleep_time`: 批处理最大休眠时间

## 目录结构

```
vtt_translator/
├── __init__.py                # 包初始化文件
├── main.py                    # 命令行入口
├── vtt_translator_core.py     # 核心翻译模块
├── vtt_translator_manager.py  # 调度管理模块
├── vtt_translator_config.py   # 配置模块
├── vtt_translator_utils.py    # 工具函数模块
├── requirements.txt           # 依赖包列表
└── README.md                  # 说明文档
```

## 示例

### 翻译单个文件

```bash
python -m vtt_translator.main translate /path/to/input.vtt /path/to/output.vtt
```

### 批量翻译目录中的前10个文件

```bash
python -m vtt_translator.main batch --start 0 --end 10
```

### 使用自定义配置文件

```bash
python -m vtt_translator.main batch --config /path/to/config.json
```