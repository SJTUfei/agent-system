# 酒店 Agent 扩展实现日志与汇报说明

## 1. 本次实现目标

本次修改围绕课程“基于 MCP 与 A2A 协议的分布式多智能体协同网络”要求展开，重点不是让单个 Agent 更聪明，而是让多个独立进程通过网络协议完成协作。

核心目标：

- 新增 `hotel_agent`，作为旅行社系统中的酒店/住宿推荐 Agent。
- 新增 `hotel_mcp`，作为 `hotel_agent` 独立调用的 MCP 工具服务器。
- 让 `hotel_agent` 与现有 `tour_agent` 产生串行网络依赖：

```text
User
  -> Coordinator
  -> tour_agent
  -> tour_mcp
  -> tour_agent
  -> Coordinator
  -> hotel_agent
  -> hotel_mcp
  -> hotel_agent
  -> Coordinator
  -> User
```

其中，`hotel_agent` 不直接调用 `tour_agent` 的函数，也不读取 `tour_agent` 的内存数据。它必须等待 `Coordinator` 通过 HTTP 收到 `tour_agent` 的网络回调后，再由 `Coordinator` 通过 HTTP 派发任务。

本轮暂不接入天气链路，也暂不做分布式容错。天气 Agent 仍作为原有能力保留，只有用户明确问天气且启动了天气组件时才使用。

## 2. 网络拓扑与端口

本次默认演示链路需要这些独立进程：

| 组件 | 文件 | 端口 | 角色 |
| --- | --- | ---: | --- |
| Coordinator | `coordinator.py` | `9000` | 主控 Agent，负责路由、串行状态管理、结果汇总 |
| TourAgent | `tour_agent.py` | `9020` | 景点/行程 Agent |
| TourMCP | `tour_mcp.py` | `8002` | 景点 MCP Server，提供 JSON-RPC 工具 |
| HotelAgent | `hotel_agent.py` | `9030` | 新增酒店 Agent |
| HotelMCP | `hotel_mcp.py` | `8003` | 新增酒店 MCP Server |
| UserClient | `user.py` | 动态端口 | 用户端，接收异步回调 |

默认不启动：

| 组件 | 文件 | 端口 | 说明 |
| --- | --- | ---: | --- |
| WeatherAgent | `weather_agent.py` | `9010` | 原有天气 Agent，可选启动 |
| WeatherMCP | `weather_mcp.py` | `8001` | 原有天气 MCP，可选启动 |

## 3. A2A 与 MCP 协议关系

### A2A: Agent-to-Agent HTTP 通信

Agent 之间使用 HTTP POST 传递扁平 JSON 报文。典型结构：

```json
{
  "source": "coordinator",
  "target": "tour_agent",
  "task_id": "1001",
  "instruction": "帮我规划上海两日游，并推荐酒店",
  "callback_url": "http://localhost:9000"
}
```

在串行链路中，`Coordinator` 派发给 `hotel_agent` 时会额外带上 `context`：

```json
{
  "source": "Coordinator",
  "target": "hotel_agent",
  "task_id": "1001",
  "instruction": "帮我规划上海两日游，并推荐酒店",
  "callback_url": "http://localhost:9000",
  "context": {
    "dependency": "tour_agent",
    "tour_result_text": "tour_agent 的自然语言结果",
    "tour_structured_data": {
      "city": "上海",
      "areas": ["黄浦区", "人民广场"],
      "attractions": []
    }
  }
}
```

### MCP: HTTP/JSON-RPC 工具调用

Agent 不直接执行工具逻辑，而是通过 HTTP POST 调用 MCP Server。典型 JSON-RPC 请求：

```json
{
  "jsonrpc": "2.0",
  "method": "recommend_hotels",
  "params": {
    "city": "上海",
    "areas": ["黄浦区", "人民广场"],
    "budget_level": "mid",
    "preferences": ["交通便利", "靠近景点"],
    "attractions": ["外滩", "上海博物馆"]
  },
  "id": "1001"
}
```

典型 JSON-RPC 响应：

