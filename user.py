import uuid
import time
import requests
import socket
import threading
from flask import Flask, request, jsonify

class UserClient:
    def __init__(self, server_url):
        """ 
        初始化用户客户端，自动分配空闲端口并启动回调监听。
        """
        # coordinator的地址
        self.server_url = server_url 
        self.sender_name = "User"
        
        # 1. 动态获取系统分配的空闲端口
        self.port = self._get_free_port()
        # 这里的 callback_url 包含了具体的路由 /callback
        #目前传的还是localhost，无法让别的电脑上布置的coordinator访问user，等后续跑通本地就会改掉
        self.callback_url = f"http://localhost:{self.port}/callback"
        
        # 2. 在后台线程启动轻量级服务器
        self._start_callback_server()

    def _get_free_port(self):
        """利用 socket 探测操作系统当前可用的空闲端口"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # 绑定 0 端口是操作系统的“特权指令”，意味着让系统随机分配一个可用端口
            s.bind(('', 0))
            # 获取分配到的真实端口号
            return s.getsockname()[1]

    def _start_callback_server(self):
        """启动后台线程运行 Flask，负责接收 Coordinator 的异步回传"""
        app = Flask(__name__)

        # 禁用 Flask 默认的控制台输出日志，让界面干净点
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        @app.route('/callback', methods=['POST'])
        def handle_callback():
            # 这里接收 Coordinator 发来的 JSON
            data = request.json
            content = data.get("body", {}).get("content", "收到空消息")
            trace_id = data.get("header", {}).get("trace_id", "unknown")
            
            print(f"\n\n[Agent 异步回传 - {trace_id}]: {content}")
            print("[用户]: ", end="", flush=True) # 恢复输入提示符
            return jsonify({"status": "success"}), 200

        # 创建并启动后台线程
        # t.daemon = True 保证主程序（UserClient）关闭时，这个后台监听也随之关闭
        t = threading.Thread(target=app.run, kwargs={'port': self.port, 'debug': False, 'use_reloader': False})
        t.daemon = True
        t.start()

    def _generate_trace_id(self):
        return f"trace_{uuid.uuid4().hex[:8]}"

    def pack_request(self, user_input):
        return {
            "header": {
                "trace_id": self._generate_trace_id(),
                "type": "instruction",
                "sender": self.sender_name,
                "callback_url": self.callback_url # 现在这里是动态真实的 URL
            },
            "body": {
                "content": user_input
            }
        }

    def send_request(self, payload):
        try:
            response = requests.post(
                f"{self.server_url}/chat", #这里传输的是/chat接口，但是coordinator目前还是监听根路径，后续需要修改
                json=payload, 
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[Error] 无法连接到 Coordinator: {e}")
            return None

    def run(self):

        # 打印前稍微等一丢丢，让子线程的 Flask 把废话说完
        time.sleep(0.2)

        print(f"=== Agent System 用户终端 已启动 ===")
        print(f"服务器: {self.server_url} | 动态监听端口: {self.port}")
        
        while True:
            user_input = input("\n[用户]: ").strip()
            if user_input.lower() in ['exit', 'quit', '退出']:
                break
            if not user_input:
                continue

            payload = self.pack_request(user_input)
            print(f"指令已发出 (trace_id: {payload['header']['trace_id']})... 等待异步回复")
            
            # 发送请求（Coordinator 应该立刻返回一个“已收到”的确认）
            self.send_request(payload)

if __name__ == "__main__":
    # 假设 Coordinator 运行在 9000
    client = UserClient(server_url="http://localhost:9000")
    client.run()