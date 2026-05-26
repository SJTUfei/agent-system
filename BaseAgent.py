from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import socket

def get_lan_ip():
    """
    通用局域网 IP 获取函数。
    通过连接一个外部虚拟地址来让系统选择本机的真实网卡 IP。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 并不需要真正建立连接，只需借此探测本机主路由网卡
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class BaseAgent:
    def __init__(self, name, port):
        self.name = name
        self.port = port
        self.lan_ip = get_lan_ip() # 启动时动态获取本机局域网 IP
    
    def start(self):
        """
        启动 Agent 的局域网监听服务器
        """
        # 绑定 '0.0.0.0' 代表监听包括本机 127.0.0.1 和 局域网真实 IP（如 192.168.x.x）在内的所有网卡
        server_address = ('0.0.0.0', self.port)
        agent_ref = self

        class AgentHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # 屏蔽 http.server 默认的控制台传输日志，由我们的统一 log 代替
                pass

            def do_POST(self):
                try:
                    content_length = int(self.headers['Content-Length'])
                    raw_data = self.rfile.read(content_length)
                    data = json.loads(raw_data.decode('utf-8'))

                    # 记录收到消息的日志
                    agent_ref.log("RECEIVE", data)

                    # 立即给发送者回复 HTTP 200 OK，代表异步任务已接收
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {"status": "accepted", "agent": agent_ref.name}
                    self.wfile.write(json.dumps(response).encode())

                    # 处理具体业务
                    agent_ref.handle_task(data)

                except Exception as e:
                    self.send_error(400, f"Bad Request: {str(e)}")

        httpd = HTTPServer(server_address, AgentHandler)

        print(f"✅ {self.name} 启动成功！")
        print(f"   📍 局域网访问地址: http://{self.lan_ip}:{self.port}")
        print(f"   📍 本地回环地址: http://localhost:{self.port}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n🛑 {self.name} 被手动关闭...")
        except Exception as e:
            print(f"\n❌ {self.name} 发生运行时错误: {e}")
        finally:
            httpd.server_close()
            print(f"🔒 {self.name} 端口已安全释放。")

    def handle_task(self, data):
        raise NotImplementedError("子类必须实现具体的 handle_task 逻辑！")

    def send_to(self, target_host, payload):
        """
        主动发起 POST 请求，支持跨设备传输。
        :param target_host: 接收方的网络终点，支持 "IP:Port" 或 "localhost:Port"
        """
        # 如果只传了端口，默认补全为 localhost
        if isinstance(target_host, int) or target_host.isdigit():
            url = f"http://localhost:{target_host}"
        else:
            url = f"http://{target_host}" if not target_host.startswith("http") else target_host

        self.log("SEND", payload)

        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                print(f"✅ 消息已成功送达至: {url}")
            else:
                print(f"⚠️ 消息送达至 {url}，但对方返回状态码: {response.status_code}")
        except Exception as e:
            print(f"❌ 无法连接到远程地址 {url}: {e}")

    def log(self, direction, message):
        """
        日志格式增强：增加了当前执行节点的局域网 IP 标识，方便跨机对比终端日志
        """
        print(f"\n{'='*20} [{self.name} @ {self.lan_ip}] {'='*20}")
        print(f"方向: {direction}")
        print(f"内容: {json.dumps(message, indent=4, ensure_ascii=False)}")
        print(f"{'='*50}")