```json
{
  "jsonrpc": "2.0",
  "result": [
    {
      "name": "上海黄浦区城市精选酒店",
      "area": "黄浦区",
      "brand": "城市精选",
      "price_level": "中档舒适",
      "price_range": "RMB 500-900",
      "score": 4.7,
      "reason": "靠近外滩、上海博物馆，适合以景点游览为主的行程。",
      "tags": ["景点近", "交通便利", "性价比高"]
    }
  ],
  "id": "1001"
}
```

## 4. 修改文件总览

| 文件 | 修改类型 | 主要内容 |
| --- | --- | --- |
| `plan.md` | 新增/更新 | 记录总体设计方案、接口约定、端口规划 |
| `implementation_log.md` | 新增/重写 | 记录实现过程和汇报说明 |
| `tour_mcp.py` | 轻量增强 | 保留同学原 MCP 逻辑，只把景点 mock 数据补充为结构化数据 |
| `tour_agent.py` | 轻量增强 | 保留同学原 Agent 流程，只额外回传 `structured_data` |
| `hotel_mcp.py` | 新增 | 新酒店 MCP Server，监听 `8003` |
| `hotel_agent.py` | 新增 | 新酒店 Agent，监听 `9030` |
| `coordinator.py` | 重写增强 | 新增 `tour -> hotel` 串行状态机 |
| `prompts.py` | 重写整理 | 清理乱码，新增酒店 Prompt 和路由说明 |
| `main.py` | 重写 | 一键启动多个独立进程 |

### 4.1 改动规模统计

以下统计来自 `git diff --numstat` 和新文件行数统计，方便说明哪些文件是轻量增强，哪些文件是本次新增工作。

原有文件改动：

| 文件 | 新增行 | 删除行 | 说明 |
| --- | ---: | ---: | --- |
| `tour_agent.py` | 60 | 1 | 同学模块，轻量增强：只增加 `structured_data` 回传和两个辅助函数 |
| `tour_mcp.py` | 29 | 6 | 同学模块，轻量增强：只把原 mock 景点数据扩展为带区域字段 |
| `coordinator.py` | 149 | 9 | 主控模块，尽量保留原结构，只新增串行状态机、酒店 Agent 注册、无关问题回传 |
| `prompts.py` | 43 | 16 | Prompt 整理，新增酒店回复 Prompt 和路由说明 |
| `main.py` | 150 | 0 | 原文件为空，本次实现一键启动器 |

新增文件：

| 文件 | 行数 | 说明 |
| --- | ---: | --- |
| `hotel_agent.py` | 152 | 本次负责的新酒店 Agent |
| `hotel_mcp.py` | 141 | 本次负责的新酒店 MCP Server |
| `plan.md` | 305 | 前期设计方案和接口约定 |
| `implementation_log.md` | 510 | 实现过程、网络交互和汇报说明 |

关于同学负责的 `tour_agent.py` / `tour_mcp.py`：

- 这两个文件没有改端口、类名、主流程和协议方法。
- `tour_agent.py` 的原有流程仍然是：接收任务 -> LLM 提取城市 -> 调 MCP -> LLM 包装回复 -> 回传 Coordinator。
- `tour_mcp.py` 的原有流程仍然是：接收 JSON-RPC -> 校验 -> 处理 `get_attractions` -> 返回 JSON-RPC。
- 本次只为酒店 Agent 增加稳定可读的上游上下文，避免酒店 Agent 从自然语言里硬解析景点区域。

## 5. `tour_mcp.py` 修改说明

### 同学模块保护原则

`tour_agent.py` 和 `tour_mcp.py` 属于同学负责的景点模块。本次后续调整已按最小侵入原则处理：

- 不改变原有端口。
- 不改变原有类名。
- 不改变原有 JSON-RPC 方法名。
- 不改变原有 Agent 主流程。
- 不让 `tour_agent` 直接调用 `hotel_agent`。
- 只增加酒店链路需要的结构化数据。

### 修改前

原来的 `tour_mcp.py` 已经是独立 MCP Server，监听 `8002`，支持 JSON-RPC 方法 `get_attractions`。但是 mock 数据比较简单：

```json
[
  {"name": "景点1", "description": "描述1"},
  {"name": "景点2", "description": "描述2"}
]
```

这种数据可以给用户看，但不方便酒店 Agent 判断住宿区域。

### 修改后

