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
        # 【修改点】：直接解析扁平化字段
        source = data.get("source")
        task_id = data.get("task_id")
        instruction = data.get("instruction", "")

        # 判断是派发新任务，还是接收结果
        if source == "user":
            user_url = data.get("callback_url")
            self.pending_tasks[task_id] = user_url
            print(f"[*] 任务 {task_id} 已登记，来源: {user_url}")
            
            try:
                target_agent_name = self.call_llm_for_routing(instruction) 
            except ValueError as e:
                print(f"❌ 路由决策出错: {e}")
                return 

            target_port = self.agent_registry.get(target_agent_name)

            if target_port:
                # 【修改点】：使用扁平化的 A2A 格式转发给下级 Agent
                dispatch_payload = {
                    "source": self.name,
                    "target": target_agent_name,
                    "task_id": task_id,
                    "instruction": instruction,
                    "callback_url": f"http://localhost:{self.port}" 
                }

                print(f"[*] 指挥官决策：任务 {task_id} 转发至 {target_agent_name} (Port: {target_port})")
                self.send_to(target_port, dispatch_payload)
            else:
                print(f"⚠️ 决策失败：无法匹配到合适的 Agent。")

        elif source in self.agent_registry:
            print(f"[*] 收到来自 {source} 的执行结果，准备回传给用户...")
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
        task_id = data.get("task_id")
        user_url = self.pending_tasks.get(task_id)
        
        if user_url:
            final_payload = {
                "source": self.name,
                "target": "user",
                "task_id": task_id,
                "instruction": data.get("instruction")
            }
            del self.pending_tasks[task_id]
            print(f"[*] 任务 {task_id} 处理完毕，正在回传...")
            
            # 由于 UserClient 目前是用 Flask @app.route('/callback')，所以要确保提取正确的端口后补全 /callback
            # 但我们在 user.py 里传过来的 callback_url 已经是完整的了
            import requests
            try:
                requests.post(user_url, json=final_payload, timeout=5)
            except Exception as e:
                print(f"❌ 回传给用户失败: {e}")
        else:
            print(f"⚠️ 收到孤儿答案 {task_id}，找不到对应的用户信息。")

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