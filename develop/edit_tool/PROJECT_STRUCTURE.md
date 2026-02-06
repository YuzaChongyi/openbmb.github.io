# MiniCPM-o 4.5 Demo 项目结构与操作说明

## 📁 项目结构

```
openbmb.github.io/
├── minicpm-o-4_5/                    # 最终发布的 Demo 页面（构建产物）
│   ├── index.html                    # Demo 主页（支持中英文切换）
│   ├── data.js                       # 渲染数据（由 build.py 生成）
│   └── audio/                        # 音频资源（由 build.py 从 resources 复制）
│       └── [case_id]/
│           ├── ref.mp3
│           └── 000_assistant.mp3
│
└── develop/                          # 开发工具
    ├── edit_tool/                    # 📝 可视化编辑器（唯一编辑入口）
    │   ├── index.html                # 编辑器前端
    │   ├── server.py                 # 编辑器后端（API + 资源热更新服务）
    │   ├── config/                   # 编辑器配置
    │   │   └── data.json             # ⭐ 主工作文件（所有内容和顺序）
    │   └── resources/                # ⭐ 资源文件（唯一的音频来源）
    │       └── audio/
    │           └── [case_id]/
    │               ├── ref.mp3
    │               └── 000_assistant.mp3
    │
    ├── minicpm-o-4_5/                # 构建工具
    │   ├── build.py                  # 🔨 构建脚本
    │   └── config/
    │       └── cases.json            # 原始配置模板（仅回退用）
    │
    └── collected/                    # 🗄️ 历史原始数据（已不再依赖）
        ├── zh/
        └── en/
```

## 🔄 数据流向

```
        ┌─────────────────────────────────────────┐
        │  📝 编辑器 (唯一编辑入口)                  │
        │  develop/edit_tool/index.html            │
        │  - 编辑文本内容                            │
        │  - 调整顺序（中英文独立）                   │
        │  - 上传/替换音频 → 立即热更新预览           │
        └──┬──────────────┬──────────────┬────────┘
           │              │              │
   💾 保存  │    🔊 上传    │    📤 导出   │
           ▼              ▼              ▼
  ┌─────────────┐  ┌──────────────┐  ┌──────────┐
  │ config/     │  │ resources/   │  │ 本地文件  │
  │ data.json   │  │ audio/...    │  │ .json    │
  │ (配置数据)   │  │ (音频资源)    │  │ (备份)   │
  └──────┬──────┘  └──────┬───────┘  └──────────┘
                   │
           │              │
           └──────┬───────┘
                  │
         🔨 构建  │
                  ▼
  ┌─────────────────────────────────┐
  │  build.py                       │
  │  - 读取 config/data.json        │
  │  - 复制 resources/audio/ → 输出 │
  │  - 生成 data.js                 │
  └──────────────┬──────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────┐
  │  📦 minicpm-o-4_5/              │
  │  - data.js    (渲染数据)        │
  │  - audio/     (音频资源)        │
  │  - index.html (页面)            │
  └──────────────┬──────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────┐
  │  🌐 GitHub Pages                │
  └─────────────────────────────────┘
```

## 🎯 四个核心操作

### 1️⃣ 📂 **导入 (Import)**

**功能：** 从本地 JSON 文件导入配置数据到编辑器

**操作：** 点击工具栏 "📂 导入" 按钮

**流程：**
```
本地文件 (data.json)
    ↓
选择文件
    ↓
读取 JSON
    ↓
加载到编辑器内存
    ↓
立即渲染显示
```

**使用场景：**
- 从备份恢复配置
- 导入其他人编辑的配置
- 在不同版本间切换
- 本地编辑后重新导入

**特点：**
- ⚠️ 会覆盖当前编辑器中的所有数据
- ⚠️ 仅在浏览器内存中，未保存到服务器
- ✅ 支持完整的数据结构（包括 order 信息）

---

### 2️⃣ 📤 **导出 (Export)**

**功能：** 将编辑器当前数据导出为本地 JSON 文件

**操作：** 点击工具栏 "📤 导出" 按钮

**流程：**
```
编辑器当前数据
    ↓
生成 JSON 文件
    ↓
触发浏览器下载
    ↓
保存到本地 (data_zh.json 或 data_en.json)
```

**使用场景：**
- 备份当前配置
- 与他人分享配置
- 版本管理（保存不同版本）
- 离线编辑后再导入

