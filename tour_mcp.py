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
            # 为了方便酒店 Agent 依赖景点结果，额外补充 area / suggested_time / tags 字段。
            mock_result = self.get_mock_attractions(city)
            
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

    def get_mock_attractions(self, city):
        city_profiles = {
            "上海": [
                {"name": "外滩", "description": "上海经典城市天际线观景地。", "area": "黄浦区", "suggested_time": "晚上", "tags": ["夜景", "地标"]},
                {"name": "南京东路步行街", "description": "靠近外滩的商业步行街。", "area": "黄浦区", "suggested_time": "下午", "tags": ["购物", "交通便利"]},
                {"name": "上海博物馆", "description": "人民广场附近的综合性博物馆。", "area": "人民广场", "suggested_time": "上午", "tags": ["文化", "室内"]},
                {"name": "陆家嘴", "description": "浦东核心商务区和观景区域。", "area": "浦东新区", "suggested_time": "傍晚", "tags": ["地标", "观景"]}
            ],
            "北京": [
                {"name": "故宫博物院", "description": "北京代表性历史文化景点。", "area": "东城区", "suggested_time": "上午", "tags": ["历史", "文化"]},
                {"name": "天安门广场", "description": "可与故宫串联游览的核心地标。", "area": "东城区", "suggested_time": "上午", "tags": ["地标", "历史"]},
                {"name": "颐和园", "description": "湖景和园林结合的经典景点。", "area": "海淀区", "suggested_time": "下午", "tags": ["园林", "慢游"]}
            ],
            "广州": [
                {"name": "广州塔", "description": "广州城市地标，适合夜间观景。", "area": "海珠区", "suggested_time": "晚上", "tags": ["地标", "夜景"]},
                {"name": "沙面岛", "description": "具有历史建筑风貌的慢游街区。", "area": "荔湾区", "suggested_time": "下午", "tags": ["街区", "建筑"]},
                {"name": "陈家祠", "description": "岭南建筑与民俗艺术代表景点。", "area": "荔湾区", "suggested_time": "上午", "tags": ["文化", "建筑"]}
            ]
        }

        return city_profiles.get(city, [
            {"name": f"{city}城市中心景点", "description": f"{city}市区内交通便利的经典景点。", "area": "市中心", "suggested_time": "上午", "tags": ["经典", "交通便利"]},
            {"name": f"{city}特色街区", "description": f"适合体验{city}本地生活和餐饮的街区。", "area": "核心商圈", "suggested_time": "下午", "tags": ["街区", "餐饮"]},
            {"name": f"{city}夜景观赏点", "description": f"适合晚上安排的{city}城市景观地点。", "area": "景观区", "suggested_time": "晚上", "tags": ["夜景", "休闲"]}
        ])

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