这部分已按“最小改动”处理：保留同学原来的 `handle_task()`、`start()`、`log()`、端口、JSON-RPC 方法名，只替换原来 `mock_result` 的数据来源。

保留原有网络协议和方法名：

- 仍然使用 `http.server`。
- 仍然监听 `8002`。
- 仍然支持 JSON-RPC 2.0。
- 仍然使用 `method = get_attractions`。

新增 `get_mock_attractions(city)` 方法，返回更结构化的景点数据：

```json
{
  "name": "外滩",
  "description": "上海经典城市天际线观景地，适合安排夜景行程。",
  "area": "黄浦区",
  "suggested_time": "晚上",
  "tags": ["夜景", "地标", "步行友好"]
}
```

这些字段的作用：

- `area`：给酒店 Agent 判断住在哪个区域。
- `suggested_time`：给行程规划说明早晚安排。
- `tags`：给推荐理由提供依据。

网络意义：

`tour_mcp.py` 仍然是独立工具服务器，`tour_agent.py` 必须通过 HTTP/JSON-RPC 获取数据，符合“Agent 不直接执行工具代码”的 MCP 思想。

### 函数级改动

修改的已有函数：

- `handle_task(self, data)`
  - 保留原来的 JSON-RPC 校验逻辑。
  - 保留原来的 `method == "get_attractions"` 分支。
  - 修改原来写死的 `mock_result = [...]`，改为 `mock_result = self.get_mock_attractions(city)`。
  - 功能变化：MCP 返回的景点数据从简单名称/描述，升级为带区域、推荐时间、标签的结构化数据。

新增函数：

- `get_mock_attractions(self, city)`
  - 根据城市返回模拟景点数据。
  - 为上海、北京、广州提供更具体的 mock 数据。
  - 对其他城市返回通用 mock 数据。
  - 关键新增字段：`area`、`suggested_time`、`tags`。

未修改的已有函数：

- `start(self)`
  - 仍然使用 `HTTPServer` 监听端口。
  - 仍然在 `do_POST` 中读取 JSON 请求、调用 `handle_task()`、返回 JSON 响应。

- `log(self, direction, message)`
  - 保持原来的网络日志打印格式。

## 6. `tour_agent.py` 修改说明

### 修改前

原来的 `tour_agent.py` 已经能：

1. 接收 Coordinator 的 A2A HTTP 请求。
2. 调用 LLM 提取城市。
3. 通过 JSON-RPC 调用 `tour_mcp.py`。
4. 用 LLM 包装自然语言回复。
5. 回传 Coordinator。

但它只回传：

```json
{
  "source": "tour_agent",
  "target": "coordinator",
  "task_id": "1001",
  "instruction": "自然语言回复"
}
```

酒店 Agent 如果只拿自然语言，就很难稳定提取区域和景点。

### 修改后

这部分也按“最小改动”处理：保留同学原来的接收任务、LLM 提取城市、调用 MCP、LLM 包装回复、回传 Coordinator 的流程，只在拿到 `attractions_data` 后补一份结构化上下文。

保留原有自然语言 `instruction`，并额外加入 `structured_data`：

```json
{
  "source": "tour_agent",
  "target": "coordinator",
  "task_id": "1001",
  "instruction": "自然语言行程规划结果",
  "structured_data": {
    "city": "上海",
    "days": 2,
    "areas": ["黄浦区", "人民广场"],
    "attractions": [],
    "itinerary": []
  }
}
```

新增关键方法：

- `build_structured_data(city, instruction, attractions)`
  - 从 MCP 返回景点中提取区域。
  - 识别用户输入中的天数。
  - 生成简单的 `itinerary`，供下游酒店 Agent 使用。

- `extract_days(instruction)`
  - 支持数字天数：`2天`、`3日`。
  - 支持中文天数：`两日`、`三天`。

网络意义：

`tour_agent` 仍然只是通过网络回传结果。它没有直接调用 `hotel_agent`，所以串行依赖由 Coordinator 控制，网络拓扑更清晰。

### 函数级改动

修改的已有函数：