**特点：**
- ✅ 包含完整数据（meta, abilities, order 等）
- ✅ 文件名包含当前语言标识
- ✅ 可读的 JSON 格式（带缩进）
- ⚠️ 仅导出数据，不包含音频文件

**文件名：**
- 中文模式：`data_zh.json`
- 英文模式：`data_en.json`

---

### 3️⃣ 💾 **保存 (Save)**

**功能：** 将编辑器数据保存到服务器配置目录

**操作：** 点击工具栏 "💾 保存" 按钮

**流程：**
```
编辑器当前数据
    ↓
POST /api/data
    ↓
server.py 处理
    ↓
写入 develop/edit_tool/config/data.json
    ↓
持久化存储
```

**保存位置：**
```
develop/edit_tool/config/data.json
```

**使用场景：**
- 编辑后持久化保存
- 作为构建脚本的数据源
- 团队协作的配置共享
- 作为编辑器的默认加载数据

**特点：**
- ✅ 保存到服务器，下次打开自动加载
- ✅ 包含完整数据结构和顺序信息
- ✅ 作为 build.py 的优先数据源
- ⚠️ 需要服务器运行（`python3 server.py`）

**与导出的区别：**
| 特性 | 保存 (Save) | 导出 (Export) |
|------|------------|---------------|
| 位置 | 服务器端 | 本地下载 |
| 持久性 | 永久保存 | 本地文件 |
| 用途 | 工作流主文件 | 备份/分享 |
| 自动加载 | ✅ 是 | ❌ 否 |

---

### 4️⃣ 🔨 **构建 (Build)**

**功能：** 生成最终的 Demo 页面数据和资源

**操作：** 点击工具栏 "🔨 构建" 按钮

**流程：**
```
触发构建
    ↓
POST /api/build
    ↓
server.py 调用 build.py
    ↓
build.py 执行：
    1. 读取 develop/edit_tool/config/data.json
       (优先级 1，编辑器保存的数据)
       或
       develop/minicpm-o-4_5/config/cases.json
       (优先级 2，原始模板)
    
    2. 处理每个 case：
       - 如果有 source_session: 从 collected/ 读取对话数据
       - 如果已有完整数据: 直接使用（手动编辑的）
    
    3. 复制音频文件：
       collected/[lang]/[session]/xxx.mp3
           ↓
       minicpm-o-4_5/audio/[case_id]/xxx.mp3
    
    4. 生成 data.js：
       - 包含所有处理后的数据
       - 保留 meta.order（顺序信息）
       - 格式化为 JavaScript 常量
    ↓
输出到 minicpm-o-4_5/
    ├── data.js           (生成的数据文件)
    └── audio/            (复制的音频资源)
```

**构建输出：**
```
minicpm-o-4_5/
├── data.js              # 📊 渲染数据
│   const DEMO_DATA = {
│       meta: {...},
│       abilities: [...]
│   };
│
└── audio/               # 🔊 音频资源
    ├── haitian_qa_001/
    │   ├── ref.mp3
    │   └── 000_assistant.mp3
    └── case_xxx/
        └── ...
```

**使用场景：**
- 编辑完成后生成最终页面
- 更新 Demo 内容
- 发布前的最后步骤
- 验证数据完整性

**特点：**
- ✅ 自动处理 session 数据
- ✅ 自动复制音频文件
- ✅ 保留完整的顺序信息
- ✅ 输出优化的 JavaScript 格式
- ⚠️ 会清空并重建 `minicpm-o-4_5/audio/` 目录

**构建优先级：**
1. **第一优先级**：`develop/edit_tool/config/data.json`
   - 编辑器保存的数据
   - 包含手动编辑和顺序信息
   
2. **第二优先级**：`develop/minicpm-o-4_5/config/cases.json`
   - 原始配置模板
   - 用于首次构建或回退

---

## 🔄 完整工作流

### 典型编辑流程

```
1. 启动服务器
   $ cd develop/edit_tool
   $ python3 server.py --port 8080

2. 打开编辑器
   浏览器访问: http://localhost:8080/develop/edit_tool/

3. 编辑内容
   - 双击文本进行编辑
   - 切换语言 (中文/EN)
   - 拖拽大纲调整顺序
   - 添加/删除 sections, cases

4. 💾 保存
   点击 "保存" 按钮
   → 数据写入 develop/edit_tool/config/data.json

5. 📤 导出（可选）
   点击 "导出" 按钮
   → 下载备份到本地

6. 🔨 构建
   点击 "构建" 按钮
   → 生成 minicpm-o-4_5/data.js 和 audio/

7. 👁 预览
   点击 "预览" 按钮
   → 打开 http://localhost:8080/minicpm-o-4_5/
   → 查看最终效果

8. 发布（可选）
   $ git add .
   $ git commit -m "Update demo content"
   $ git push
   → GitHub Pages 自动更新
```

