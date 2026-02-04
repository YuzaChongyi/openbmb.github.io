#!/usr/bin/env python3
"""扫描 collected 目录，生成 cases.json 配置

Usage:
    cd /path/to/openbmb.github.io
    python develop/minicpm-o-4_5/generate_cases.py
"""

import json
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).parent
COLLECTED_DIR = SCRIPT_DIR.parent / "collected"
CONFIG_PATH = SCRIPT_DIR / "config" / "cases.json"


def read_first_user_text(session_dir: Path) -> str:
    """读取第一轮用户输入作为 summary"""
    asr_file = session_dir / "000_user_audio0.asr.txt"
    if asr_file.exists():
        text = asr_file.read_text(encoding="utf-8").strip()
        # 截取前50字符
        if len(text) > 50:
            text = text[:50] + "..."
        return text
    return session_dir.name


def count_turns(session_dir: Path) -> int:
    """统计对话轮数"""
    count = 0
    while (session_dir / f"{count:03d}_assistant.txt").exists():
        count += 1
    return count


def scan_sessions(lang_dir: Path) -> dict:
    """扫描某语言目录下的所有 session"""
    results = {}
    
    for category_dir in sorted(lang_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        if category_dir.name == "index.jsonl":
            continue
            
        category_name = category_dir.name
        sessions = []
        
        for session_dir in sorted(category_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            if not session_dir.name.startswith("session_"):
                continue
            
            summary = read_first_user_text(session_dir)
            turns = count_turns(session_dir)
            
            sessions.append({
                "session_id": session_dir.name,
                "summary": summary,
                "turns": turns
            })
        
        if sessions:
            results[category_name] = sessions
    
    return results


def main():
    print("扫描 collected 目录...")
    
    # 扫描中文
    zh_dir = COLLECTED_DIR / "zh"
    zh_data = scan_sessions(zh_dir) if zh_dir.exists() else {}
    
    # 扫描英文
    en_dir = COLLECTED_DIR / "en"
    en_data = scan_sessions(en_dir) if en_dir.exists() else {}
    
    print("\n=== 中文数据 ===")
    for cat, sessions in zh_data.items():
        print(f"\n📁 {cat} ({len(sessions)} sessions)")
        for s in sessions:
            print(f"  - {s['session_id']}: {s['summary']} ({s['turns']}轮)")
    
    print("\n=== 英文数据 ===")
    for cat, sessions in en_data.items():
        print(f"\n📁 {cat} ({len(sessions)} sessions)")
        for s in sessions:
            print(f"  - {s['session_id']}: {s['summary']} ({s['turns']}轮)")
    
    # 生成建议的 cases.json 结构
    print("\n" + "=" * 60)
    print("建议的 cases.json 配置：")
    print("=" * 60)
    
    # 映射 collected 分类到 cases.json 结构
    mapping = {
        "haitian": {
            "sub_abilities": {
                "story": {
                    "source_category": "海天_故事",
                    "lang": "zh"
                },
                "qa": {
                    "source_category": "综合能力_多轮",
                    "lang": "zh"
                }
            }
        },
        "custom_voice": {
            "sub_abilities": {
                "clone": {
                    "source_category": "role_play",
                    "lang": "zh"
                }
            }
        },
        "advanced_speech": {
            "sub_abilities": {
                "emphasis": {
                    "source_category": "海天_高级语音",
                    "lang": "zh"
                }
            }
        },
        "english": {
            "sub_abilities": {
                "conversation": {
                    "source_category": "role_play",
                    "lang": "en"
                }
            }
        }
    }
    
    # 加载现有配置
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    # 填充 cases
    for ability in config["abilities"]:
        ability_id = ability["id"]
        if ability_id not in mapping:
            continue
        
        for sub in ability["sub_abilities"]:
            sub_id = sub["id"]
            if sub_id not in mapping[ability_id]["sub_abilities"]:
                continue
            
            source_info = mapping[ability_id]["sub_abilities"][sub_id]
            source_cat = source_info["source_category"]
            lang = source_info["lang"]
            
            # 获取对应的 sessions
            data = zh_data if lang == "zh" else en_data
            if source_cat not in data:
                continue
            
            sessions = data[source_cat]
            cases = []
            for i, s in enumerate(sessions):
                case_id = f"{ability_id}_{sub_id}_{i+1:03d}"
                cases.append({
                    "id": case_id,
                    "summary": s["summary"],
                    "source_session": s["session_id"]
                })
            
            sub["cases"] = cases
            print(f"\n{ability['name']} > {sub['name']}: 添加 {len(cases)} 个 cases")
    
    # 保存配置
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存到: {CONFIG_PATH}")


if __name__ == "__main__":
    main()
