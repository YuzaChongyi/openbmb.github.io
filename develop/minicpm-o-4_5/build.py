#!/usr/bin/env python3
"""MiniCPM-o 4.5 Demo Page 构建脚本

从 cases.json 配置读取案例列表，
从 collected sessions 读取对话数据，
生成开源用的 data.js 和复制音频文件。

Usage:
    cd /path/to/openbmb.github.io
    python develop/minicpm-o-4_5/build.py
"""

import json
import shutil
import re
from pathlib import Path
from typing import Optional, Union


# === 路径配置 ===
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
CONFIG_PATH = SCRIPT_DIR / "config" / "cases.json"
EDIT_TOOL_CONFIG = SCRIPT_DIR.parent / "edit_tool" / "config" / "data.json"
OUTPUT_DIR = REPO_ROOT / "minicpm-o-4_5"
COLLECTED_DIR = SCRIPT_DIR.parent / "collected"


def get_text(obj: Union[str, dict], lang: str = "zh") -> str:
    """从多语言对象中获取指定语言的文本
    
    Args:
        obj: 字符串或 {"zh": "...", "en": "..."} 对象
        lang: 语言代码
    
    Returns:
        对应语言的文本
    """
    if isinstance(obj, dict):
        return obj.get(lang, obj.get("zh", ""))
    return obj