- `handle_task(self, data)`
  - 保留原来的 A2A 接收逻辑。
  - 保留原来的 LLM 城市提取逻辑。
  - 保留原来的 JSON-RPC 调用 `tour_mcp` 逻辑。
  - 保留原来的 LLM 自然语言包装逻辑。
  - 新增局部变量 `structured_data = None`。
  - 在 MCP 成功返回 `result` 后，新增：
    - `structured_data = self.build_structured_data(city, instruction, attractions_data)`
  - 在原 `return_payload` 中额外加入：
    - `return_payload["structured_data"] = structured_data`
  - 功能变化：既保持同学原来的自然语言回复，又给 Coordinator/HotelAgent 提供结构化上下文。

新增函数：

- `build_structured_data(self, city, instruction, attractions_data)`
  - 从 MCP 景点数据中提取所有 `area`。
  - 调用 `extract_days()` 识别用户需求中的旅行天数。
  - 生成 `itinerary` 简单行程结构。
  - 返回给下游的字段包括：`city`、`days`、`areas`、`attractions`、`itinerary`。

- `extract_days(self, instruction)`
  - 支持识别 `2天`、`3日` 这种数字表达。
  - 支持识别 `两日`、`三天` 这种中文表达。
  - 没有识别到天数时返回 `None`。

未修改的已有结构：

- `TourAgent.__init__()`
  - 仍然监听 `9020`。
  - 仍然调用 `tour_mcp` 的 `8002` 端口。

- `if __name__ == "__main__"`
  - 仍然通过 `--api_key` 启动。
  - 仍然创建 `TourAgent("tour_agent", 9020, args.api_key)`。

## 7. `hotel_mcp.py` 新增说明

`hotel_mcp.py` 是本次新增的独立 MCP Server。

### 启动信息

- 文件：`hotel_mcp.py`
- 端口：`8003`
- 协议：HTTP POST + JSON-RPC 2.0
- 方法：`recommend_hotels`

### 请求参数

```json
{
  "city": "上海",
  "areas": ["黄浦区", "人民广场"],
  "budget_level": "mid",
  "preferences": ["交通便利", "靠近景点"],
  "attractions": ["外滩", "上海博物馆"]
}
```

### 返回数据

返回模拟酒店列表，每个酒店包含：

- `name`：酒店名称
- `area`：推荐住宿区域
- `brand`：品牌或类型
- `price_level`：价格等级
- `price_range`：价格范围
- `score`：评分
- `reason`：推荐原因
- `tags`：标签

### 网络意义

`hotel_agent` 不在本地直接生成酒店列表，而是通过 HTTP/JSON-RPC 调用 `hotel_mcp`。这体现了 MCP 工具服务器的独立性，也满足“新增 Agent 配备独立 MCP Server”的要求。

### 函数级说明

新增类：

- `HotelMcp`
  - 新增酒店 MCP Server 类。
  - 负责监听 HTTP 请求、解析 JSON-RPC、返回酒店工具结果。

新增函数：

- `__init__(self, name, port)`
  - 保存 MCP 名称和监听端口。

- `handle_task(self, data)`
  - 校验 JSON-RPC 2.0 请求格式。
  - 识别 `method == "recommend_hotels"`。
  - 从 `params` 中读取：
    - `city`
    - `areas`
    - `budget_level`
    - `preferences`
    - `attractions`
  - 调用 `recommend_hotels()` 生成模拟酒店数据。
  - 如果方法不存在，返回 JSON-RPC 标准错误 `-32601`。

- `recommend_hotels(self, city, areas, budget_level, preferences, attractions)`
  - 根据上游景点区域选择酒店位置。
  - 根据预算等级生成价格范围。
  - 根据偏好标签调整推荐理由和标签。
  - 返回酒店列表，每个酒店包含名称、区域、品牌、价格、评分、推荐原因。

- `start(self)`
  - 使用 `HTTPServer` 监听 `8003`。
  - 在 `do_POST` 中读取 JSON-RPC 请求并同步返回 JSON-RPC 响应。

- `log(self, direction, message)`
  - 打印 MCP 收发方向和 JSON Payload，便于展示网络交互。

## 8. `hotel_agent.py` 新增说明

`hotel_agent.py` 是本次新增的工作 Agent。

### 启动信息

- 文件：`hotel_agent.py`
- 端口：`9030`
- 上游依赖：`tour_agent` 的回调结果
- 工具依赖：`hotel_mcp:8003`

