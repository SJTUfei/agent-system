from BaseAgent import BaseAgent, get_lan_ip
from llm_client import ask_llm
from prompts import ROUTING_PROMPT_TEMPLATE
import argparse

class Coordinator(BaseAgent):
    def __init__(self, name, port, api_key, weather_agent_host):
        super().__init__(name, port)
        self.api_key = api_key
        # 记录待处理任务：{task_id: user_callback_url}
        self.pending_tasks = {}
        
        # 局域网子 Agent 注册表，支持在命令行动态传入其他设备上的 Agent IP 及端口
        self.agent_registry = {
            "weather_agent": weather_agent_host  # 例如 "192.168.1.101:9010" 或 "localhost:9010"
        }

    def handle_task(self, data):
        source = data.get("source")
        task_id = data.get("task_id")
        instruction = data.get("instruction", "")

        # 判断是派发新任务，还是接收子 Agent 算好的结果
        if source == "user":
            user_url = data.get("callback_url")
            self.pending_tasks[task_id] = user_url
            print(f"[*] 新任务 {task_id} 已登记，客户端回调来源: {user_url}")
            
            try:
                target_agent_name = self.call_llm_for_routing(instruction) 
            except ValueError as e:
                print(f"❌ 路由决策出错: {e}")
                return 

            target_host = self.agent_registry.get(target_agent_name)

            if target_host:
                # 使用自身的局域网真实 IP 组合成 callback_url，让远程机器能准确找到我
                dispatch_payload = {
                    "source": self.name,
                    "target": target_agent_name,
                    "task_id": task_id,
                    "instruction": instruction,
                    "callback_url": f"http://{self.lan_ip}:{self.port}" 
                }

                print(f"[*] 指挥官决策：任务 {task_id} 转发至 {target_agent_name} ({target_host})")
                self.send_to(target_host, dispatch_payload)
            else:
                print(f"⚠️ 决策失败：路由指派了 '{target_agent_name}'，但注册表中未配置其 IP 终点。")

        elif source in self.agent_registry:
            print(f"[*] 收到子智能体 {source} 传回的执行结果，准备将其跨网络返还给用户客户端...")
            self.finalize_response(data)

    def call_llm_for_routing(self, instruction):
        valid_agents = list(self.agent_registry.keys())
        agents_str = ", ".join(valid_agents)
        
        system_prompt = ROUTING_PROMPT_TEMPLATE.format(
            agent_list=agents_str,
            instruction=instruction
        )
        
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
            # 清理内存中的任务追踪
            del self.pending_tasks[task_id]
            print(f"[*] 任务 {task_id} 处理完毕，开始向外网发起 HTTP POST 异步回调...")
            
            import requests
            try:
                # 此时的 user_url 是客户端所在的真实 IP，例如 http://192.168.1.102:53421/callback
                response = requests.post(user_url, json=final_payload, timeout=5)
                if response.status_code == 200:
                    print(f"✅ 最终旅游方案已成功送回用户端！")
            except Exception as e:
                print(f"❌ 异步回传给用户端 {user_url} 发生异常: {e}")
        else:
            print(f"⚠️ 收到孤儿答案 {task_id}，在 pending_tasks 中找不到对应的回调客户端。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coordinator 局域网启动脚本")
    parser.add_argument("--api_key", "-k", type=str, required=True, help="LLM API Key")
    parser.add_argument("--port", "-p", type=int, default=9000, help="本节点监听端口 (默认9000)")
    parser.add_argument("--weather_agent_host", "-w", type=str, default="localhost:9010", help="天气智能体的网络地址 (例如 192.168.1.101:9010)")
    args = parser.parse_args()
    
    coord = Coordinator("Coordinator", args.port, args.api_key, args.weather_agent_host)
    coord.start()