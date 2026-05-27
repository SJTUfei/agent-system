from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class HotelMcp:
    def __init__(self, name, port):
        self.name = name
        self.port = port

    def handle_task(self, data):
        """Handle JSON-RPC 2.0 requests for hotel recommendations."""
        req_id = data.get("id", None)

        if data.get("jsonrpc") != "2.0" or "method" not in data:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid Request"},
                "id": req_id
            }

        method = data.get("method")
        params = data.get("params", {})

        if method == "recommend_hotels":
            city = params.get("city", "未知")
            areas = params.get("areas", [])
            budget_level = params.get("budget_level", "mid")
            preferences = params.get("preferences", [])
            attractions = params.get("attractions", [])
            print(f"[*] 收到酒店推荐请求：城市={city}, 区域={areas}, 预算={budget_level}")

            return {
                "jsonrpc": "2.0",
                "result": self.recommend_hotels(city, areas, budget_level, preferences, attractions),
                "id": req_id
            }

        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
            "id": req_id
        }

    def recommend_hotels(self, city, areas, budget_level, preferences, attractions):
        target_areas = areas or ["市中心"]
        primary_area = target_areas[0]
        attraction_text = "、".join(attractions[:3]) if attractions else "主要景点"

        price_map = {
            "budget": ("经济型", "RMB 300-500"),
            "mid": ("中档舒适", "RMB 500-900"),
            "high": ("高端精选", "RMB 900+")
        }
        price_level, price_range = price_map.get(budget_level, price_map["mid"])

        templates = [
            {
                "name": f"{city}{primary_area}城市精选酒店",
                "area": primary_area,
                "brand": "城市精选",
                "price_level": price_level,
                "price_range": price_range,
                "score": 4.7,
                "reason": f"靠近{attraction_text}，适合以景点游览为主的行程。",
                "tags": ["景点近", "交通便利", "性价比高"]
            },
            {
                "name": f"{city}{primary_area}地铁口商务酒店",
                "area": primary_area,
                "brand": "便捷商务",
                "price_level": price_level,
                "price_range": price_range,
                "score": 4.5,
                "reason": "靠近地铁和核心商圈，适合每天换区域游玩。",
                "tags": ["地铁近", "商务", "出行方便"]
            },
            {
                "name": f"{city}慢享设计酒店",
                "area": target_areas[-1],
                "brand": "设计精品",
                "price_level": price_level,
                "price_range": price_range,
                "score": 4.6,
                "reason": "环境安静，适合希望住宿体验更舒适的游客。",
                "tags": ["安静", "设计感", "评价好"]
            }
        ]

        if "品牌稳定" in preferences or "评分优先" in preferences:
            templates[0]["score"] = 4.8
            templates[0]["tags"].append("评分优先")
        if "预算友好" in preferences:
            templates[1]["tags"].append("预算友好")
        if "靠近景点" in preferences:
            templates[0]["tags"].append("靠近景点")

        return templates

    def start(self):
        server_address = ('', self.port)
        hotel_mcp = self

        class HotelMcpHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    content_length = int(self.headers['Content-Length'])
                    raw_data = self.rfile.read(content_length)
                    data = json.loads(raw_data.decode('utf-8'))

                    hotel_mcp.log("RECEIVE", data)
                    response_body = hotel_mcp.handle_task(data)

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response_body, ensure_ascii=False).encode('utf-8'))

                    hotel_mcp.log("SEND", response_body)

                except Exception as e:
                    self.send_error(400, f"Bad Request: {str(e)}")

        httpd = HTTPServer(server_address, HotelMcpHandler)

        print(f"[OK] {self.name} 启动成功，作为独立酒店工具服务正在端口 {self.port} 待命...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[STOP] {self.name} 正在关闭...")
            httpd.server_close()

    def log(self, direction, message):
        print(f"\n{'=' * 20} [{self.name}] {'=' * 20}")
        print(f"方向: {direction}")
        print(f"内容: {json.dumps(message, indent=4, ensure_ascii=False)}")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    mcp = HotelMcp("hotel_mcp", 8003)
    mcp.start()
