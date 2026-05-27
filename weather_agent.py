from BaseAgent import BaseAgent
from llm_client import ask_llm
from prompts import WEATHER_EXTRACT_PROMPT, WEATHER_REPLY_PROMPT
import requests
import json
import argparse

class WeatherAgent(BaseAgent):
    def __init__(self, name, port, api_key, mcp_host):
        super().__init__(name, port)
        self.api_key = api_key
        # 允许自由指定 MCP 所在的局域网 IP 与端口
        self.mcp_host = mcp_host  
        
    def handle_task(self, data):
        task_id = data.get("task_id")
        instruction = data.get("instruction", "")
        callback_url = data.get("callback_url", "http://localhost:9000")
        
        self.log("AGENT_PROCESS", f"开始分析来自主控的任务 {task_id}: {instruction}")
        
        # ==========================================
        # Step 1: 提炼参数 (LLM)
        # ==========================================
        city = ask_llm(WEATHER_EXTRACT_PROMPT, instruction, self.api_key, temperature=0.0).strip()
        print(f"[*] LLM 参数提取结果: 城市 = {city}")
        
        if city == "未知" or city == "none":
            final_answer = "抱歉，我没有在您的话语中识别出需要查询天气的具体城市，请重新指定。"
        else:
            # ==========================================
            # Step 2: 组装 JSON-RPC 并同步请求 MCP Server
            # ==========================================
            rpc_request = {
                "jsonrpc": "2.0",
                "method": "get_weather",
                "params": {"city": city},
                "id": task_id
            }
            
            self.log("SEND (RPC -> MCP)", rpc_request)
            try:
                # 请求目标 MCP IP 端口
                mcp_target = f"http://{self.mcp_host}" if not self.mcp_host.startswith("http") else self.mcp_host
                response = requests.post(mcp_target, json=rpc_request, timeout=10)
                rpc_response = response.json()
                self.log("RECEIVE (MCP -> RPC)", rpc_response)
                
                # ==========================================
                # Step 3: 提取结果进行二次包装润色 (LLM)
                # ==========================================
                if "result" in rpc_response:
                    weather_data = rpc_response["result"]
                    llm_input = f"用户问题：{instruction}\n数据库返回数据：{json.dumps(weather_data, ensure_ascii=False)}"
                    final_answer = ask_llm(WEATHER_REPLY_PROMPT, llm_input, self.api_key, temperature=0.5)
                else:
                    error_msg = rpc_response.get("error", {}).get("message", "未知错误")
                    final_answer = f"抱歉，在查询天气工具时发生错误：{error_msg}"
                    
            except Exception as e:
                print(f"❌ 局域网请求 MCP 服务器 {self.mcp_host} 失败: {e}")
                final_answer = "抱歉，天气服务目前不可用，请稍后再试。"

        # ==========================================
        # Step 4: 组装 A2A 扁平格式，传回给指定的 Coordinator 局域网地址
        # ==========================================
        return_payload = {
            "source": self.name,
            "target": "coordinator",
            "task_id": task_id,
            "instruction": final_answer
        }
        
        print(f"[*] WeatherAgent 处理完毕，准备向远程主控回传结果...")
        # callback_url 是 Coordinator 的真实网络可达地址，直接利用 BaseAgent 的 send_to 即可
        self.send_to(callback_url, return_payload)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", "-k", type=str, required=True, help="API Key")
    parser.add_argument("--port", "-p", type=int, default=9010, help="本节点监听端口 (默认9010)")
    parser.add_argument("--mcp_host", "-m", type=str, default="localhost:8001", help="MCP 服务的局域网地址 (例如 192.168.1.102:8001)")
    args = parser.parse_args()
    
    agent = WeatherAgent("weather_agent", args.port, args.api_key, args.mcp_host)
    agent.start()