### 处理流程

1. 接收 Coordinator 的 A2A 请求。
2. 从 `context.tour_structured_data` 中读取：
   - 城市
   - 景点区域
   - 景点名称
   - 行程摘要
3. 从用户原始 `instruction` 中提取：
   - 预算等级：`budget` / `mid` / `high`
   - 偏好：交通便利、预算友好、评分优先、靠近景点等
4. 构造 JSON-RPC 请求，调用 `hotel_mcp`。
5. 调用 LLM，将酒店 MCP 返回的结构化数据包装成自然语言推荐。
6. 回传 Coordinator。

### 关键方法

- `extract_areas(tour_structured_data)`
  - 从上游 `areas`、`attractions[].area`、`itinerary[].areas` 合并区域。

- `extract_budget_level(instruction)`
  - 根据“便宜、经济、预算、省钱”判断为 `budget`。
  - 根据“高端、豪华、五星、品质”判断为 `high`。
  - 默认 `mid`。

- `extract_preferences(instruction)`
  - 从用户输入中识别交通、地铁、性价比、评分、品牌、景点等偏好。

### 网络意义

`hotel_agent` 的执行条件来自 Coordinator 的第二次网络派发，而不是本地函数调用。这是本次作业中最关键的串行依赖点：

```text
Coordinator 收到 tour_agent 网络结果
  -> 构造 context
  -> HTTP POST 唤醒 hotel_agent
```

### 函数级说明

新增类：

- `HotelAgent(BaseAgent)`
  - 新增酒店工作 Agent。
  - 继承 `BaseAgent`，因此具备 HTTP 监听、A2A 接收、A2A 发送和日志能力。

新增函数：

- `__init__(self, name, port, api_key)`
  - 保存 API key。
  - 设置 `self.mcp_port = 8003`，表示酒店 Agent 的工具服务器是 `hotel_mcp`。

- `handle_task(self, data)`
  - 接收 Coordinator 派发的 A2A 任务。
  - 读取 `instruction` 和 `context`。
  - 从 `context.tour_structured_data` 中提取城市、区域、景点。
  - 从用户原始输入中提取预算和偏好。
  - 构造 JSON-RPC 请求：
    - `method = "recommend_hotels"`
    - `params = city / areas / budget_level / preferences / attractions`
  - 通过 HTTP POST 调用 `hotel_mcp:8003`。
  - 收到酒店 MCP 响应后，调用 LLM 使用 `HOTEL_REPLY_PROMPT` 生成自然语言推荐。
  - 将自然语言结果和酒店结构化数据一起回传 Coordinator。

- `extract_areas(self, tour_structured_data)`
  - 优先读取 `tour_structured_data["areas"]`。
  - 补充读取 `attractions[].area`。
  - 补充读取 `itinerary[].areas`。
  - 去重后返回区域列表。
  - 如果没有区域，默认返回 `["市中心"]`。

- `extract_budget_level(self, instruction)`
  - 根据用户输入判断预算：
    - 包含“便宜/经济/预算/省钱” -> `budget`
    - 包含“高端/豪华/五星/品质” -> `high`
    - 默认 -> `mid`

- `extract_preferences(self, instruction)`
  - 从用户输入中提取偏好：
    - 交通/地铁 -> 交通便利
    - 性价比/便宜 -> 预算友好
    - 评分/评价 -> 评分优先
    - 品牌 -> 品牌稳定
    - 景点/近 -> 靠近景点
  - 没有识别到时，默认返回交通便利、靠近景点、性价比高。

- `extract_city_from_instruction(self, instruction)`
  - 在没有上游结构化城市时，从用户输入中兜底识别常见城市。
  - 用于“只问酒店”场景。

## 9. `coordinator.py` 修改说明

`Coordinator` 是本次网络协同的核心改动点。

### 新增 Agent 注册

新增：

```python
self.agent_registry = {
    "weather_agent": 9010,
    "tour_agent": 9020,
    "hotel_agent": 9030
}
```

### 新增串行任务状态表

新增：

```python
self.pipeline_tasks = {}
```

典型状态：

```python
{
    "user_url": "...",
    "original_instruction": "...",
    "stage": "waiting_tour",
    "tour_result": None,
    "hotel_result": None
}
```

