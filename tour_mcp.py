# tour_mcp.py
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class TourMcp:
    def __init__(self, name, port):
        self.name = name
        self.port = port

    def handle_task(self, data):
        """
        纯粹的工具执行逻辑：校验 JSON-RPC 2.0 规范并返回结果
        """
        req_id = data.get("id", None)
        
        # 1. 严格校验请求规范
        if data.get("jsonrpc") != "2.0" or "method" not in data:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid Request"},
                "id": req_id
            }
            
        method = data.get("method")
        params = data.get("params", {})
        
        # 2. 路由到具体的工具函数
        if method == "get_attractions":
            city = params.get("city", "未知")
            print(f"[*] 收到查询请求：正在查询 {city} 的景点...")
            
            # 💡 这里写死模拟数据，真实业务中这里会使用 requests 调用景点 API
            mock_result = [
                {"name": "景点1", "description": "描述1"},
                {"name": "景点2", "description": "描述2"},
                {"name": "景点3", "description": "描述3"}
            ]
            
            # 3. 构造标准的 JSON-RPC 响应
            return {
                "jsonrpc": "2.0",
                "result": mock_result,
                "id": req_id
            }
        else:
            # 找不到对应的方法
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
                "id": req_id
            }

    def start(self):
        server_address = ('', self.port)
        tour_mcp = self
        
        class TourMcpHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    content_length = int(self.headers['Content-Length'])
                    raw_data = self.rfile.read(content_length)
                    data = json.loads(raw_data.decode('utf-8'))
                    
                    tour_mcp.log("RECEIVE", data)
                    
                    # 💡 调用 handle_task，拿到真正的结果字典
                    response_body = tour_mcp.handle_task(data)
                    
                    # 开始发送同步响应
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    
                    # 💡 把结果打包当场发送回去
                    self.wfile.write(json.dumps(response_body, ensure_ascii=False).encode('utf-8'))
                    
                    tour_mcp.log("SEND", response_body)
                    
                except Exception as e:
                    self.send_error(400, f"Bad Request: {str(e)}")
                    
        httpd = HTTPServer(server_address, TourMcpHandler)

        print(f"✅ {self.name} 启动成功，作为独立工具服务正在端口 {self.port} 待命...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n🛑 {self.name} 正在关闭...")
            httpd.server_close()

    def log(self, direction, message):
        print(f"\n{'='*20} [{self.name}] {'='*20}")
        print(f"方向: {direction}")
        print(f"内容: {json.dumps(message, indent=4, ensure_ascii=False)}")
        print(f"{'='*50}")

if __name__ == "__main__":
    # 监听 8002 端口
    mcp = TourMcp("tour_mcp", 8002)
    mcp.start()