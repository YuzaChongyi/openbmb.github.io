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
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs


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


class EditorHandler(SimpleHTTPRequestHandler):
    """自定义 HTTP 处理器"""
    
    def __init__(self, *args, **kwargs):
        # 设置服务根目录为项目根目录
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)
    
    def do_GET(self):
        """处理 GET 请求"""
        # API: 获取数据
        if self.path == '/api/data':
            self._handle_get_data()
        # 音频请求：优先从 resources 提供（热更新）
        elif self.path.startswith('/minicpm-o-4_5/audio/'):
            self._serve_audio(self.path)
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
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    parser = argparse.ArgumentParser(description='MiniCPM-o Demo Editor Server')
    parser.add_argument('--port', type=int, default=8080, help='Server port')
    args = parser.parse_args()
    
    server_address = ('', args.port)
    httpd = HTTPServer(server_address, EditorHandler)
    
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
