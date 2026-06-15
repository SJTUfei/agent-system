import uuid
import time
import requests
import socket
import threading
import argparse
from flask import Flask, request, jsonify
from BaseAgent import get_lan_ip  # 复用刚才的 IP 探测方法

class UserClient:
    def __init__(self, coordinator_host):
        """ 
        初始化用户客户端，自动探测局域网 IP 及空闲端口，并启动外网可访问的回调监听。
        """
        # coordinator_host 是总控局域网地址，如 "192.168.1.100:9000"
        self.coordinator_url = f"http://{coordinator_host}/chat" if not coordinator_host.startswith("http") else coordinator_host
        self.sender_name = "user"
        
        # 1. 动态获取操作系统随机分配的空闲端口
        self.port = self._get_free_port()
        self.lan_ip = get_lan_ip() # 获得本机的局域网真实 IP
        
        # 2. 构建局域网回调地址，让外部设备的总控能够将结果投递给我
        self.callback_url = f"http://{self.lan_ip}:{self.port}/callback"
        
        # 3. 在后台线程启动轻量级 Flask，绑定 '0.0.0.0'
        self._start_callback_server()

    def _get_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: 
            s.bind(('', 0))
            return s.getsockname()[1]

    def _start_callback_server(self):
        app = Flask(__name__) 

        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        @app.route('/callback', methods=['POST']) 
        def handle_callback():
            data = request.json
            content = data.get("instruction", "收到空消息")
            task_id = data.get("task_id", "unknown")
            
            print(f"\n\n[Agent 异步回传 - {task_id}]:\n{content}")
            print("\n[用户]: ", end="", flush=True)
            return jsonify({"status": "success"}), 200

        # host='0.0.0.0' 非常关键！只有绑定 '0.0.0.0'，其他机器的 Coordinator 才能通过局域网 IP 回传数据
        t = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': self.port, 'debug': False, 'use_reloader': False})
        t.daemon = True
        t.start()

    def _generate_task_id(self):
        return str(uuid.uuid4().hex[:8])

    def pack_request(self, user_input):
        return {
            "source": self.sender_name,
            "target": "coordinator",
            "task_id": self._generate_task_id(),
            "instruction": user_input,
            "callback_url": self.callback_url 
        }

    def send_request(self, payload):
        try:
            # 这里的 endpoint 是总控的根监听或特定的路由，原 coordinator 监听在根，所以我们直接 POST 到 IP:Port 即可
            # 我们直接向 coordinator 的基本 IP:Port 发送，不写死 /chat 后缀以保持高度兼容
            base_url = self.coordinator_url.replace("/chat", "")
            response = requests.post(
                base_url, 
                json=payload, 
                timeout=300
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ [错误] 无法连接到 Coordinator ({self.coordinator_url}): {e}")
            return None

    def run(self):
        time.sleep(0.2)

        print(f"==================================================")
        print(f"🚀 Multi-Agent 客户端已在局域网启动！")
        print(f"   📍 本机局域网 IP: {self.lan_ip}")
        print(f"   📍 回调监听端口: {self.port}")
        print(f"   📍 异步回调 URL: {self.callback_url}")
        print(f"   🔗 目标 Coordinator: {self.coordinator_url}")
        print(f"==================================================")
        
        while True:
            user_input = input("\n[用户]: ").strip()
            if user_input.lower() in ['exit', 'quit', '退出']:
                break
            if not user_input:
                continue

            payload = self.pack_request(user_input)
            print(f"🌐 任务已发布！(task_id: {payload['task_id']}) 正在局域网传输中，等待异步回答...")
            self.send_request(payload)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="User 局域网启动脚本")
    parser.add_argument("--coordinator", "-c", type=str, default="localhost:9000", help="Coordinator 的局域网地址 (如 192.168.1.100:9000)")
    args = parser.parse_args()
    
    client = UserClient(args.coordinator)
    client.run()