### 新增复合请求判断

新增方法：

```python
should_run_tour_then_hotel(instruction)
```

如果用户输入同时包含：

- 行程/景点类关键词：`景点`、`行程`、`旅游`、`旅行`、`游玩`、`路线`、`两日游` 等
- 酒店/住宿类关键词：`酒店`、`住宿`、`住哪`、`宾馆`、`民宿` 等

则进入串行流程：

```text
tour_agent -> hotel_agent
```

### 新增统一派发方法

新增方法：

```python
dispatch_to_agent(task_id, target_agent_name, instruction, context=None)
```

作用：

- 从 `agent_registry` 找端口。
- 构造 A2A Payload。
- 如果有 `context`，就附加给下游 Agent。
- 调用 `BaseAgent.send_to()` 通过 HTTP POST 发出。

### 新增串行回调处理

新增方法：

```python
handle_pipeline_result(data)
```

处理两种回调：

1. `source == "tour_agent"` 且 `stage == "waiting_tour"`
   - 保存 tour 结果。
   - 将阶段改为 `waiting_hotel`。
   - 构造酒店上下文。
   - 通过 HTTP 唤醒 `hotel_agent`。

2. `source == "hotel_agent"` 且 `stage == "waiting_hotel"`
   - 保存 hotel 结果。
   - 汇总最终答案。
   - 回传用户。

### 新增最终汇总

新增方法：

```python
finalize_pipeline_response(task_id)
```

最终回传格式：

```text
【行程规划】
tour_agent 的回复

【酒店推荐】
hotel_agent 的回复
```

### 新增无关问题处理

新增方法：

```python
reply_unsupported_task(task_id, user_url, instruction)
```

如果 LLM 路由返回 `none` 或非法结果，Coordinator 会直接通过用户回调地址返回提示，避免 `user.py` 一直等待。

### 函数级改动

修改的已有函数：

- `__init__(self, name, port, api_key)`
  - 保留原有 `api_key` 和 `pending_tasks`。
  - 新增 `self.pipeline_tasks = {}`，用于记录串行任务状态。
  - 在 `agent_registry` 中新增：
    - `"hotel_agent": 9030`

- `handle_task(self, data)`
  - 保留原来的用户任务登记逻辑。
  - 保留原来的普通 LLM 路由逻辑。
  - 保留原来的普通 Agent 结果回传逻辑。
  - 新增复合请求判断：
    - 如果用户输入同时包含旅游/行程关键词和酒店/住宿关键词，不走普通单 Agent 路由。
    - 先创建 `pipeline_tasks[task_id]`。
    - 再通过 HTTP 派发给 `tour_agent`。
  - 新增对串行回调的识别：
    - 如果 `task_id in self.pipeline_tasks`，调用 `handle_pipeline_result(data)`。
  - 当普通路由失败时，调用 `reply_unsupported_task()` 给用户回传提示。

- `finalize_response(self, data)`
  - 保留原来的普通 Agent 结果回传逻辑。
  - 新增：如果 Agent 返回了 `structured_data`，会一起回传给用户端，便于调试和展示。

保留的已有函数：

- `call_llm_for_routing(self, instruction)`
  - 仍然负责普通单 Agent 请求的 LLM 路由。
  - 没有参与复合请求的串行判断；复合请求由规则优先触发，保证演示稳定。

新增函数：

- `should_run_tour_then_hotel(self, instruction)`
  - 判断用户输入是否同时包含：
    - 旅游/行程/景点类关键词
    - 酒店/住宿类关键词
  - 返回 `True` 时启动串行流程。

- `dispatch_to_agent(self, task_id, target_agent_name, instruction, context=None)`
  - 统一构造 A2A Payload。
  - 根据 `agent_registry` 找端口。
  - 如果传入 `context`，就附加到 Payload。
  - 调用 `self.send_to(target_port, dispatch_payload)` 通过 HTTP POST 派发。

- `handle_pipeline_result(self, data)`
  - 处理串行任务中的 Agent 回调。
  - 当收到 `tour_agent` 结果：
    - 保存 `tour_result`
    - 阶段改为 `waiting_hotel`
    - 构造 `context`
    - 通过 HTTP 唤醒 `hotel_agent`
  - 当收到 `hotel_agent` 结果：
    - 保存 `hotel_result`
    - 调用 `finalize_pipeline_response()`

