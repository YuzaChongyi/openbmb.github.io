#!/usr/bin/env python3
"""MiniCPM-o Demo Editor 本地服务器

提供以下功能：
1. 静态文件服务（从项目根目录）
2. 资源优先服务（edit_tool/resources 优先于 minicpm-o-4_5，实现热更新）
3. 数据加载/保存 API
4. 音频文件上传 API
5. 构建触发 API

Usage:
    cd /path/to/openbmb.github.io/develop/edit_tool
    python server.py [--port 8080]
"""

import json
import os
import re
import subprocess
import argparse
import base64
import mimetypes
import tempfile
import shutil
import traceback
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import requests as requests_lib
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests_lib = None


# 路径配置
SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR / "config"
RESOURCES_DIR = SCRIPT_DIR / "resources"
REPO_ROOT = SCRIPT_DIR.parent.parent
BUILD_SCRIPT = SCRIPT_DIR.parent / "minicpm-o-4_5" / "build.py"

# 确保目录存在
CONFIG_DIR.mkdir(exist_ok=True)
RESOURCES_DIR.mkdir(exist_ok=True)
(RESOURCES_DIR / "audio").mkdir(exist_ok=True)


# === 远程 Session 导入支持 ===

def _load_env() -> dict:
    """从 .env 文件加载配置（key=value 格式）

    Returns:
        配置字典
    """
    env_path = SCRIPT_DIR / ".env"
    config: dict = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
    return config

_ENV = _load_env()
GEMINI_API_KEY = _ENV.get("GEMINI_API_KEY", "")
GEMINI_BASE_URL = _ENV.get("GEMINI_BASE_URL", "")
GEMINI_MODEL = _ENV.get("GEMINI_MODEL", "")

# 后台 ASR 任务跟踪
_transcription_tasks: dict = {}  # case_id -> {"total", "completed", "results", "errors", "done"}
_transcription_lock = threading.Lock()


def _download_url(url: str, username: str, password: str) -> bytes:
    """下载 URL 内容（支持 Basic Auth）

    Args:
        url: 目标 URL
        username: Basic Auth 用户名
        password: Basic Auth 密码

    Returns:
        响应内容的 bytes

    Raises:
        RuntimeError: requests 未安装
        requests.HTTPError: 请求失败
    """
    if not requests_lib:
        raise RuntimeError("需要安装 requests 库: pip install requests")
    auth = (username, password) if username else None
    resp = requests_lib.get(url, auth=auth, timeout=120, verify=False)
    resp.raise_for_status()
    return resp.content


def _transcribe_audio(audio_path: Path) -> str:
    """使用 Gemini API 转录音频文件为文本

    Args:
        audio_path: 本地音频文件路径

    Returns:
        转录文本

    Raises:
        RuntimeError: requests 未安装
        requests.HTTPError: API 请求失败
    """
    if not requests_lib:
        raise RuntimeError("需要安装 requests 库: pip install requests")
    if not GEMINI_API_KEY or not GEMINI_BASE_URL:
        raise RuntimeError("缺少 ASR 配置，请在 develop/edit_tool/.env 中设置 GEMINI_API_KEY 和 GEMINI_BASE_URL")

    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    suffix = audio_path.suffix.lower().lstrip(".")
    audio_format = suffix if suffix in ("wav", "mp3", "flac", "ogg") else "wav"

    resp = requests_lib.post(
        f"{GEMINI_BASE_URL}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEMINI_API_KEY}",
        },
        json={
            "model": GEMINI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个音频转录助手。用户会发送音频，你只需输出音频中说话人的原文文本，保留自然的标点符号。不要添加任何解释、翻译或额外内容。"
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
                        {"type": "text", "text": "transcribe"}
                    ]
                }
            ]
        },
        verify=False,
        timeout=300
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]

    # 清理可能残留的指令文本
    for noise in ["请转录这段音频的内容", "只输出转录的原文文本", "不要添加任何解释或标点修正"]:
        raw = raw.replace(noise, "")
    return raw.strip()


