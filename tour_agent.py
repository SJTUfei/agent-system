# tour_agent.py
from BaseAgent import BaseAgent
from llm_client import ask_llm
from prompts import TOUR_EXTRACT_PROMPT, TOUR_REPLY_PROMPT
import requests
import json
import argparse

class TourAgent(BaseAgent):
    def __init__(self, name, port, api_key):
        super().__init__(name, port)
        self.api_key = api_key
        # 写死 MCP Server 的目标端口（按照要求如 8002）
        self.mcp_port = 8002
        
    def handle_task(self, data):
        # 1. 接收主控发来的 A2A 扁平化报文
        task_id = data.get("task_id")
        instruction = data.get("instruction", "")
        # 获取回调地址的端口（假设 coordinator 传来了 callback_url 或者我们知道它是 9000）
        callback_url = data.get("callback_url", "http://localhost:9000")
        
        self.log("AGENT_PROCESS", f"开始处理任务 {task_id}: {instruction}")
        
        # ==========================================
        # Step 1: 唤醒 LLM，从自然语言中提取工具参数
        # ==========================================
        city = ask_llm(TOUR_EXTRACT_PROMPT, instruction, self.api_key, temperature=0.0).strip()
        print(f"[*] LLM 参数提取结果: 城市 = {city}")
        
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
                # 同步调用 MCP Server，必须在线等待结果
                response = requests.post(f"http://localhost:{self.mcp_port}", json=rpc_request, timeout=10)
                rpc_response = response.json()
                self.log("RECEIVE (MCP -> RPC)", rpc_response)
                
                # ==========================================
                # Step 3: 解析 MCP 结果，再次唤醒 LLM 进行拟人化包装
                # ==========================================
                if "result" in rpc_response:
                    attractions_data = rpc_response["result"]
                    # 将景点数据喂给大模型
                    llm_input = f"用户问题：{instruction}\n数据库返回数据：{json.dumps(attractions_data, ensure_ascii=False)}"
                    final_answer = ask_llm(TOUR_REPLY_PROMPT, llm_input, self.api_key, temperature=0.5)
                else:
                    error_msg = rpc_response.get("error", {}).get("message", "未知错误")
                    final_answer = f"抱歉，在查询景点工具时发生错误：{error_msg}"
                    
            except Exception as e:
                print(f"❌ 请求 MCP 服务器失败: {e}")
                final_answer = "抱歉，景点服务目前不可用，请稍后再试。"

        # ==========================================
        # Step 4: 组装 A2A 扁平格式，传回给 Coordinator
        # ==========================================
        return_payload = {
            "source": self.name,
            "target": "coordinator",
            "task_id": task_id,
            "instruction": final_answer
        }
        
        print(f"[*] TourAgent 处理完毕，准备回传至 Coordinator...")
        # 提取目标端口并使用 BaseAgent 原生的 send_to 发送
        coord_port = int(callback_url.split(":")[-1].replace("/", ""))
        self.send_to(coord_port, return_payload)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", "-k", type=str, required=True, help="API Key")
    args = parser.parse_args()
    
    # 监听 9020 端口
    agent = TourAgent("tour_agent", 9020, args.api_key)
    agent.start()