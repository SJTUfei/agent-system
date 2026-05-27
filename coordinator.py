from BaseAgent import BaseAgent
from llm_client import ask_llm
from prompts import ROUTING_PROMPT_TEMPLATE
import argparse
import requests

class Coordinator(BaseAgent):
    def __init__(self, name, port,api_key):
        super().__init__(name, port)
        # 记录待处理任务：{trace_id: user_callback_url}
        self.api_key = api_key
        self.pending_tasks = {}
        # 串行任务状态：用于记录 tour_agent -> hotel_agent 的网络依赖
        self.pipeline_tasks = {}
        # 子 Agent 注册表
        self.agent_registry = {
            "weather_agent": 9010,
            "tour_agent": 9020,
            "hotel_agent": 9030
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

            # 新增：如果用户同时提出行程/景点 + 酒店需求，启动串行网络流程
            if self.should_run_tour_then_hotel(instruction):
                print(f"[*] 任务 {task_id} 命中旅行 + 酒店复合请求，先派发给 tour_agent")
                self.pipeline_tasks[task_id] = {
                    "user_url": user_url,
                    "original_instruction": instruction,
                    "stage": "waiting_tour",
                    "tour_result": None,
                    "hotel_result": None
                }
                self.dispatch_to_agent(task_id, "tour_agent", instruction)
                return
            
            try:
                target_agent_name = self.call_llm_for_routing(instruction) 
            except ValueError as e:
                print(f"路由决策出错: {e}")
                self.reply_unsupported_task(task_id, user_url, instruction)
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
                print("[!] 决策失败：无法匹配到合适的 Agent。")
                self.reply_unsupported_task(task_id, user_url, instruction)

        elif source in self.agent_registry:
            if task_id in self.pipeline_tasks:
                self.handle_pipeline_result(data)
            else:
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
            if "structured_data" in data:
                final_payload["structured_data"] = data.get("structured_data")

            del self.pending_tasks[task_id]
            print(f"[*] 任务 {task_id} 处理完毕，正在回传...")
            
            # 由于 UserClient 目前是用 Flask @app.route('/callback')，所以要确保提取正确的端口后补全 /callback
            # 但我们在 user.py 里传过来的 callback_url 已经是完整的了
            try:
                requests.post(user_url, json=final_payload, timeout=5)
            except Exception as e:
                print(f"回传给用户失败: {e}")
        else:
            print(f"[!] 收到孤儿答案 {task_id}，找不到对应的用户信息。")

    def should_run_tour_then_hotel(self, instruction):
        tour_keywords = ["景点", "行程", "旅游", "旅行", "游玩", "路线", "几日游", "一日游", "两日游", "三日游"]
        hotel_keywords = ["酒店", "住宿", "住哪", "住哪里", "宾馆", "民宿", "订房"]
        has_tour_intent = any(keyword in instruction for keyword in tour_keywords)
        has_hotel_intent = any(keyword in instruction for keyword in hotel_keywords)
        return has_tour_intent and has_hotel_intent

    def dispatch_to_agent(self, task_id, target_agent_name, instruction, context=None):
        target_port = self.agent_registry.get(target_agent_name)
        if not target_port:
            print(f"[!] 决策失败：无法匹配到合适的 Agent: {target_agent_name}")
            return

        dispatch_payload = {
            "source": self.name,
            "target": target_agent_name,
            "task_id": task_id,
            "instruction": instruction,
            "callback_url": f"http://localhost:{self.port}"
        }
        if context is not None:
            dispatch_payload["context"] = context

        print(f"[*] Coordinator 派发任务 {task_id} -> {target_agent_name} (Port: {target_port})")
        self.send_to(target_port, dispatch_payload)

    def handle_pipeline_result(self, data):
        task_id = data.get("task_id")
        source = data.get("source")
        pipeline = self.pipeline_tasks[task_id]

        if source == "tour_agent" and pipeline["stage"] == "waiting_tour":
            print(f"[*] 任务 {task_id}: 已收到 tour_agent 网络回调，依赖条件满足")
            pipeline["tour_result"] = data
            pipeline["stage"] = "waiting_hotel"

            context = {
                "dependency": "tour_agent",
                "tour_result_text": data.get("instruction", ""),
                "tour_structured_data": data.get("structured_data", {})
            }
            print(f"[*] 任务 {task_id}: 正在通过网络唤醒 hotel_agent")
            self.dispatch_to_agent(
                task_id,
                "hotel_agent",
                pipeline["original_instruction"],
                context=context
            )
            return

        if source == "hotel_agent" and pipeline["stage"] == "waiting_hotel":
            print(f"[*] 任务 {task_id}: 已收到 hotel_agent 网络回调，准备汇总最终结果")
            pipeline["hotel_result"] = data
            self.finalize_pipeline_response(task_id)
            return

        print(f"[!] 任务 {task_id}: 收到不符合当前阶段的回调 source={source}, stage={pipeline['stage']}")

    def finalize_pipeline_response(self, task_id):
        pipeline = self.pipeline_tasks.get(task_id)
        if not pipeline:
            print(f"[!] 找不到串行任务状态: {task_id}")
            return

        tour_text = pipeline["tour_result"].get("instruction", "") if pipeline["tour_result"] else ""
        hotel_text = pipeline["hotel_result"].get("instruction", "") if pipeline["hotel_result"] else ""
        final_answer = (
            "【行程规划】\n"
            f"{tour_text}\n\n"
            "【酒店推荐】\n"
            f"{hotel_text}"
        )

        final_payload = {
            "source": self.name,
            "target": "user",
            "task_id": task_id,
            "instruction": final_answer,
            "structured_data": {
                "tour": pipeline["tour_result"].get("structured_data", {}) if pipeline["tour_result"] else {},
                "hotel": pipeline["hotel_result"].get("structured_data", {}) if pipeline["hotel_result"] else {}
            }
        }

        user_url = pipeline["user_url"]
        del self.pipeline_tasks[task_id]
        if task_id in self.pending_tasks:
            del self.pending_tasks[task_id]

        print(f"[*] 串行任务 {task_id} 已完成，正在回传给用户...")
        try:
            requests.post(user_url, json=final_payload, timeout=5)
        except Exception as e:
            print(f"回传给用户失败: {e}")

    def reply_unsupported_task(self, task_id, user_url, instruction):
        final_payload = {
            "source": self.name,
            "target": "user",
            "task_id": task_id,
            "instruction": (
                "当前系统主要支持旅行相关任务，例如天气查询、景点推荐、行程规划、酒店/住宿推荐。"
                f"\n您刚才的问题是：{instruction}\n"
                "可以换成类似“帮我规划上海两日游并推荐酒店”的问题来体验多 Agent 协同链路。"
            )
        }

        if task_id in self.pending_tasks:
            del self.pending_tasks[task_id]

        print(f"[*] 任务 {task_id} 不属于当前 Agent 能力范围，已回传提示给用户。")
        try:
            requests.post(user_url, json=final_payload, timeout=5)
        except Exception as e:
            print(f"回传给用户失败: {e}")

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