def load_config() -> dict:
    """加载配置文件
    
    优先从 edit_tool 配置读取（如果存在），否则从 cases.json 读取
    """
    if EDIT_TOOL_CONFIG.exists():
        print(f"[INFO] 从 edit_tool 配置加载: {EDIT_TOOL_CONFIG}")
        with open(EDIT_TOOL_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    
    print(f"[INFO] 从默认配置加载: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_session_dir(source_session: str, ability_id: str) -> Optional[Path]:
    """在 collected 目录中查找 session 目录
    
    Args:
        source_session: session 目录名，如 session_20260129_034105_a264bd2a
        ability_id: ability ID，用于判断语言（english -> en, 其他 -> zh）
    
    Returns:
        session 目录的 Path，找不到返回 None
    """
    # 根据 ability_id 判断语言
    lang = "en" if ability_id == "english" else "zh"
    lang_dir = COLLECTED_DIR / lang
    
    if not lang_dir.exists():
        return None
    
    # 递归搜索
    for session_dir in lang_dir.rglob(source_session):
        if session_dir.is_dir():
            return session_dir
    return None


def read_session_data(session_dir: Path) -> dict:
    """从 session 目录读取完整对话数据
    
    Args:
        session_dir: session 目录路径
    
    Returns:
        {
            "system": {"prefix": ..., "suffix": ...},
            "turns": [{"user_text": ..., "assistant_text": ...}, ...]
        }
    """
    data = {"system": {}, "turns": []}
    
    # 读取 system
    prefix_file = session_dir / "system_prefix.txt"
    suffix_file = session_dir / "system_suffix.txt"
    
    if prefix_file.exists():
        data["system"]["prefix"] = prefix_file.read_text(encoding="utf-8").strip()
    else:
        data["system"]["prefix"] = ""
    
    if suffix_file.exists():
        data["system"]["suffix"] = suffix_file.read_text(encoding="utf-8").strip()
    else:
        data["system"]["suffix"] = ""
    
    # 读取对话轮次
    turn_idx = 0
    while True:
        user_asr_file = session_dir / f"{turn_idx:03d}_user_audio0.asr.txt"
        assistant_text_file = session_dir / f"{turn_idx:03d}_assistant.txt"
        assistant_audio_file = session_dir / f"{turn_idx:03d}_assistant_audio0.mp3"
        
        if not user_asr_file.exists() and not assistant_text_file.exists():
            break
        
        turn = {
            "user_text": "",
            "assistant_text": "",
            "has_assistant_audio": False
        }
        
        if user_asr_file.exists():
            turn["user_text"] = user_asr_file.read_text(encoding="utf-8").strip()
        
        if assistant_text_file.exists():
            turn["assistant_text"] = assistant_text_file.read_text(encoding="utf-8").strip()
        
        if assistant_audio_file.exists():
            turn["has_assistant_audio"] = True
        
        data["turns"].append(turn)
        turn_idx += 1
    
    return data


def copy_audio_files(session_dir: Path, case_id: str, output_audio_dir: Path) -> dict:
    """复制音频文件到输出目录
    
    Args:
        session_dir: 源 session 目录
        case_id: case ID，用于命名子目录
        output_audio_dir: 输出音频根目录
    
    Returns:
        音频路径映射 {"ref_audio": "audio/xxx/ref.mp3", "turns": [...]}
    """
    case_audio_dir = output_audio_dir / case_id
    case_audio_dir.mkdir(parents=True, exist_ok=True)
    
    paths = {"ref_audio": None, "turns": []}
    
    # 复制参考音频
    ref_audio_src = session_dir / "system_ref_audio.mp3"
    if ref_audio_src.exists():
        ref_audio_dst = case_audio_dir / "ref.mp3"
        shutil.copy2(ref_audio_src, ref_audio_dst)
        paths["ref_audio"] = f"audio/{case_id}/ref.mp3"
    
    # 复制每轮 assistant 音频
    turn_idx = 0
    while True:
        assistant_audio_src = session_dir / f"{turn_idx:03d}_assistant_audio0.mp3"
        if not assistant_audio_src.exists():
            break
        
        assistant_audio_dst = case_audio_dir / f"{turn_idx:03d}_assistant.mp3"
        shutil.copy2(assistant_audio_src, assistant_audio_dst)
        paths["turns"].append(f"audio/{case_id}/{turn_idx:03d}_assistant.mp3")
        turn_idx += 1
    
    return paths


def process_case(case: dict, ability_id: str, output_audio_dir: Path) -> Optional[dict]:
    """处理单个 case，读取 session 数据并复制音频
    
    Args:
        case: case 配置
        ability_id: 所属 ability 的 ID
        output_audio_dir: 输出音频目录
    
    Returns:
        处理后的 case 数据（用于 data.js），处理失败返回 None
    """
    # 如果已经有完整数据（从 edit_tool 保存的），直接使用
    if "turns" in case and case["turns"] and "system" in case:
        print(f"  使用已处理的 case: {case['id']}")
        return {
            "id": case["id"],
            "summary": case.get("summary", ""),
            "system": case["system"],
            "turns": case["turns"]
        }
    
    # 否则从 source_session 读取
    source_session = case.get("source_session")
    if not source_session:
        print(f"  [WARN] Case {case.get('id', '?')} 缺少 source_session，跳过")
        return None
    
    session_dir = find_session_dir(source_session, ability_id)
    if not session_dir:
        print(f"  [WARN] 找不到 session: {source_session}，跳过")
        return None
    
    print(f"  处理 case: {case['id']} <- {source_session}")
    
    # 读取 session 数据
    session_data = read_session_data(session_dir)
    
    # 复制音频
    audio_paths = copy_audio_files(session_dir, case["id"], output_audio_dir)
    
    # 构建输出数据（保留多语言 summary）
    output_case = {
        "id": case["id"],
        "summary": case.get("summary", ""),
        "system": {
            "prefix": session_data["system"]["prefix"],
            "ref_audio": audio_paths["ref_audio"],
            "suffix": session_data["system"]["suffix"]
        },
        "turns": []
    }
    
    # 处理对话轮次
    user_text_override = case.get("user_text_override", {})
    for i, turn in enumerate(session_data["turns"]):
        # 允许覆盖 user 文本
        user_text = user_text_override.get(str(i), turn["user_text"])
        
        output_turn = {
            "user_text": user_text,
            "assistant_text": turn["assistant_text"],
            "assistant_audio": audio_paths["turns"][i] if i < len(audio_paths["turns"]) else None
        }
        output_case["turns"].append(output_turn)
    
    return output_case


def build_data(config: dict, output_dir: Path) -> dict:
    """构建 data.js 数据
    
    Args:
        config: cases.json 配置
        output_dir: 输出目录
    
    Returns:
        最终的数据结构
    """
    output_audio_dir = output_dir / "audio"
    output_audio_dir.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "meta": config["meta"],
        "abilities": []
    }
    
    for ability in config["abilities"]:
        output_ability = {
            "id": ability["id"],
            "name": ability["name"],  # 保留多语言对象
            "description": ability.get("description", ""),  # 保留多语言对象
            "sub_abilities": []
        }
        
        for sub_ability in ability.get("sub_abilities", []):
            output_sub = {
                "id": sub_ability["id"],
                "name": sub_ability["name"],  # 保留多语言对象
                "description": sub_ability.get("description", ""),
                "cases": []
            }
            
            for case in sub_ability.get("cases", []):
                processed = process_case(case, ability["id"], output_audio_dir)
                if processed:
                    output_sub["cases"].append(processed)
            
            output_ability["sub_abilities"].append(output_sub)
        
        output_data["abilities"].append(output_ability)
    
    return output_data


def write_data_js(data: dict, output_dir: Path, filename: str = "data.js"):
    """将数据写入 data.js"""
    data_js_path = output_dir / filename
    
    # 格式化 JSON，便于阅读
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    
    content = f"// Auto-generated by build.py - DO NOT EDIT\nconst DEMO_DATA = {json_str};\n"
    
    data_js_path.write_text(content, encoding="utf-8")
    print(f"写入 {data_js_path}")


def main():
    print("=" * 60)
    print("MiniCPM-o 4.5 Demo Page Builder")
    print("=" * 60)
    
    # 清理输出目录中的音频（保留其他文件）
    output_audio_dir = OUTPUT_DIR / "audio"
    if output_audio_dir.exists():
        print(f"清理音频目录: {output_audio_dir}")
        shutil.rmtree(output_audio_dir)
    
    # 加载配置
    config = load_config()
    
    # 构建数据
    print("\n" + "=" * 40)
    print("构建数据")
    print("=" * 40)
    output_data = build_data(config, OUTPUT_DIR)
    
    # 写入单一的 data.js（包含多语言字段）
    write_data_js(output_data, OUTPUT_DIR, "data.js")
    
    # 统计
    total_cases = sum(
        len(sub["cases"])
        for ability in output_data["abilities"]
        for sub in ability["sub_abilities"]
    )
    
    print("\n" + "=" * 60)
    print(f"构建完成！共处理 {total_cases} 个 cases")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
