# weather_mcp.py
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from BaseAgent import get_lan_ip  # 引入 IP 探测

class WeatherMcp:
    def __init__(self, name, port):
        self.name = name
        self.port = port
        self.lan_ip = get_lan_ip()

    def handle_task(self, data):
        req_id = data.get("id", None)
        
        if data.get("jsonrpc") != "2.0" or "method" not in data:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid Request"},
                "id": req_id
            }
            
        method = data.get("method")
        params = data.get("params", {})
        
        if method == "get_weather":
            city = params.get("city", "未知")
            print(f"[*] 收到 JSON-RPC 2.0 请求：正在查询 {city} 的天气...")
            
            # 💡 模拟天气数据
            mock_result = {"temp": "15°C", "condition": "晴"}
            
            return {
                "jsonrpc": "2.0",
                "result": mock_result,
                "id": req_id
            }
        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
                "id": req_id
            }

    def start(self):
        # 绑定 '0.0.0.0' 使其可以被局域网内的任何 Agent 访问
        server_address = ('0.0.0.0', self.port)
        weather_mcp = self
        
        class WeatherMcpHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # 屏蔽底层输出

            def do_POST(self):
                try:
                    content_length = int(self.headers['Content-Length'])
                    raw_data = self.rfile.read(content_length)
                    data = json.loads(raw_data.decode('utf-8'))
                    
                    weather_mcp.log("RECEIVE", data)
                    
                    # 💡 获取响应体
                    response_body = weather_mcp.handle_task(data)
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    
                    self.wfile.write(json.dumps(response_body, ensure_ascii=False).encode('utf-8'))
                    weather_mcp.log("SEND", response_body)
                    
                except Exception as e:
                    self.send_error(400, f"Bad Request: {str(e)}")
                    
        httpd = HTTPServer(server_address, WeatherMcpHandler)

        print(f"✅ {self.name} 工具服务端已开启！")
        print(f"   📍 局域网访问地址: http://{self.lan_ip}:{self.port}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n🛑 {self.name} 正在关闭...")
        finally:
            httpd.server_close()

    def log(self, direction, message):
        print(f"\n{'='*20} [{self.name} @ {self.lan_ip}] {'='*20}")
        print(f"方向: {direction}")
        print(f"内容: {json.dumps(message, indent=4, ensure_ascii=False)}")
        print(f"{'='*50}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=8001, help="本节点监听端口 (默认8001)")
    args = parser.parse_args()

    mcp = WeatherMcp("weather_mcp", args.port)
    mcp.start()