def _convert_wav_to_mp3(src: Path, dst: Path) -> bool:
    """尝试使用 ffmpeg 将 wav 转为 mp3

    Args:
        src: 源 wav 文件
        dst: 目标 mp3 文件

    Returns:
        转换是否成功
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-i', str(src), '-y', '-codec:a', 'libmp3lame', '-qscale:a', '2', str(dst)],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _save_audio_resource(src: Path, audio_dir: Path, target_basename: str) -> str:
    """将音频文件保存到资源目录（尝试转 mp3）

    Args:
        src: 源文件路径
        audio_dir: 目标目录 (resources/audio/{case_id}/)
        target_basename: 目标文件名（不含扩展名），如 "ref" 或 "000_assistant"

    Returns:
        相对路径，如 "audio/{case_id}/ref.mp3"
    """
    case_id = audio_dir.name
    if src.suffix.lower() == '.wav' and _convert_wav_to_mp3(src, audio_dir / f'{target_basename}.mp3'):
        return f'audio/{case_id}/{target_basename}.mp3'
    else:
        ext = src.suffix
        shutil.copy2(src, audio_dir / f'{target_basename}{ext}')
        return f'audio/{case_id}/{target_basename}{ext}'


def import_remote_session(session_url: str, username: str, password: str, case_id: str) -> dict:
    """从远程 session URL 导入为 case 数据（ASR 异步执行）

    同步完成：下载文件、处理音频资源、提取助手文本。
    异步执行：用户音频 ASR 转录（后台线程，通过轮询获取结果）。

    Args:
        session_url: session URL（可包含 session_view.html 后缀）
        username: Basic Auth 用户名
        password: Basic Auth 密码
        case_id: 新 case 的唯一 ID

    Returns:
        case 数据字典。user_text 为 "[转录中...]" 表示 ASR 尚未完成。
        额外字段 _has_pending_asr 标记是否有后台任务。

    Raises:
        RuntimeError: 下载失败
    """
    base_url = session_url.replace('/session_view.html', '').rstrip('/')

    # 1. 获取页面（支持目录列表和 Session Viewer 两种格式）
    html = _download_url(f"{base_url}/", username, password).decode('utf-8')

    # 从 <a href="..."> 和 <audio/img src="..."> 中提取文件引用
    href_files = re.findall(r'<a href="([^"]+)">', html)
    src_files = re.findall(r'\bsrc="([^"]+)"', html)
    all_refs = set(href_files + src_files)
    files = sorted([f for f in all_refs
                    if not f.startswith(('..', '/', '#', 'http', 'data:'))
                    and '.' in f])

    # 补充已知文件名（Session Viewer 不一定引用 txt 文件）
    for known in ['system_prefix.txt', 'system_suffix.txt']:
        if known not in files:
            files.append(known)

    print(f"[import] 发现 {len(files)} 个文件: {files}")

    audio_dir = RESOURCES_DIR / "audio" / case_id
    audio_dir.mkdir(parents=True, exist_ok=True)

    # 手动管理 tmpdir 生命周期（后台 ASR 线程负责清理）
    tmpdir = Path(tempfile.mkdtemp(prefix=f"import_{case_id}_"))

    try:
        # 2. 下载所有文件（跳过 404 等错误）
        for fname in files:
            print(f"[import] 下载: {fname}")
            try:
                content = _download_url(f"{base_url}/{fname}", username, password)
                (tmpdir / fname).write_bytes(content)
            except Exception as e:
                print(f"[import] 跳过: {fname} ({e})")

        # 3. 读取 system prompt
        sys_prefix = ''
        sys_suffix = ''
        if (tmpdir / 'system_prefix.txt').exists():
            sys_prefix = (tmpdir / 'system_prefix.txt').read_text(encoding='utf-8').strip()
        if (tmpdir / 'system_suffix.txt').exists():
            sys_suffix = (tmpdir / 'system_suffix.txt').read_text(encoding='utf-8').strip()

        # 4. 处理参考音频
        ref_file = next((f for f in files if f.startswith('system_ref_audio')), None)
        ref_audio_path = ''
        if ref_file:
            ref_audio_path = _save_audio_resource(tmpdir / ref_file, audio_dir, 'ref')

        # 5. 处理对话轮次（不做 ASR，收集待转录列表）
        turns = []
        pending_asr: dict = {}  # {turn_idx: user_audio_filename}
        turn_idx = 0
        while True:
            pfx = f'{turn_idx:03d}'
            user_audio = next((f for f in files if f.startswith(f'{pfx}_user_audio0')), None)
            asst_txt_name = f'{pfx}_assistant.txt'
            asst_audio = next((f for f in files if f.startswith(f'{pfx}_assistant_audio0')), None)

            if not user_audio and not asst_audio:
                break

            # 标记需要 ASR 的 turn
            user_text = ''
            if user_audio and (tmpdir / user_audio).exists():
                pending_asr[turn_idx] = user_audio
                user_text = '[转录中...]'

            # 读取助手文本（新格式可能未列出 txt，按需下载）
            asst_text = ''
            if (tmpdir / asst_txt_name).exists():
                asst_text = (tmpdir / asst_txt_name).read_text(encoding='utf-8').strip()
            elif asst_txt_name not in files:
                try:
                    txt_content = _download_url(f"{base_url}/{asst_txt_name}", username, password)
                    (tmpdir / asst_txt_name).write_bytes(txt_content)
                    asst_text = txt_content.decode('utf-8').strip()
                except Exception:
                    pass

            # 处理助手音频
            asst_audio_path = ''
            if asst_audio and (tmpdir / asst_audio).exists():
                asst_audio_path = _save_audio_resource(
                    tmpdir / asst_audio, audio_dir, f'{pfx}_assistant'
                )

            turns.append({
                'user_text': user_text,
                'assistant_text': asst_text,
                'assistant_audio': asst_audio_path
            })
            turn_idx += 1
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

    # 启动后台 ASR 任务（tmpdir 由后台线程清理）
    has_pending = bool(pending_asr)
    if has_pending:
        _start_transcription_task(case_id, pending_asr, tmpdir)
    else:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"[import] 导入完成: {len(turns)} 轮对话, {len(pending_asr)} 条待转录")

    return {
        'id': case_id,
        'summary': {'zh': '', 'en': ''},
        'system': {
            'prefix': sys_prefix,
            'ref_audio': ref_audio_path,
            'suffix': sys_suffix
        },
        'turns': turns,
        '_has_pending_asr': has_pending
    }


def _start_transcription_task(case_id: str, pending_audio: dict, tmpdir: Path) -> None:
    """启动后台 ASR 转录任务

    Args:
        case_id: case ID
        pending_audio: {turn_idx: user_audio_filename}（文件在 tmpdir 中）
        tmpdir: 临时目录，由后台线程负责清理
    """
    with _transcription_lock:
        _transcription_tasks[case_id] = {
            "total": len(pending_audio),
            "completed": 0,
            "results": {},
            "errors": {},
            "done": False
        }

    thread = threading.Thread(
        target=_transcription_worker,
        args=(case_id, pending_audio, tmpdir),
        daemon=True
    )
    thread.start()
    print(f"[import] 启动后台 ASR: {case_id}, {len(pending_audio)} 条音频")


def _transcription_worker(case_id: str, pending_audio: dict, tmpdir: Path) -> None:
    """后台 ASR 转录 worker

    逐条转录用户音频，实时更新任务状态，最后清理临时目录。
    """
    try:
        for turn_idx, audio_filename in sorted(pending_audio.items()):
            audio_path = tmpdir / audio_filename
            print(f"[asr-{case_id}] 转录 turn {turn_idx}: {audio_filename}")
            try:
                text = _transcribe_audio(audio_path)
                print(f"[asr-{case_id}] turn {turn_idx} 完成: {text[:80]}")
                with _transcription_lock:
                    task = _transcription_tasks[case_id]
                    task["results"][str(turn_idx)] = text
                    task["completed"] += 1
            except Exception as e:
                print(f"[asr-{case_id}] turn {turn_idx} 失败: {e}")
                with _transcription_lock:
                    task = _transcription_tasks[case_id]
                    task["errors"][str(turn_idx)] = str(e)
                    task["completed"] += 1
    finally:
        with _transcription_lock:
            _transcription_tasks[case_id]["done"] = True
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"[asr-{case_id}] 任务结束，临时目录已清理")


class EditorHandler(SimpleHTTPRequestHandler):
    """自定义 HTTP 处理器"""
    
    def __init__(self, *args, **kwargs):
        # 设置服务根目录为项目根目录
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)
    
    def do_GET(self):
        """处理 GET 请求"""
        # 去掉 query string，仅用路径部分做路由
        parsed = urlparse(self.path)
        clean_path = parsed.path
        
        # API: 获取数据
        if clean_path == '/api/data':
            self._handle_get_data()
        elif clean_path == '/api/transcription-status':
            self._handle_transcription_status()
        # 音频请求：优先从 resources 提供（热更新）
        elif clean_path.startswith('/minicpm-o-4_5/audio/'):
            self._serve_audio(clean_path)
        else:
            # 静态文件服务
            super().do_GET()
    
    def do_POST(self):
        """处理 POST 请求"""
        if self.path == '/api/data':
            self._handle_save_data()
        elif self.path == '/api/build':
            self._handle_build()
        elif self.path == '/api/upload':
            self._handle_upload()
        elif self.path == '/api/import-session':
            self._handle_import_session()
        else:
            self.send_error(404, "Not Found")
    
    def do_HEAD(self):
        """处理 HEAD 请求"""
        if self.path.startswith('/api/'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
        else:
            super().do_HEAD()
    
    def _serve_audio(self, request_path):
        """优先从 resources 提供音频文件（热更新支持）
        
        请求路径: /minicpm-o-4_5/audio/case_id/file.mp3
        优先级 1: develop/edit_tool/resources/audio/case_id/file.mp3
        优先级 2: minicpm-o-4_5/audio/case_id/file.mp3 (已构建的)
        """
        # 提取相对路径: audio/case_id/file.mp3
        relative_path = request_path.replace('/minicpm-o-4_5/', '', 1)
        
        # 优先从 resources 提供
        resource_file = RESOURCES_DIR / relative_path
        if resource_file.exists() and resource_file.is_file():
            self._send_file(resource_file)
            return
        
        # 回退到已构建的文件
        built_file = REPO_ROOT / "minicpm-o-4_5" / relative_path
        if built_file.exists() and built_file.is_file():
            self._send_file(built_file)
            return
        
        self.send_error(404, f"Audio file not found: {relative_path}")
    
    def _send_file(self, file_path):
        """发送文件响应"""
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'application/octet-stream'
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')  # 热更新不缓存
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")
    
    def _handle_get_data(self):
        """获取数据"""
        config_path = CONFIG_DIR / "data.json"
        
        if config_path.exists():
            # 从编辑器配置加载
            print(f"[GET /api/data] 从编辑器配置加载: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # 回退到 data.js
            demo_data_path = REPO_ROOT / "minicpm-o-4_5" / "data.js"
            if demo_data_path.exists():
                print(f"[GET /api/data] 从 data.js 加载: {demo_data_path}")
                with open(demo_data_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 提取 JSON 部分
                    match = re.search(r"const DEMO_DATA = (\{.*\});", content, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                    else:
                        self.send_error(500, "Could not parse data.js")
                        return
            else:
                # 回退到 cases.json
                cases_path = SCRIPT_DIR.parent / "minicpm-o-4_5" / "config" / "cases.json"
                if cases_path.exists():
                    print(f"[GET /api/data] 从 cases.json 加载: {cases_path}")
                    with open(cases_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    self.send_error(404, "No data file found")
                    return
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    
    def _handle_save_data(self):
        """保存数据"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            file_path = CONFIG_DIR / "data.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"[POST /api/data] 保存成功: {file_path}")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": "Data saved successfully"
            }).encode('utf-8'))
            
        except json.JSONDecodeError as e:
            print(f"[POST /api/data] JSON 解析错误: {e}")
            self.send_error(400, f"Invalid JSON: {e}")
        except Exception as e:
            print(f"[POST /api/data] 保存错误: {e}")
            self.send_error(500, f"Server error: {e}")
    
    def _handle_upload(self):
        """处理音频文件上传
        
        请求格式 (JSON):
        {
            "path": "audio/case_id/ref.mp3",
            "data": "<base64 encoded file content>"
        }
        
        文件保存到: develop/edit_tool/resources/audio/case_id/ref.mp3
        """
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
            
            file_path = payload.get('path', '')
            file_data_b64 = payload.get('data', '')
            
            if not file_path or not file_data_b64:
                self.send_error(400, "Missing 'path' or 'data' field")
                return
            
            # 安全检查：防止路径遍历
            if '..' in file_path or file_path.startswith('/'):
                self.send_error(400, "Invalid file path")
                return
            
            # 解码文件内容
            file_bytes = base64.b64decode(file_data_b64)
            
            # 保存到 resources 目录
            save_path = RESOURCES_DIR / file_path
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(file_bytes)
            
            file_size_kb = len(file_bytes) / 1024
            print(f"[POST /api/upload] 上传成功: {save_path} ({file_size_kb:.1f} KB)")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": f"File uploaded: {file_path}",
                "path": file_path,
                "size": len(file_bytes)
            }).encode('utf-8'))
            
        except base64.binascii.Error as e:
            print(f"[POST /api/upload] Base64 解码错误: {e}")
            self.send_error(400, f"Invalid base64 data: {e}")
        except json.JSONDecodeError as e:
            print(f"[POST /api/upload] JSON 解析错误: {e}")
            self.send_error(400, f"Invalid JSON: {e}")
        except Exception as e:
            print(f"[POST /api/upload] 上传错误: {e}")
            self.send_error(500, f"Upload error: {e}")
    
    def _handle_build(self):
        """触发构建"""
        try:
            print(f"[POST /api/build] 开始构建...")
            result = subprocess.run(
                ['python3', str(BUILD_SCRIPT)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"[POST /api/build] 构建成功")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "message": "Build completed",
                    "output": result.stdout
                }).encode('utf-8'))
            else:
                print(f"[POST /api/build] 构建失败: {result.stderr}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "error",
                    "message": "Build failed",
                    "error": result.stderr,
                    "output": result.stdout
                }).encode('utf-8'))
                
        except Exception as e:
            print(f"[POST /api/build] 构建错误: {e}")
            self.send_error(500, f"Build error: {e}")
    
    def _handle_import_session(self):
        """处理远程 session 导入请求

        POST /api/import-session
        {
            "url": "http://...session_view.html",
            "username": "xu",
            "password": "9679",
            "case_id": "english_conv_004"
        }
        """
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode('utf-8'))
            url = payload.get('url', '')
            username = payload.get('username', '')
            password = payload.get('password', '')
            case_id = payload.get('case_id', '')

            if not url or not case_id:
                self.send_error(400, "Missing 'url' or 'case_id'")
                return

            print(f"[POST /api/import-session] 导入: {url} → {case_id}")
            case_data = import_remote_session(url, username, password, case_id)
            has_pending_asr = case_data.pop('_has_pending_asr', False)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "case": case_data,
                "has_pending_asr": has_pending_asr
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            print(f"[POST /api/import-session] 错误: {e}")
            traceback.print_exc()
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "message": str(e)
            }, ensure_ascii=False).encode('utf-8'))

    def _handle_transcription_status(self):
        """查询后台 ASR 转录状态

        GET /api/transcription-status?case_id=xxx
        返回: {"total", "completed", "results": {idx: text}, "errors": {idx: msg}, "done": bool}
        """
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        case_id = params.get('case_id', [''])[0]

        if not case_id:
            self.send_error(400, "Missing 'case_id' parameter")
            return

        with _transcription_lock:
            task = _transcription_tasks.get(case_id)

        if not task:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "not_found",
                "case_id": case_id
            }).encode('utf-8'))
            return

        with _transcription_lock:
            response = {
                "status": "ok",
                "case_id": case_id,
                "total": task["total"],
                "completed": task["completed"],
                "results": dict(task["results"]),
                "errors": dict(task["errors"]),
                "done": task["done"]
            }

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {args[0]}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP Server，支持并发请求（ASR 轮询不会被阻塞）"""
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description='MiniCPM-o Demo Editor Server')
    parser.add_argument('--port', type=int, default=8080, help='Server port')
    args = parser.parse_args()
    
    server_address = ('', args.port)
    httpd = ThreadedHTTPServer(server_address, EditorHandler)
    
    print("=" * 50)
    print("MiniCPM-o Demo Editor Server")
    print("=" * 50)
    print(f"Server root:  {REPO_ROOT}")
    print(f"Config dir:   {CONFIG_DIR}")
    print(f"Resources:    {RESOURCES_DIR}")
    print(f"Build script: {BUILD_SCRIPT}")
    print("=" * 50)
    print(f"Editor:  http://localhost:{args.port}/develop/edit_tool/")
    print(f"Preview: http://localhost:{args.port}/minicpm-o-4_5/")
    print("=" * 50)
    print("Audio serving: resources/ > minicpm-o-4_5/audio/")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == '__main__':
    main()
