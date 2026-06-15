# hotel_agent.py
from BaseAgent import BaseAgent
from llm_client import ask_llm
from prompts import HOTEL_REPLY_PROMPT
import argparse
import json
import requests


class HotelAgent(BaseAgent):
    def __init__(self, name, port, api_key, mcp_host):
        super().__init__(name, port)
        self.api_key = api_key
        # 允许灵活配置独立的酒店 MCP 工具端点
        self.mcp_host = mcp_host

    def handle_task(self, data):
        task_id = data.get("task_id")
        instruction = data.get("instruction", "")
        callback_url = data.get("callback_url", "http://localhost:9000")
        context = data.get("context", {})

        self.log("AGENT_PROCESS", {
            "message": f"开始处理酒店推荐任务 {task_id}",
            "context_dependency": context.get("dependency")
        })

        tour_structured_data = context.get("tour_structured_data") or {}
        tour_result_text = context.get("tour_result_text", "")

        city = tour_structured_data.get("city") or self.extract_city_from_instruction(instruction)
        areas = self.extract_areas(tour_structured_data)
        attractions = [
            item.get("name")
            for item in tour_structured_data.get("attractions", [])
            if item.get("name")
        ]
        budget_level = self.extract_budget_level(instruction)
        preferences = self.extract_preferences(instruction)

        rpc_request = {
            "jsonrpc": "2.0",
            "method": "recommend_hotels",
            "params": {
                "city": city,
                "areas": areas,
                "budget_level": budget_level,
                "preferences": preferences,
                "attractions": attractions
            },
            "id": task_id
        }

        self.log("SEND (RPC -> MCP)", rpc_request)
        try:
            mcp_target = f"http://{self.mcp_host}" if not self.mcp_host.startswith("http") else self.mcp_host
            response = requests.post(mcp_target, json=rpc_request, timeout=10)
            rpc_response = response.json()
            self.log("RECEIVE (MCP -> RPC)", rpc_response)

            if "result" in rpc_response:
                hotel_data = rpc_response["result"]
                llm_input = (
                    f"用户原始需求：{instruction}\n"
                    f"上游行程规划结果：{tour_result_text}\n"
                    f"上游结构化行程数据：{json.dumps(tour_structured_data, ensure_ascii=False)}\n"
                    f"酒店 MCP 返回数据：{json.dumps(hotel_data, ensure_ascii=False)}"
                )
                final_answer = ask_llm(HOTEL_REPLY_PROMPT, llm_input, self.api_key, temperature=0.5)
                structured_data = {
                    "hotels": hotel_data,
                    "based_on": "tour_agent",
                    "city": city,
                    "areas": areas
                }
            else:
                error_msg = rpc_response.get("error", {}).get("message", "未知错误")
                final_answer = f"抱歉，在查询酒店工具时发生错误：{error_msg}"
                structured_data = {"hotels": [], "error": error_msg}

        except Exception as e:
            print(f"❌ 局域网请求 MCP 服务器 {self.mcp_host} 失败: {e}")
            final_answer = "抱歉，酒店数据服务目前不可用，请稍后再试。"
            structured_data = {"hotels": [], "error": str(e)}

        # ==========================================
        # Step 4: 返回平铺报文投递给远程的主控 Coordinator
        # ==========================================
        return_payload = {
            "source": self.name,
            "target": "coordinator",
            "task_id": task_id,
            "instruction": final_answer,
            "structured_data": structured_data
        }

        print(f"[*] HotelAgent 处理完毕，准备向远程主控回传结果...")
        self.send_to(callback_url, return_payload)

    def extract_areas(self, tour_structured_data):
        areas = []
        for day in tour_structured_data.get("itinerary", []):
            for area in day.get("areas", []):
                if area and area not in areas:
                    areas.append(area)
        return areas or ["市中心"]

    def extract_budget_level(self, instruction):
        if any(word in instruction for word in ["便宜", "经济", "预算", "省钱"]):
            return "budget"
        if any(word in instruction for word in ["高端", "豪华", "五星", "品质"]):
            return "high"
        return "mid"

    def extract_preferences(self, instruction):
        preferences = []
        keyword_map = {
            "交通": "交通便利", "地铁": "交通便利", "性价比": "预算友好",
            "便宜": "预算友好", "评分": "评分优先", "评价": "评分优先",
            "品牌": "品牌稳定", "景点": "靠近景点", "近": "靠近景点"
        }
        for keyword, preference in keyword_map.items():
            if keyword in instruction and preference not in preferences:
                preferences.append(preference)
        return preferences or ["交通便利", "靠近景点", "性价比高"]

    def extract_city_from_instruction(self, instruction):
        known_cities = ["上海", "北京", "广州", "深圳", "杭州", "南京", "成都", "重庆", "西安"]
        for city in known_cities:
            if city in instruction:
                return city
        return "未知"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HotelAgent 局域网启动脚本")
    parser.add_argument("--api_key", "-k", type=str, required=True, help="API Key")
    parser.add_argument("--port", "-p", type=int, default=9030, help="本节点监听端口 (默认9030)")
    parser.add_argument("--mcp_host", "-m", type=str, default="localhost:8003", help="酒店 MCP 的网络地址")
    args = parser.parse_args()

    agent = HotelAgent(name="hotel_agent", port=args.port, api_key=args.api_key, mcp_host=args.mcp_host)
    print(f"🚀 {agent.name} 正在启动服务...")
    agent.start()