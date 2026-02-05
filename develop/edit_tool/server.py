#!/usr/bin/env python3
"""MiniCPM-o Demo Editor 本地服务器

提供以下功能：
1. 静态文件服务（从项目根目录）
2. 数据加载 API
3. 数据保存 API
4. 构建触发 API

Usage:
    cd /path/to/openbmb.github.io/develop/edit_tool
    python server.py [--port 8080]
"""

import json
import os
import re
import subprocess
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


# 路径配置
SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR / "config"
REPO_ROOT = SCRIPT_DIR.parent.parent
BUILD_SCRIPT = SCRIPT_DIR.parent / "minicpm-o-4_5" / "build.py"

# 确保配置目录存在
CONFIG_DIR.mkdir(exist_ok=True)


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
        else:
            # 静态文件服务
            super().do_GET()
    
    def do_POST(self):
        """处理 POST 请求"""
        if self.path == '/api/data':
            self._handle_save_data()
        elif self.path == '/api/build':
            self._handle_build()
        elif self.path.startswith('/api/upload/'):
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
    
    def _handle_upload(self):
        """处理文件上传"""
        # TODO: 实现音频文件上传
        self.send_error(501, "Upload not implemented yet")
    
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
    print(f"Server root: {REPO_ROOT}")
    print(f"Config dir:  {CONFIG_DIR}")
    print(f"Build script: {BUILD_SCRIPT}")
    print("=" * 50)
    print(f"Editor:  http://localhost:{args.port}/develop/edit_tool/")
    print(f"Preview: http://localhost:{args.port}/minicpm-o-4_5/")
    print("=" * 50)
    print("Press Ctrl+C to stop")
    print()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == '__main__':
    main()
