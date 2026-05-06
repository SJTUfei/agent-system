import uuid
import time
import requests
import socket #无论是你在浏览器里发起的 HTTP 请求，还是下载文件、发邮件，底层都是通过 socket 来建立连接和传输数据的
import threading
from flask import Flask, request, jsonify

class UserClient:
    def __init__(self, server_url):
        """ 
        初始化用户客户端，自动分配空闲端口并启动回调监听。
        """
        # server_url是coordinator的地址
        self.server_url = server_url 
        self.sender_name = "user"
        
        # 1. 动态获取系统分配的空闲端口，客户端与服务器是不同的，客户端不用固定端口号
        self.port = self._get_free_port()
        # callback_url 是 UserClient 自己在本机后台启动的轻量级服务器地址
        #目前传的还是localhost，无法让别的电脑上布置的coordinator访问user，等后续跑通本地就会改掉
        self.callback_url = f"http://localhost:{self.port}/callback"
        
        # 2. 在后台线程启动轻量级服务器
        self._start_callback_server()

    def _get_free_port(self):
        """利用 socket 探测操作系统当前可用的空闲端口"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: 
            #实例化（创建）了一个套接字对象，socket.AF_INET：表示使用 IPv4 互联网地址家族；socket.SOCK_STREAM：表示使用 TCP 协议，连续不断且保证顺序的
            # 绑定 0 端口是操作系统的“特权指令”，意味着让系统随机分配一个可用端口
            s.bind(('', 0)) #只要端口号对了，所有网卡、局域网、本机都能访问
            # 获取分配到的真实端口号
            return s.getsockname()[1] #s.getsockname()会返回一个包含 IP 和 端口 的元组（Tuple），格式大概像这样：('0.0.0.0', 54321)

    def _start_callback_server(self):
        """启动后台线程运行 Flask，负责接收 Coordinator 的异步回传"""
        app = Flask(__name__) 
        #Flask 是 Python 中最著名的“轻量级 Web 框架”，帮你把底层那些解析 HTTP 报文、处理网络流的脏活累活全包了
        #UserClient 只需要一个极其简单的后台监听服务来接收 Coordinator 发来的异步回调 。用 Flask 可以用最少的代码（几行搞定）在后台跑起一个稳定的 HTTP 服务器

        # 禁用 Flask 默认的控制台输出日志，让界面干净点
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        @app.route('/callback', methods=['POST']) 
        #只要有人通过网络访问了 /callback 这个资源路径，立刻去执行我下面的这个 handle_callback 函数
        # methods参数严格限制该路由允许的 HTTP 请求方法，Coordinator 是要给 UserClient “塞数据（回传 JSON 结果）” 的，这在 HTTP 规范中必须使用 POST 方法
        def handle_callback():
            # 这里接收 Coordinator 发来的 JSON
            data = request.json
            content = data.get("instruction", "收到空消息")
            task_id = data.get("task_id", "unknown")
            
            print(f"\n\n[Agent 异步回传 - {task_id}]: {content}")
            print("[用户]: ", end="", flush=True) # 恢复输入提示符
            return jsonify({"status": "success"}), 200 #在 Flask 的框架设计中，它允许你的路由函数（比如 handle_callback）返回一个元组，最常见的格式就是 (响应正文, 状态码)

        # 创建并启动后台线程
        # t.daemon = True 保证主程序（UserClient）关闭时，这个后台监听也随之关闭
        t = threading.Thread(target=app.run, kwargs={'port': self.port, 'debug': False, 'use_reloader': False})
        t.daemon = True
        t.start()

    def _generate_task_id(self):
        return str(uuid.uuid4().hex[:8])

    def pack_request(self, user_input):
        # 【修改点】：使用严格的扁平化 A2A 格式
        return {
            "source": self.sender_name,
            "target": "coordinator",
            "task_id": self._generate_task_id(),
            "instruction": user_input,
            "callback_url": self.callback_url 
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
            print(f"指令已发出 (task_id: {payload['task_id']})... 等待异步回复")
            
            # 发送请求（Coordinator 应该立刻返回一个“已收到”的确认）
            self.send_request(payload)

if __name__ == "__main__":
    # 假设 Coordinator 运行在 9000
    client = UserClient(server_url="http://localhost:9000")
    client.run()