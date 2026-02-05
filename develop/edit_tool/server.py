"""
MiniCPM-o Demo 编辑器本地服务

提供以下 API：
- GET  /api/data/{lang}           获取数据
- POST /api/data/{lang}           保存数据
- POST /api/upload/{lang}/{path}  上传音频
- GET  /api/collected/list        列出可导入的 sessions
- GET  /api/collected/{session}   获取 session 详情
- POST /api/build                 触发构建

启动方式：
    cd develop/edit_tool
    python server.py
"""

import json
import os
import shutil
import subprocess
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

# 路径配置
EDIT_TOOL_DIR = Path(__file__).parent.resolve()
DEVELOP_DIR = EDIT_TOOL_DIR.parent
PROJECT_ROOT = DEVELOP_DIR.parent
CONFIG_DIR = EDIT_TOOL_DIR / "config"
RESOURCES_DIR = EDIT_TOOL_DIR / "resources"
COLLECTED_DIR = DEVELOP_DIR / "collected"
OUTPUT_DIR = PROJECT_ROOT / "minicpm-o-4_5"

# 确保目录存在
CONFIG_DIR.mkdir(exist_ok=True)
RESOURCES_DIR.mkdir(exist_ok=True)
(RESOURCES_DIR / "zh").mkdir(exist_ok=True)
(RESOURCES_DIR / "en").mkdir(exist_ok=True)


