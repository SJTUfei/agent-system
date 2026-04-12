from http.server import HTTPServer,BaseHTTPRequestHandler
import requests
import json

class BaseAgent:
    def __init__(self,name,port):
        self.name = name
        self.port = port
    
    def start(self):
        """
        启动 Agent 的网络监听服务器
        """
        # 1. 准备服务器地址
        # '' 代表监听本机所有网卡，self.port 是初始化时指定的端口
        server_address = ('', self.port)

        # 这里的 self 是 BaseAgent 的实例，我们把它存给 agent_ref
        # 这样在下面的嵌套类里，我们就能通过‘闭包’访问到它
        agent_ref = self

        # 2. 定义处理规则 (Handler)
        # 每次有 HTTP 请求敲门时，HTTPServer 都会创建一个这个类的实例
        class AgentHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                """
                处理 POST 请求：这是 Agent 之间交换 JSON 数据的标准方式
                """
                try:
                    # A. 获取请求体的大小
                    content_length = int(self.headers['Content-Length'])
                    
                    # B. 读取原始二进制数据
                    raw_data = self.rfile.read(content_length)
                    
                    # C. 将二进制数据解析为 Python 字典 (JSON)
                    data = json.loads(raw_data.decode('utf-8'))

                    # D. 打印收到消息的日志
                    # 这里通过 agent_ref 成功访问到了老板的 log 方法和名字
                    agent_ref.log("RECEIVE", data)

                    # E. 立即给发送者回复 HTTP 200 OK
                    # 在异步回调模式中，先给回执，再慢慢处理业务
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {"status": "accepted", "agent": agent_ref.name}
                    self.wfile.write(json.dumps(response).encode())

                    # F. 把球踢给老板：执行具体的业务逻辑
                    # 注意：如果逻辑很耗时（比如问 AI），建议这里用线程跑，我们稍后优化
                    agent_ref.handle_task(data)

                except Exception as e:
                    # 如果解析失败，返回 400 错误
                    self.send_error(400, f"Bad Request: {str(e)}")

        # 3. 实例化服务器
        # 传入地址和刚才定义好的“接待规则”
        httpd = HTTPServer(server_address, AgentHandler)

        # 4. 进入无限循环监听状态
        print(f"✅ {self.name} 启动成功，正在端口 {self.port} 待命...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n🛑 {self.name} 正在关闭...")
            httpd.server_close()

    def handle_task(self, data):
        # 如果有人直接运行 BaseAgent 并触发了这个函数，直接报错提醒
        raise NotImplementedError("子类必须实现具体的 handle_task 逻辑！")

    def send_to(self, target_port, payload):
        """
        主动发起 POST 请求，将数据发送给另一个 Agent 或用户
        """
        # 1. 构造完整的 URL 地址
        # 实验中我们都在本机运行，所以用 localhost。端口是动态传入的。
        url = f"http://localhost:{target_port}"

        # 2. 打印发送日志（符合实验要求：清晰展现收发路径和 Payload）
        self.log("SEND", payload)

        try:
            # 3. 核心动作：发起 POST 请求
            # json=payload 会自动把字典转为 JSON 字符串，并设置正确的 Header
            # timeout=5 保证如果对方没开机，程序不会死等
            response = requests.post(url, json=payload, timeout=5)

            # 4. 检查对方是否收到（还记得刚才 Handler 里的 200 OK 吗？）
            if response.status_code == 200:
                print(f"✅ 消息已成功送达至端口 {target_port}")
            else:
                print(f"⚠️ 消息送达但对方返回状态码: {response.status_code}")

        except Exception as e:
            # 如果对方端口没监听，或者网络断了，会跳到这里
            print(f"❌ 无法连接到端口 {target_port}: {e}")

    def log(self, direction, message):
        """
        统一的日志打印格式，方便调试
        """
        print(f"\n{'='*20} [{self.name}] {'='*20}")
        print(f"方向: {direction}")
        print(f"内容: {json.dumps(message, indent=4, ensure_ascii=False)}")
        print(f"{'='*50}")