- `finalize_pipeline_response(self, task_id)`
  - 汇总 `tour_agent` 和 `hotel_agent` 的自然语言结果。
  - 组装最终回复：
    - `【行程规划】`
    - `【酒店推荐】`
  - 删除 `pipeline_tasks` 和 `pending_tasks` 中对应状态。
  - 通过用户 `callback_url` 回传最终结果。

- `reply_unsupported_task(self, task_id, user_url, instruction)`
  - 用于无关问题或无法路由问题。
  - 回传提示，说明系统支持天气、景点、行程、酒店类任务。
  - 防止用户端一直等待异步回调。

## 10. `prompts.py` 修改说明

原文件存在编码残留，可读性较差。本次重写为清晰中文 Prompt。

保留：

- `ROUTING_PROMPT_TEMPLATE`
- `WEATHER_EXTRACT_PROMPT`
- `WEATHER_REPLY_PROMPT`
- `TOUR_EXTRACT_PROMPT`
- `TOUR_REPLY_PROMPT`

新增：

- `HOTEL_REPLY_PROMPT`

`HOTEL_REPLY_PROMPT` 要求 LLM 根据：

- 用户住宿需求
- 上游行程自然语言结果
- 上游结构化行程数据
- 酒店 MCP 返回数据

生成酒店推荐，并说明推荐区域、品牌/类型、价格/性价比、评分评价和推荐原因。

### Prompt 级改动

修改的 Prompt：

- `ROUTING_PROMPT_TEMPLATE`
  - 增加 `hotel_agent` 的能力说明。
  - 增加“上海外滩附近住哪里比较方便？ -> hotel_agent”的示例。
  - 让普通单酒店问题可以被路由到 `hotel_agent`。

- `TOUR_REPLY_PROMPT`
  - 增加“结构化行程上下文”的说明。
  - 让景点 Agent 的自然语言回复和结构化输出语义一致。

新增的 Prompt：

- `HOTEL_REPLY_PROMPT`
  - 用于 `hotel_agent` 将 MCP 返回的酒店候选数据包装成自然语言。
  - 明确要求说明推荐区域、品牌/类型、价格/性价比、评分评价、适合当前行程的原因。

保留的 Prompt：

- `WEATHER_EXTRACT_PROMPT`
- `WEATHER_REPLY_PROMPT`
- `TOUR_EXTRACT_PROMPT`

## 11. `main.py` 修改说明

为了避免手动打开多个终端，本次将 `main.py` 改成一键启动器。

### 默认命令

```bash
python main.py --api_key YOUR_KEY
```

默认自动启动：

```text
tour_mcp.py
hotel_mcp.py
coordinator.py
tour_agent.py
hotel_agent.py
user.py
```

Windows 下默认每个组件打开一个新控制台窗口，方便观察每个进程的网络交互日志。

### 可选参数

启动天气链路：

```bash
python main.py --api_key YOUR_KEY --include-weather
```

只启动后台服务，不启动用户端：

```bash
python main.py --api_key YOUR_KEY --no-user
```

所有进程共用当前终端输出：

```bash
python main.py --api_key YOUR_KEY --same-window
```

通过环境变量提供 key：

```bash
set DEEPSEEK_API_KEY=YOUR_KEY
python main.py
```

### 函数级说明

新增函数：

- `build_services(api_key, include_weather, no_user)`
  - 根据启动参数生成要启动的进程列表。
  - 默认包含 `tour_mcp`、`hotel_mcp`、`coordinator`、`tour_agent`、`hotel_agent`、`user`。
  - 如果 `include_weather=True`，额外加入 `weather_mcp` 和 `weather_agent`。
  - 如果 `no_user=True`，不启动 `user.py`。

- `launch_service(name, command, port, new_window)`
  - 使用 `subprocess.Popen()` 启动单个组件。
  - Windows 默认使用 `CREATE_NEW_CONSOLE` 打开独立控制台。
  - 打印组件名、端口和启动命令。

