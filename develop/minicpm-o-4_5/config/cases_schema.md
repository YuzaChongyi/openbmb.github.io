# Cases 配置文件 Schema

本文档描述 `cases.json` 的数据结构，用于配置 MiniCPM-o 4.5 Demo Page 的展示内容。

## 整体结构

```json
{
  "meta": {
    "title": "MiniCPM-o 4.5",
    "description": "...",
    "version": "1.0.0"
  },
  "abilities": [...]
}
```

## 层级结构

```
abilities (一级能力)
└── sub_abilities (二级能力)
    └── cases (具体案例)
        └── turns (对话轮次)
```

## 字段说明

### Ability (一级能力)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | ✅ | 唯一标识，用于 URL hash，如 `haitian` |
| name | string | ✅ | 显示名称，如 `海天主打音色` |
| description | string | ❌ | 能力描述 |
| sub_abilities | array | ✅ | 二级能力列表 |

### SubAbility (二级能力)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | ✅ | 唯一标识，如 `story` |
| name | string | ✅ | 显示名称，如 `讲故事` |
| description | string | ❌ | 二级能力描述 |
| cases | array | ✅ | 案例列表 |

### Case (具体案例)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | ✅ | 唯一标识，如 `bedtime_story_001` |
| summary | string | ✅ | 案例摘要，用于卡片展示 |
| source_session | string | ✅ | 源 session 目录名（仅开发用，不会出现在最终数据中） |
| source_url | string | ❌ | 源 URL（仅开发用，不会出现在最终数据中） |
| system | object | ✅ | 系统设置 |
| turns | array | ✅ | 对话轮次 |
| user_text_override | object | ❌ | 覆盖 user 文本的映射 `{turn_idx: "new_text"}` |

### System (系统设置)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| prefix | string | ✅ | 系统前缀文本 |
| ref_audio | string | ✅ | 参考音频相对路径 |
| suffix | string | ✅ | 系统后缀文本 |

注：build 脚本会自动从 session 中读取这些字段，无需手动填写。

### Turn (对话轮次)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_text | string | ✅ | 用户输入文本 |
| assistant_text | string | ✅ | 助手回复文本 |
| assistant_audio | string | ✅ | 助手音频相对路径 |

注：build 脚本会自动从 session 中读取并填充这些字段。

## 配置示例

```json
{
  "meta": {
    "title": "MiniCPM-o 4.5",
    "description": "下一代全模态语音对话模型"
  },
  "abilities": [
    {
      "id": "haitian",
      "name": "海天主打音色",
      "description": "专业声优音色，自然韵律",
      "sub_abilities": [
        {
          "id": "story",
          "name": "讲故事",
          "cases": [
            {
              "id": "bedtime_story",
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

## 扩展操作

### 添加新 Case

1. 在对应的 `sub_abilities.cases` 数组中添加条目
2. 填写 `id`, `summary`, `source_session`
3. 运行 `python build.py`

### 覆盖 User 文本

如果需要将 ASR 转录替换为正式文本：

```json
{
  "id": "example_case",
  "source_session": "session_xxx",
  "user_text_override": {
    "0": "这是第一轮的正式用户输入",
    "1": "这是第二轮的正式用户输入"
  }
}
```
