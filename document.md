# Multi-Agent 系统项目开发文档

本项目实现了一个基于 **异步回调机制** 的轻量级多智能体协同系统。通过将复杂的任务逻辑（如天气查询、大模型推理）拆分到不同的 Agent 中，实现了任务的解耦与自动化调度[cite: 1, 2, 6]。

---

## 1. 整体架构与文件作用

项目采用中心化调度架构，由 `Coordinator` 负责路由分发，各功能 `Agent` 负责具体业务执行。

| 文件名 | 核心作用 | 技术选型 |
| :--- | :--- | :--- |
| **`BaseAgent.py`** | **抽象基类**：封装了所有 Agent 通用的网络监听、日志记录和消息发送逻辑。它是整个系统的通信基石。 | `http.server`, `requests` |
| **`coordinator.py`** | **任务调度员**：负责登记用户任务，利用 LLM 决定将任务分配给哪个子 Agent，并处理结果回传。 | `BaseAgent`, `llm_client` |
| **`user.py`** | **交互终端**：用户输入指令的入口，并在后台启动轻量级服务器接收异步结果回传[cite: 5]。 | `Flask`, `threading`, `socket` |
| **`weather_agent.py`** | **业务执行者**：负责参数提取（LLM）、工具调用（MCP）以及最终回答的拟人化包装[cite: 6]。 | `BaseAgent`, `llm_client` |
| **`weather_mcp.py`** | **工具服务端**：严格遵循 JSON-RPC 2.0 协议，模拟真实的天气数据库或 API 接口[cite: 7]。 | `JSON-RPC 2.0`, `http.server` |
| **`llm_client.py`** | **AI 适配器**：统一封装了大模型调用接口，支持 DeepSeek 等多种 API 以后端调用[cite: 3]。 | `openai SDK` |
| **`prompts.py`** | **提示词库**：集中管理路由决策、参数提取等所有环节的 System Prompt[cite: 4]。 | Python 字符串 |

---

## 2. 核心技术实现

### 2.1 服务器搭建技术
*   **低量级 Agent 服务 (`http.server`)**: 使用 Python 原生的 `HTTPServer` 搭建。它监听特定端口并重写 `do_POST` 方法，直接解析二进制字节流为 JSON 数据，适合作为轻量级智能体的节点[cite: 1, 7]。
*   **动态回调服务 (`Flask`)**: 在 `UserClient` 中集成 Flask。利用其路由装饰器（如 `@app.route('/callback')`）快速处理异步结果，并结合 `socket` 自动探测空闲端口，避免端口冲突[cite: 5]。

### 2.2 通信标准 (A2A 扁平化报文)
系统内部（Agent-to-Agent）采用统一的 **JSON 扁平化报文** 格式，确保跨节点通信的标准化[cite: 1, 2, 5, 6]：

```json
{
    "source": "发送方标识 (如 user, coordinator, weather_agent)",
    "target": "接收方标识",
    "task_id": "任务唯一标识 (用于异步追踪结果)",
    "instruction": "具体指令内容或执行结果",
    "callback_url": "后续结果回传的 HTTP 地址"
}