class EditorHandler(SimpleHTTPRequestHandler):
    """编辑器 HTTP 请求处理器"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # 设置静态文件目录为项目根目录，支持预览整个项目
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            self._handle_api_get(path)
        else:
            # 静态文件
            super().do_GET()

    def do_POST(self) -> None:
        """处理 POST 请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            self._handle_api_post(path)
        else:
            self._send_error(404, "Not Found")

    def do_HEAD(self) -> None:
        """处理 HEAD 请求（用于状态检查）"""
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_response(200)
            self._send_cors_headers()
            self.end_headers()
        else:
            super().do_HEAD()

    def do_OPTIONS(self) -> None:
        """处理 CORS 预检请求"""
        self._send_cors_headers()
        self.send_response(200)
        self.end_headers()

    def _send_cors_headers(self) -> None:
        """发送 CORS 头"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: Any, status: int = 200) -> None:
        """发送 JSON 响应"""
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def _send_error(self, status: int, message: str) -> None:
        """发送错误响应"""
        self._send_json({"error": message}, status)

    def _read_body(self) -> bytes:
        """读取请求体"""
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    def _handle_api_get(self, path: str) -> None:
        """处理 API GET 请求"""
        # GET /api/data/{lang}
        if path.startswith("/api/data/"):
            lang = path.split("/")[-1]
            if lang not in ("zh", "en"):
                self._send_error(400, f"Invalid language: {lang}")
                return
            self._get_data(lang)

        # GET /api/collected/list
        elif path == "/api/collected/list":
            self._list_collected()

        # GET /api/collected/{session}
        elif path.startswith("/api/collected/"):
            session_path = path[len("/api/collected/"):]
            self._get_collected_session(session_path)

        else:
            self._send_error(404, "API not found")

    def _handle_api_post(self, path: str) -> None:
        """处理 API POST 请求"""
        # POST /api/data/{lang}
        if path.startswith("/api/data/"):
            lang = path.split("/")[-1]
            if lang not in ("zh", "en"):
                self._send_error(400, f"Invalid language: {lang}")
                return
            self._save_data(lang)

        # POST /api/upload/{lang}/...
        elif path.startswith("/api/upload/"):
            parts = path[len("/api/upload/"):].split("/", 1)
            if len(parts) < 2:
                self._send_error(400, "Invalid upload path")
                return
            lang, resource_path = parts
            self._upload_file(lang, resource_path)

        # POST /api/build
        elif path == "/api/build":
            self._trigger_build()

        else:
            self._send_error(404, "API not found")

    def _get_data(self, lang: str) -> None:
        """获取数据
        
        优先级：
        1. edit_tool/config/data_{lang}.json（编辑器保存的完整数据）
        2. minicpm-o-4_5/data.js 或 data_en.js（构建产物，包含完整对话）
        3. 空数据
        """
        # 1. 尝试从 edit_tool 配置加载
        data_file = CONFIG_DIR / f"data_{lang}.json"
        if data_file.exists():
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 检查是否有完整对话数据
            if self._has_full_data(data):
                self._send_json(data)
                return
        
        # 2. 尝试从 data.js 加载完整数据
        js_file = OUTPUT_DIR / ("data.js" if lang == "zh" else "data_en.js")
        if js_file.exists():
            try:
                content = js_file.read_text(encoding="utf-8")
                # 提取 JSON 部分
                import re
                match = re.search(r'const DEMO_DATA = ({[\s\S]*});', content)
                if match:
                    data = json.loads(match.group(1))
                    self._send_json(data)
                    return
            except Exception as e:
                print(f"[WARN] 解析 {js_file} 失败: {e}")
        
        # 3. 返回空数据
        self._send_json({
            "meta": {"title": "MiniCPM-o 4.5", "description": ""},
            "abilities": []
        })
    
    def _has_full_data(self, data: dict) -> bool:
        """检查数据是否包含完整对话内容"""
        try:
            for ability in data.get("abilities", []):
                for sub in ability.get("sub_abilities", []):
                    for case in sub.get("cases", []):
                        # 有 turns 且 turns 不为空，认为是完整数据
                        if case.get("turns") and len(case["turns"]) > 0:
                            return True
            return False
        except Exception:
            return False

    def _save_data(self, lang: str) -> None:
        """保存数据"""
        try:
            body = self._read_body()
            data = json.loads(body.decode("utf-8"))

            data_file = CONFIG_DIR / f"data_{lang}.json"
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(data, ensure_ascii=False, indent=2, fp=f)

            self._send_json({"success": True, "message": f"Saved to {data_file.name}"})
            print(f"[SAVED] {data_file}")

        except json.JSONDecodeError as e:
            self._send_error(400, f"Invalid JSON: {e}")
        except Exception as e:
            self._send_error(500, f"Save failed: {e}")

    def _upload_file(self, lang: str, resource_path: str) -> None:
        """上传文件"""
        try:
            body = self._read_body()
            
            target_path = RESOURCES_DIR / lang / resource_path
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with open(target_path, "wb") as f:
                f.write(body)

            relative_path = f"resources/{lang}/{resource_path}"
            self._send_json({
                "success": True,
                "path": relative_path,
                "message": f"Uploaded to {relative_path}"
            })
            print(f"[UPLOADED] {target_path}")

        except Exception as e:
            self._send_error(500, f"Upload failed: {e}")

    def _list_collected(self) -> None:
        """列出 collected 中的所有 sessions"""
        sessions: List[Dict[str, Any]] = []

        for lang in ("zh", "en"):
            lang_dir = COLLECTED_DIR / lang
            if not lang_dir.exists():
                continue

            # 遍历所有分类目录
            for category_dir in lang_dir.iterdir():
                if not category_dir.is_dir():
                    continue

                # 遍历所有 session 目录
                for session_dir in category_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    if not session_dir.name.startswith("session_"):
                        continue

                    # 收集 session 信息
                    session_info = self._parse_session_info(session_dir, lang, category_dir.name)
                    if session_info:
                        sessions.append(session_info)

        # 按时间倒序
        sessions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        self._send_json(sessions)

    def _parse_session_info(self, session_dir: Path, lang: str, category: str) -> Optional[Dict[str, Any]]:
        """解析 session 目录信息"""
        try:
            # 提取时间戳
            name_parts = session_dir.name.split("_")
            timestamp = "_".join(name_parts[1:3]) if len(name_parts) >= 3 else ""

            # 检查是否有 ref audio
            has_ref = (session_dir / "system_ref_audio.mp3").exists()

            # 统计 turn 数量
            turn_count = len(list(session_dir.glob("*_assistant.txt")))

            return {
                "id": session_dir.name,
                "path": f"{lang}/{category}/{session_dir.name}",
                "lang": lang,
                "category": category,
                "timestamp": timestamp,
                "has_ref": has_ref,
                "turn_count": turn_count
            }
        except Exception:
            return None

    def _get_collected_session(self, session_path: str) -> None:
        """获取 session 详情"""
        session_dir = COLLECTED_DIR / session_path

        if not session_dir.exists():
            self._send_error(404, f"Session not found: {session_path}")
            return

        try:
            result: Dict[str, Any] = {
                "path": session_path,
                "system": {},
                "turns": []
            }

            # 读取 system prefix
            prefix_file = session_dir / "system_prefix.txt"
            if prefix_file.exists():
                result["system"]["prefix"] = prefix_file.read_text(encoding="utf-8").strip()

            # 读取 system suffix
            suffix_file = session_dir / "system_suffix.txt"
            if suffix_file.exists():
                result["system"]["suffix"] = suffix_file.read_text(encoding="utf-8").strip()

            # ref audio 路径
            ref_audio = session_dir / "system_ref_audio.mp3"
            if ref_audio.exists():
                result["system"]["ref_audio"] = str(ref_audio.relative_to(COLLECTED_DIR))

            # 读取 turns
            turn_files = sorted(session_dir.glob("*_assistant.txt"))
            for turn_file in turn_files:
                turn_idx = turn_file.name.split("_")[0]
                turn: Dict[str, Any] = {}

                # user text
                user_text_file = session_dir / f"{turn_idx}_user_audio0.asr.txt"
                if user_text_file.exists():
                    turn["user_text"] = user_text_file.read_text(encoding="utf-8").strip()

                # assistant text
                turn["assistant_text"] = turn_file.read_text(encoding="utf-8").strip()

                # assistant audio
                assistant_audio = session_dir / f"{turn_idx}_assistant_audio0.mp3"
                if assistant_audio.exists():
                    turn["assistant_audio"] = str(assistant_audio.relative_to(COLLECTED_DIR))

                result["turns"].append(turn)

            self._send_json(result)

        except Exception as e:
            self._send_error(500, f"Failed to read session: {e}")

    def _trigger_build(self) -> None:
        """触发构建"""
        try:
            build_script = DEVELOP_DIR / "minicpm-o-4_5" / "build.py"

            if not build_script.exists():
                self._send_error(404, "Build script not found")
                return

            # 运行构建脚本
            result = subprocess.run(
                [sys.executable, str(build_script)],
                cwd=str(DEVELOP_DIR / "minicpm-o-4_5"),
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                self._send_json({
                    "success": True,
                    "message": "Build completed",
                    "output": result.stdout
                })
                print(f"[BUILD] Success")
            else:
                self._send_json({
                    "success": False,
                    "message": "Build failed",
                    "error": result.stderr,
                    "output": result.stdout
                }, 500)
                print(f"[BUILD] Failed: {result.stderr}")

        except Exception as e:
            self._send_error(500, f"Build failed: {e}")


def run_server(port: int = 8080) -> None:
    """启动服务器"""
    server_address = ("", port)
    httpd = HTTPServer(server_address, EditorHandler)

    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║           MiniCPM-o Demo Editor Server                        ║
╠═══════════════════════════════════════════════════════════════╣
║  编辑器地址: http://localhost:{port}                            ║
║  API 文档:                                                     ║
║    GET  /api/data/{{zh|en}}         获取数据                    ║
║    POST /api/data/{{zh|en}}         保存数据                    ║
║    POST /api/upload/{{lang}}/{{path}} 上传音频                   ║
║    GET  /api/collected/list        列出 sessions              ║
║    POST /api/build                 触发构建                    ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    print(f"[INFO] Serving from: {EDIT_TOOL_DIR}")
    print(f"[INFO] Config dir: {CONFIG_DIR}")
    print(f"[INFO] Resources dir: {RESOURCES_DIR}")
    print(f"[INFO] Press Ctrl+C to stop\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped")
        httpd.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MiniCPM-o Demo Editor Server")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    args = parser.parse_args()

    run_server(args.port)