- `stop_processes(processes)`
  - 在 `Ctrl+C` 或主流程结束时尝试关闭已启动进程。
  - 如果进程未及时退出，则强制结束。

- `parse_args()`
  - 解析命令行参数：
    - `--api_key`
    - `--include-weather`
    - `--no-user`
    - `--same-window`
    - `--startup-delay`

- `main()`
  - 检查 API key。
  - 调用 `build_services()` 生成服务列表。
  - 逐个调用 `launch_service()` 启动组件。
  - 循环监控子进程状态。
  - 捕获 `KeyboardInterrupt` 并关闭子进程。

## 12. 控制台日志展示点

本系统原有 `BaseAgent.log()` 会打印：

- 当前 Agent 名称
- 方向：`SEND` / `RECEIVE` / `AGENT_PROCESS`
- JSON Payload 内容

本次在 Coordinator 额外加入关键流程日志：

- 用户任务登记。
- 判断命中旅行 + 酒店复合请求。
- 派发给 `tour_agent`。
- 收到 `tour_agent` 网络回调。
- 依赖条件满足，唤醒 `hotel_agent`。
- 收到 `hotel_agent` 网络回调。
- 汇总结果回传用户。

这些日志可以直接用于证明网络链路确实发生了串行流转。

## 13. 典型演示输入

推荐演示输入：

```text
帮我规划上海两日游，并推荐交通方便、性价比高的酒店
```

预期触发：

```text
Coordinator
  -> tour_agent:9020
  -> tour_mcp:8002
  -> Coordinator
  -> hotel_agent:9030
  -> hotel_mcp:8003
  -> Coordinator
  -> User
```

只问景点：

```text
推荐几个上海景点
```

预期只走：

```text
Coordinator -> tour_agent -> tour_mcp -> Coordinator -> User
```

只问酒店：

```text
上海外滩附近推荐酒店
```

预期只走：

```text
Coordinator -> hotel_agent -> hotel_mcp -> Coordinator -> User
```

无关问题：

```text
帮我写一首诗
```

预期：

```text
Coordinator -> User
```

Coordinator 会提示当前系统主要支持旅行相关任务。

## 14. 验证记录

已完成的检查：

- 使用只读 `compile()` 检查仓库内全部 `.py` 文件，语法通过。
- 直接调用 `TourMcp.handle_task()`，确认 `get_attractions` 返回 JSON-RPC 2.0 格式，并带有 `area/suggested_time/tags`。
- 直接调用 `HotelMcp.handle_task()`，确认 `recommend_hotels` 返回 JSON-RPC 2.0 格式，并能根据区域和景点生成酒店推荐。
- 本地环境暂未安装 `openai` 包，直接导入 Agent 会触发 `llm_client.py` 的依赖错误；验证纯逻辑时临时注入 fake `llm_client`，确认：
  - `TourAgent.build_structured_data()` 行为正确。
  - `Coordinator.should_run_tour_then_hotel()` 能识别复合请求。

## 15. 和作业要求的对应关系

| 作业要求 | 本次实现对应点 |
| --- | --- |
| 新增旅行社 Agent | 新增 `hotel_agent.py` |
| 新 Agent 配独立 MCP Server | 新增 `hotel_mcp.py`，监听 `8003` |
| MCP 使用 HTTP/JSON-RPC | `hotel_agent` 调用 `hotel_mcp.recommend_hotels` |
| Agent 间不直接函数调用 | `tour_agent` 与 `hotel_agent` 只通过 Coordinator 网络传递 |
| 串行或条件触发依赖 | Coordinator 等 `tour_agent` 回调后才唤醒 `hotel_agent` |
| 控制台打印网络交互 | 复用 `BaseAgent.log()`，Coordinator 增加阶段日志 |
| 多进程/端口管理 | `main.py` 一键启动多个独立进程 |

## 16. 后续可选增强

当前版本先聚焦核心扩展功能。后续如果需要拿更多扩展分，可以考虑：

- 加 `--mock-llm` 模式，调试时不消耗 API key。
- 加分布式网络容错：MCP 超时后回传标准错误报文。
- 加 Agent 注册中心：Agent 启动时注册能力和端口，Coordinator 查询后派发。
- 加 TCP A2A 协议：用 `socket + struct` 实现 Length Header + JSON Body。
