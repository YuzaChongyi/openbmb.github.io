# MiniCPM-o 4.5 Demo Page 开发指南

本目录包含 Demo Page 的开发文件，不会被开源。

## 目录结构

```
develop/
├── README.md                    # 本文件
├── collected/                   # 收集的 session 数据
│   ├── zh/                      # 中文 sessions
│   └── en/                      # 英文 sessions
└── minicpm-o-4_5/
    ├── build.py                 # 构建脚本
    ├── generate_cases.py        # Case 自动生成脚本
    └── config/
        ├── cases.json           # Case 配置文件（主要编辑这个）
        └── cases_schema.md      # Schema 文档
```

## 快速开始

### 1. 编辑配置

编辑 `minicpm-o-4_5/config/cases.json`

### 2. 运行构建

```bash
cd /Users/sunweiyue/Desktop/lib/openbmb.github.io
python3 develop/minicpm-o-4_5/build.py
```

### 3. 预览效果

```bash
cd minicpm-o-4_5
python3 -m http.server 8080
# 浏览器打开 http://localhost:8080
```

## cases.json 配置说明

### 结构概览

```json
{
  "meta": { "title": "...", "description": "..." },
  "abilities": [
    {
      "id": "haitian",
      "name": "海天主打音色",
      "sub_abilities": [
        {
          "id": "story",
          "name": "讲故事",
          "cases": [
            {
              "id": "haitian_story_001",
              "summary": "用轻柔语气讲睡前故事",
              "source_session": "session_20260129_034105_a264bd2a"
            }
          ]
        }
      ]
    }
  ]
}
```

### Case 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一标识，用于音频目录命名 |
| `summary` | ✅ | 卡片上显示的摘要文本 |
| `source_session` | ✅ | collected 中的 session 目录名 |
| `user_text_override` | ❌ | 覆盖 ASR 转录的用户文本 |

### 常用操作

#### 修改 summary

```json
{
  "id": "haitian_story_001",
  "summary": "温柔讲述睡前故事",  // ← 直接修改
  "source_session": "session_20260129_034105_a264bd2a"
}
```

#### 覆盖用户文本（替换 ASR）

```json
{
  "id": "haitian_story_001",
  "summary": "温柔讲述睡前故事",
  "source_session": "session_20260129_034105_a264bd2a",
  "user_text_override": {
    "0": "用轻柔的语气讲一个睡前故事",
    "1": "再讲一个关于小兔子的故事"
  }
}
```

#### 添加新 Case

1. 确认 session 存在于 `collected/zh/` 或 `collected/en/`
2. 在对应 `sub_abilities.cases` 数组中添加：

```json
{
  "id": "new_case_001",
  "summary": "新案例描述",
  "source_session": "session_xxxxxxxx_xxxxxx_xxxxxxxx"
}
```

#### 删除 Case

直接从 `cases` 数组中删除对应条目即可。

## 自动生成配置

如果需要重新扫描 collected 目录生成配置：

```bash
python3 develop/minicpm-o-4_5/generate_cases.py
```

⚠️ 注意：这会覆盖现有的 cases.json，请先备份。

## 构建输出

运行 `build.py` 后会生成：

```
minicpm-o-4_5/
├── data.js          # 渲染数据（不含溯源信息）
└── audio/           # 音频文件
    ├── {case_id}/
    │   ├── ref.mp3              # 参考音频
    │   ├── 000_assistant.mp3    # 第0轮回复
    │   ├── 001_assistant.mp3    # 第1轮回复
    │   └── ...
    └── ...
```

## 能力分类映射

| 能力 ID | 名称 | 数据来源 |
|---------|------|----------|
| `haitian` | 海天主打音色 | zh/海天_故事, zh/综合能力_多轮 |
| `custom_voice` | Custom Voice | zh/role_play |
| `advanced_speech` | 高级语音能力 | zh/海天_高级语音 |
| `duplex` | 双工能力 | （待补充） |
| `english` | 英文能力 | en/role_play |