### 从备份恢复

```
1. 📂 导入
   点击 "导入" → 选择备份的 data_zh.json

2. 💾 保存
   点击 "保存" → 写入服务器配置

3. 🔨 构建
   点击 "构建" → 生成最终文件
```

---

## 📊 数据源优先级总结

### 编辑器加载数据

```
优先级 1: develop/edit_tool/config/data.json
    ↓ (不存在)
优先级 2: minicpm-o-4_5/data.js
    ↓ (不存在)
优先级 3: develop/minicpm-o-4_5/config/cases.json
    ↓ (不存在)
默认: 空数据 { meta: {...}, abilities: [] }
```

### 构建脚本数据源

```
优先级 1: develop/edit_tool/config/data.json (编辑器保存的)
    ↓ (不存在)
优先级 2: develop/minicpm-o-4_5/config/cases.json (原始模板)
```

---

## 🔑 关键文件说明

### 1. `develop/edit_tool/config/data.json`
**作用：** 编辑器的工作文件，保存所有编辑结果

**何时生成：** 首次点击"保存"按钮

**包含内容：**
- 完整的 meta（包括 order）
- 所有 abilities/sub_abilities/cases
- 已处理的对话数据
- 中英文独立的顺序信息

**特点：**
- ✅ 编辑器优先加载此文件
- ✅ 构建脚本优先使用此文件
- ✅ 包含最新的编辑状态

---

### 2. `develop/minicpm-o-4_5/config/cases.json`
**作用：** 原始配置模板

**用途：**
- 定义 case 和 session 的映射关系
- 作为首次构建的数据源
- 作为回退选项

**包含内容：**
- 基础的 meta 信息
- abilities 结构
- source_session 引用
- 多语言字段

**特点：**
- ⚠️ 不包含 order 信息（会自动初始化）
- ⚠️ 需要从 collected/ 读取对话数据

---

### 3. `minicpm-o-4_5/data.js`
**作用：** 最终 Demo 页面的数据文件

**何时生成：** 点击"构建"按钮

**格式：**
```javascript
// Auto-generated by build.py - DO NOT EDIT
const DEMO_DATA = {
  "meta": {...},
  "abilities": [...]
};
```

**包含内容：**
- 完整的渲染数据
- 处理后的对话内容
- 音频路径引用
- 顺序信息（meta.order）

**特点：**
- ✅ 供 index.html 直接使用
- ✅ 包含所有需要的数据
- ⚠️ 由脚本生成，不要手动编辑

---

## ⚠️ 注意事项

1. **保存 vs 导出**
   - "保存"是持久化到服务器，下次自动加载
   - "导出"是下载到本地，用于备份

2. **修改后必须保存**
   - 编辑后只在浏览器内存中
   - 必须点击"保存"才能持久化
   - 刷新页面会丢失未保存的修改

3. **保存后必须构建**
   - "保存"只更新编辑器配置
   - "构建"才生成最终的 Demo 文件
   - Demo 页面使用的是 data.js，不是 data.json

4. **音频文件管理**
   - 当前版本：音频从 collected/ 目录复制
   - 未来版本：支持在编辑器中上传音频

5. **顺序信息**
   - 首次使用会自动初始化
   - 中英文顺序独立
   - 需要保存后才持久化

---

## 🚀 快速参考

| 操作 | 按钮 | 快捷理解 | 持久化 |
|------|------|----------|--------|
| 导入 | 📂 | 从本地文件 → 编辑器 | ❌ 内存 |
| 导出 | 📤 | 编辑器 → 本地文件 | ✅ 本地 |
| 保存 | 💾 | 编辑器 → 服务器 | ✅ 服务器 |
| 构建 | 🔨 | 服务器 → Demo 文件 | ✅ 服务器 |
| 预览 | 👁 | 查看 Demo 效果 | - |

**记忆口诀：**
- **导入/导出**：编辑器 ↔ 本地文件（临时备份）
- **保存**：编辑器 → 服务器（持久化配置）
- **构建**：服务器配置 → Demo 页面（发布）
