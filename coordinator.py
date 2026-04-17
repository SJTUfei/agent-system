from BaseAgent import BaseAgent
from llm_client import ask_llm
from prompts import ROUTING_PROMPT_TEMPLATE
import argparse

class Coordinator(BaseAgent):
    def __init__(self, name, port,api_key):
        super().__init__(name, port)
        # 记录待处理任务：{trace_id: user_callback_url}
        self.api_key = api_key
        self.pending_tasks = {}
        # 子 Agent 注册表
        self.agent_registry = {
            "weather_agent": 9010
        }

    def handle_task(self, data):
        header = data.get("header", {})
        msg_type = header.get("type")
        trace_id = header.get("trace_id")
        content = data.get("body", {}).get("content", "")

        if msg_type == "instruction":
            # 1. 记账：把用户的地址存起来
            user_url = header.get("callback_url")
            self.pending_tasks[trace_id] = user_url
            print(f"[*] 任务 {trace_id} 已登记，来源: {user_url}")
            
            # 2. 路由决策：问 LLM 这个任务该给哪个 Agent
            try:
                target_agent_name = self.call_llm_for_routing(content) 
            except ValueError as e:
                print(f"❌ 路由决策出错: {e}")
                return # 或者发回一个错误给用户

            target_port = self.agent_registry.get(target_agent_name)

            if target_port:
                # 3. 规范化并封装 Payload
                dispatch_payload = {
                    "header": {
                        "trace_id": trace_id,
                        "type": "instruction",
                        "sender": self.name,
                        "callback_url": f"http://localhost:{self.port}" 
                    },
                    "body": {
                        "content": content
                    }
                }

                # 4. 执行转发
                print(f"[*] 指挥官决策：任务 {trace_id} 转发至 {target_agent_name} (Port: {target_port})")
                self.send_to(target_port, dispatch_payload)
            else:
                print(f"⚠️ 决策失败：无法匹配到合适的 Agent。")

        elif msg_type == "answer":
            # 收到下级 Agent 办完事回来的结果
            print(f"[*] 收到来自 {header.get('sender')} 的执行结果，准备回传给用户...")
            self.finalize_response(data)

    def call_llm_for_routing(self, instruction):
        valid_agents = list(self.agent_registry.keys())
        agents_str = ", ".join(valid_agents)
        
        system_prompt = ROUTING_PROMPT_TEMPLATE.format(
            agent_list=agents_str,
            instruction=instruction
        )
        
        # 0.0 的 temperature 保证决策稳定性
        raw_result = ask_llm(system_prompt, "请输出匹配的 Agent 名称：", self.api_key, 0.0)
        result = raw_result.strip().lower()
        
        if result == "none":
            return "none"
        
        if result in valid_agents:
            return result
        
        raise ValueError(f"LLM 路由异常！非法返回值: '{raw_result}'")

    def finalize_response(self, data):
        trace_id = data.get("header", {}).get("trace_id")
        user_url = self.pending_tasks.get(trace_id)
        
        if user_url:
            final_payload = {
                "header": {
                    "trace_id": trace_id,
                    "type": "answer",
                    "sender": self.name
                },
                "body": {
                    "content": data.get("body", {}).get("content")
                }
            }
            # 任务完成，清理记录
            del self.pending_tasks[trace_id]
            
            # 使用统一的 send_to，确保日志被记录
            print(f"[*] 任务 {trace_id} 处理完毕，正在回传...")
            self.send_to(user_url, final_payload)
        else:
            print(f"⚠️ 收到孤儿答案 {trace_id}，找不到对应的用户信息。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行含有 API 调用的脚本")
    parser.add_argument(
        "--api_key", 
        "-k", 
        type=str, 
        required=True, 
        help="请在此输入您的 API Key"
    )
    args = parser.parse_args()
    api_key = args.api_key
    coord = Coordinator("Coordinator", 9000, api_key)
    coord.start()