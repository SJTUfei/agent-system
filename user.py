import uuid
import time
import requests

class UserClient:
    """
    UserClient 类用于模拟 Agent 系统中的用户客户端。
    
    主要职责：
    1. 接收用户输入的自然语言指令。
    2. 将指令按照规定的 JSON 格式封装为请求报文。
    3. 通过 HTTP 协议与 Coordinator 进行通信。
    4. 解析响应报文并将结果呈现给用户。
    """

    def __init__(self, server_url, client_port=9000):
        """
        初始化用户客户端。

        :param server_url: Coordinator 服务的访问地址 (例如 "http://localhost:8000")
        :param client_port: 用户客户端监听的回调端口，用于填充 callback_url
        """
        self.server_url = server_url
        self.callback_url = f"http://localhost:{client_port}"
        self.sender_name = "User"

    def _generate_trace_id(self):
        """
        生成唯一的追踪 ID，用于标识单次请求链路。
        
        :return: 字符串格式的唯一 ID
        """
        return f"trace_{uuid.uuid4().hex[:8]}"

    def pack_request(self, user_input):
        """
        将用户输入封装为符合项目规约的 JSON 报文。

        :param user_input: 用户在命令行输入的原始字符串
        :return: 字典格式的待发送报文
        """
        return {
            "header": {
                "trace_id": self._generate_trace_id(),
                "type": "instruction",
                "sender": self.sender_name,
                "callback_url": self.callback_url
            },
            "body": {
                "content": user_input
            }
        }

    def send_request(self, payload):
        """
        向 Coordinator 发送同步 POST 请求。

        :param payload: 封装好的 JSON 报文
        :return: 解析后的响应字典，若失败则返回 None
        """
        try:
            # 模拟真实发送过程
            response = requests.post(
                f"{self.server_url}/chat", 
                json=payload, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[Error] 无法连接到 Coordinator: {e}")
            return None

    def unpack_response(self, response_json):
        """
        解析 Coordinator 返回的报文，提取核心回答内容。

        :param response_json: Coordinator 返回的原始 JSON 字典
        :return: 提取出的回答文本内容
        """
        if not response_json:
            return "系统繁忙，未获取到有效回复。"
        
        # 按照约定格式提取 body 中的 content
        return response_json.get("body", {}).get("content", "解析失败：响应内容为空")

    def run(self):
        """
        启动客户端交互主循环。
        """
        print(f"=== Agent System 用户终端 已启动 ===")
        print(f"服务器地址: {self.server_url} | 回调地址: {self.callback_url}")
        
        while True:
            user_input = input("\n[用户]: ").strip()
            if user_input.lower() in ['exit', 'quit', '退出']:
                break
            if not user_input:
                continue

            # 1. 封装
            payload = self.pack_request(user_input)
            
            # 2. 发送并获取响应
            print(f"系统处理中 (trace_id: {payload['header']['trace_id']})...")
            raw_response = self.send_request(payload)
            
            # 3. 解析与展示
            answer = self.unpack_response(raw_response)
            print(f"[Agent]: {answer}")

if __name__ == "__main__":
    # 示例启动逻辑
    client = UserClient(server_url="http://localhost:8000")
    client.run()