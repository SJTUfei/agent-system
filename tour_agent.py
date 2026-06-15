# tour_agent.py
from BaseAgent import BaseAgent
from llm_client import ask_llm
from prompts import TOUR_EXTRACT_PROMPT, TOUR_REPLY_PROMPT
import requests
import json
import argparse
import re

class TourAgent(BaseAgent):
    def __init__(self, name, port, api_key, mcp_host):
        super().__init__(name, port)
        self.api_key = api_key
        # 动态指定或承接外部传入的 MCP 所在的局域网 IP 与端口（如 192.168.1.105:8002）
        self.mcp_host = mcp_host
        
    def handle_task(self, data):
        # 1. 接收主控发来的 A2A 扁平化报文
        task_id = data.get("task_id")
        instruction = data.get("instruction", "")
        callback_url = data.get("callback_url", "http://localhost:9000")
        
        self.log("AGENT_PROCESS", f"开始处理任务 {task_id}: {instruction}")
        
        # ==========================================
        # Step 1: 唤醒 LLM，从自然语言中提取工具参数
        # ==========================================
        city = ask_llm(TOUR_EXTRACT_PROMPT, instruction, self.api_key, temperature=0.0).strip()
        print(f"[*] LLM 参数提取结果: 城市 = {city}")
        
        structured_data = None
        if city == "未知" or city == "none":
            final_answer = "抱歉，我没有在您的话语中识别出需要查询景点的具体城市，请重新指定。"
        else:
            # ==========================================
            # Step 2: 构造 JSON-RPC 2.0 请求并调用 MCP
            # ==========================================
            rpc_request = {
                "jsonrpc": "2.0",
                "method": "get_attractions",
                "params": {"city": city},
                "id": task_id
            }
            
            self.log("SEND (RPC -> MCP)", rpc_request)
            try:
                # 兼容是否携带 http:// 前缀，动态拼接跨设备局域网目标终点
                mcp_target = f"http://{self.mcp_host}" if not self.mcp_host.startswith("http") else self.mcp_host
                response = requests.post(mcp_target, json=rpc_request, timeout=10)
                rpc_response = response.json()
                self.log("RECEIVE (MCP -> RPC)", rpc_response)
                
                # ==========================================
                # Step 3: 解析 MCP 结果，再次唤醒 LLM 进行拟人化包装
                # ==========================================
                if "result" in rpc_response:
                    attractions_data = rpc_response["result"]
                    llm_input = f"用户问题：{instruction}\n数据库返回数据：{json.dumps(attractions_data, ensure_ascii=False)}"
                    final_answer = ask_llm(TOUR_REPLY_PROMPT, llm_input, self.api_key, temperature=0.5)
                    # 兼容酒店 Agent：保留原 instruction 回复，同时额外附带结构化上下文。
                    structured_data = self.build_structured_data(city, instruction, attractions_data)
                else:
                    error_msg = rpc_response.get("error", {}).get("message", "未知错误")
                    final_answer = f"抱歉，在查询旅游工具时发生错误：{error_msg}"
                    
            except Exception as e:
                print(f"❌ 局域网请求 MCP 服务器 {self.mcp_host} 失败: {e}")
                final_answer = "抱歉，旅游数据服务目前不可用，请稍后再试。"

        # ==========================================
        # Step 4: 组装扁平化报文回传给主控
        # ==========================================
        return_payload = {
            "source": self.name,
            "target": "coordinator",
            "task_id": task_id,
            "instruction": final_answer
        }
        if structured_data:
            return_payload["structured_data"] = structured_data
            
        print(f"[*] TourAgent 处理完毕，准备向远程主控回传结果...")
        self.send_to(callback_url, return_payload)

    def build_structured_data(self, city, instruction, attractions_data):
        days = self.extract_days(instruction) or 1
        areas = list(set([item.get("area") for item in attractions_data if item.get("area")]))
        
        itinerary = []
        if days > 1 and areas:
            for index in range(days):
                day_areas = areas[index::days] or areas[:1]
                itinerary.append({
                    "day": index + 1,
                    "areas": day_areas,
                    "summary": f"第 {index + 1} 天建议围绕 {', '.join(day_areas)} 安排行程。"
                })
        elif areas:
            itinerary.append({
                "day": 1,
                "areas": areas,
                "summary": f"建议优先围绕 {', '.join(areas)} 安排行程和住宿。"
            })

        return {
            "city": city,
            "days": days,
            "areas": areas,
            "attractions": attractions_data,
            "itinerary": itinerary
        }

    def extract_days(self, instruction):
        digit_match = re.search(r"(\d+)\s*[天日]", instruction)
        if digit_match:
            return int(digit_match.group(1))

        chinese_days = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
        for text, value in chinese_days.items():
            if f"{text}日" in instruction or f"{text}天" in instruction:
                return value
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TourAgent 局域网启动脚本")
    parser.add_argument("--api_key", "-k", type=str, required=True, help="API Key")
    parser.add_argument("--port", "-p", type=int, default=9020, help="本节点监听端口 (默认9020)")
    parser.add_argument("--mcp_host", "-m", type=str, default="localhost:8002", help="旅游 MCP 的网络地址")
    args = parser.parse_args()
    
    # 实例化并启动监听服务
    agent = TourAgent(name="tour_agent", port=args.port, api_key=args.api_key, mcp_host=args.mcp_host)
    print(f"🚀 {agent.name} 正在启动服务...")
    agent.start()