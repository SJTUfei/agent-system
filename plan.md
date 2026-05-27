# 酒店 Agent 扩展方案

## 1. 仓库现状判断

当前项目是一个轻量级分布式多 Agent 原型，整体风格比较直接：

- `BaseAgent.py` 封装所有 Agent 的 HTTP 监听、A2A JSON 收发和日志打印。
- `coordinator.py` 负责接收用户任务、用 LLM 路由到工作 Agent、等待 Agent 回调结果，再回传给用户。
- `weather_agent.py` / `tour_agent.py` 是工作 Agent，流程都是：接收 Coordinator 的 A2A 任务 -> 调用自己的 MCP Server -> 用 LLM 包装回复 -> POST 回 Coordinator。
- `weather_mcp.py` / `tour_mcp.py` 是独立 MCP Server，使用 Python 原生 `http.server`，并按 JSON-RPC 2.0 格式收发。
- 通信 Payload 当前采用扁平结构：

```json
{
  "source": "coordinator",
  "target": "tour_agent",
  "task_id": "1001",
  "instruction": "帮我规划上海两日游",
  "callback_url": "http://localhost:9000"
}
```

因此新增酒店 Agent 最干净的方式是继续沿用这个结构，只在 Payload 中增加可选的 `context` / `structured_data` 字段，不破坏已有 Agent。

## 2. 本次扩展目标

你负责实现 `hotel_agent` 和它独立的 `hotel_mcp`，并让它和同学负责的 `tour_agent` 形成明确的网络执行依赖：

```text
User
  -> Coordinator: 用户提出旅行 + 酒店需求
  -> TourAgent: Coordinator 先派发景点/行程规划任务
  -> TourMCP: TourAgent 通过 JSON-RPC 获取景点数据
  -> Coordinator: TourAgent 通过网络回传行程结果
  -> HotelAgent: Coordinator 收到 tour 结果后，再通过网络唤醒酒店 Agent
  -> HotelMCP: HotelAgent 通过 JSON-RPC 获取酒店推荐数据
  -> Coordinator: HotelAgent 回传最终酒店推荐
  -> User: Coordinator 汇总行程 + 酒店推荐后返回
```

关键点：`hotel_agent` 不直接调用 `tour_agent` 的 Python 函数，也不读取它的内存结果；必须等待 Coordinator 通过 HTTP 收到 `tour_agent` 的网络回调后，再由 Coordinator 通过 HTTP 派发给 `hotel_agent`。

范围说明：

- 本扩展链路不主动接入 `weather_agent`。只有用户明确询问天气时，系统继续走原有天气 Agent 路由。
- 本扩展重点证明 `tour_agent -> hotel_agent` 的网络串行依赖，以及 `hotel_agent -> hotel_mcp` 的独立 MCP 调用。
- 分布式网络容错本轮暂不实现，先保证核心作业扩展链路清晰可演示。

## 3. 端口规划

沿用现有端口习惯：

| 组件 | 端口 | 说明 |
| --- | ---: | --- |
| Coordinator | `9000` | 主控 Agent |
| WeatherAgent | `9010` | 已有天气 Agent |
| TourAgent | `9020` | 同学负责的景点/行程 Agent |
| HotelAgent | `9030` | 新增酒店 Agent |
| WeatherMCP | `8001` | 已有天气 MCP |
| TourMCP | `8002` | 同学负责/已有景点 MCP |
| HotelMCP | `8003` | 新增酒店 MCP |

## 4. 与 TourAgent 的接口约定

为了方便同学实现 tour-agent，也为了兼容现在已有的 `tour_agent.py`，建议采用“结构化字段优先，纯文本兜底”的契约。

### 4.1 TourAgent 回传给 Coordinator

推荐格式：

```json
{
  "source": "tour_agent",
  "target": "coordinator",
  "task_id": "1001",
  "instruction": "这里是自然语言行程规划结果",
  "structured_data": {
    "city": "上海",
    "days": 2,
    "attractions": [
      {"name": "外滩", "area": "黄浦区", "suggested_time": "晚上"},
      {"name": "上海博物馆", "area": "黄浦区", "suggested_time": "上午"}
    ],
    "itinerary": [
      {"day": 1, "areas": ["黄浦区", "南京东路"], "summary": "外滩和南京路路线"},
      {"day": 2, "areas": ["人民广场", "浦东"], "summary": "博物馆和陆家嘴路线"}
    ]
  }
}
```

兼容策略：

- 如果同学暂时只回传 `instruction` 文本，`Coordinator` 仍可以把这个文本作为 `tour_result_text` 转给 `hotel_agent`。
- 如果有 `structured_data`，`hotel_agent` 优先使用里面的 `city`、`areas`、`attractions`、`itinerary`，酒店推荐会更稳定。

### 4.2 对现有 TourAgent 的轻量增强

现在仓库里的 `tour_agent.py` 和 `tour_mcp.py` 已经基本完成，可以作为景点 Agent/MCP 使用。为了让酒店 Agent 更方便地依赖它，计划做一层不破坏原逻辑的增强：

- `tour_mcp.py`
  - 保留现有 JSON-RPC 方法名 `get_attractions`。
  - 将 mock 景点数据从只有 `name` / `description`，扩展为 `name` / `description` / `area` / `suggested_time` / `tags`。
  - 返回值仍放在 JSON-RPC 的 `result` 字段里，避免影响 `tour_agent` 的调用方式。

- `tour_agent.py`
  - 保留现有自然语言 `instruction` 回传。
  - 在 `return_payload` 中额外增加 `structured_data`。
  - `structured_data.city` 来自 LLM 提取出的城市。
  - `structured_data.attractions` 直接来自 `tour_mcp` 返回的景点数组。
  - `structured_data.itinerary` 先用简单规则生成，例如把景点区域聚合为推荐住宿/游玩区域；后续同学如果补更完整行程，也能替换这部分。

增强后的回传示例：

```json
{
  "source": "tour_agent",
  "target": "coordinator",
  "task_id": "1001",
  "instruction": "自然语言行程规划结果",
  "structured_data": {
    "city": "上海",
    "days": null,
    "attractions": [
      {
        "name": "外滩",
        "description": "经典城市景观",
        "area": "黄浦区",
        "suggested_time": "晚上",
        "tags": ["夜景", "地标"]
      }
    ],
    "itinerary": [
      {
        "day": 1,
        "areas": ["黄浦区"],
        "summary": "围绕外滩、南京东路等核心景点游览"
      }
    ]
  }
}
```

这样做的好处是：同学的 TourAgent 仍然可以独立完成景点推荐展示；我们的 HotelAgent 则可以稳定读取 `city`、`area`、`attractions`，不用从大段自然语言里反复猜。

## 5. HotelAgent 接口设计

### 5.1 Coordinator 派发给 HotelAgent

```json
{
  "source": "coordinator",
  "target": "hotel_agent",
  "task_id": "1001",
  "instruction": "用户原始需求：帮我规划上海两日游并推荐酒店",
  "callback_url": "http://localhost:9000",
  "context": {
    "dependency": "tour_agent",
    "tour_result_text": "TourAgent 的自然语言结果",
    "tour_structured_data": {
      "city": "上海",
      "days": 2,
      "attractions": [],
      "itinerary": []
    }
  }
}
```

### 5.2 HotelAgent 调用 HotelMCP

JSON-RPC 2.0 请求：

```json
{
  "jsonrpc": "2.0",
  "method": "recommend_hotels",
  "params": {
    "city": "上海",
    "areas": ["黄浦区", "南京东路", "人民广场"],
    "budget_level": "mid",
    "preferences": ["交通便利", "靠近景点", "性价比高"],
    "attractions": ["外滩", "上海博物馆"]
  },
  "id": "1001"
}
```

JSON-RPC 2.0 响应：

```json
{
  "jsonrpc": "2.0",
  "result": [
    {
      "name": "上海外滩附近精选酒店",
      "area": "黄浦区",
      "brand": "精选商务",
      "price_level": "中等",
      "score": 4.7,
      "reason": "靠近外滩和南京东路，步行及地铁都方便",
      "tags": ["交通便利", "景点近", "性价比高"]
    }
  ],
  "id": "1001"
}
```

### 5.3 HotelAgent 回传给 Coordinator

```json
{
  "source": "hotel_agent",
  "target": "coordinator",
  "task_id": "1001",
  "instruction": "自然语言酒店推荐结果",
  "structured_data": {
    "hotels": [],
    "based_on": "tour_agent"
  }
}
```

## 6. Coordinator 串行依赖设计

建议在 `Coordinator` 中新增一个轻量级任务状态表，例如：

```python
self.pipeline_tasks = {
    task_id: {
        "user_url": "...",
        "original_instruction": "...",
        "stage": "waiting_tour",
        "tour_result": None,
        "hotel_result": None
    }
}
```

处理逻辑：

1. 用户输入中如果同时包含“景点/行程/旅游规划”和“酒店/住宿/住哪里”等意图，Coordinator 不直接路由到单一 Agent，而是启动 `tour_then_hotel` 流程。
2. Coordinator 先向 `tour_agent:9020` 发送任务，`stage = waiting_tour`。
3. Coordinator 收到 `tour_agent` 回传后，保存 `tour_result`，打印“依赖已满足，准备唤醒 hotel_agent”。
4. Coordinator 再向 `hotel_agent:9030` 发送任务，并把 `tour_result` 放入 `context`，`stage = waiting_hotel`。
5. Coordinator 收到 `hotel_agent` 回传后，将 tour 结果和 hotel 结果合并，回传给 User。

这样可以清楚证明“酒店 Agent 依赖景点 Agent 的网络结果”。

## 7. 新增和修改文件清单

计划新增：

- `hotel_agent.py`
  - 继承 `BaseAgent`
  - 监听 `9030`
  - 接收 Coordinator 的 `context.tour_*`
  - 调用 `hotel_mcp:8003` 的 `recommend_hotels`
  - 使用 LLM 将酒店数据包装成自然语言
  - 回调 Coordinator

- `hotel_mcp.py`
  - 使用 `http.server`
  - 监听 `8003`
  - 实现 JSON-RPC 2.0 方法 `recommend_hotels`
  - 根据城市、区域、景点、预算偏好返回模拟酒店数据

计划修改：

- `coordinator.py`
  - 注册 `hotel_agent:9030`
  - 增加 `tour_then_hotel` 串行流程状态
  - 收到 `tour_agent` 结果后条件触发 `hotel_agent`
  - 收到 `hotel_agent` 结果后汇总返回用户

- `tour_agent.py`
  - 保留原有景点推荐回复逻辑
  - 回传时补充 `structured_data`
  - 让 Coordinator 可以把结构化行程上下文转交给 HotelAgent

- `tour_mcp.py`
  - 保留原有 `get_attractions` 方法
  - 扩展 mock 景点字段，补充区域、推荐游览时间和标签
  - 为酒店推荐提供更明确的位置依据

- `prompts.py`
  - 增加酒店参数提取 Prompt
  - 增加酒店推荐回复 Prompt
  - 可选：增强路由 Prompt，使其能识别“行程 + 酒店”的复合请求

- `document.md` 或新增 `README` 片段
  - 记录启动顺序、端口、示例请求和预期日志

## 8. 日志展示要求

需要保证控制台能清晰展示这些关键事件：

- Coordinator 收到用户任务和 `task_id`
- Coordinator 判断进入 `tour_then_hotel` 串行流程
- Coordinator POST 到 `tour_agent:9020` 的 Payload
- TourAgent POST 到 `tour_mcp:8002` 的 JSON-RPC Payload
- Coordinator 收到 TourAgent 回调
- Coordinator 打印“等待条件满足：tour_agent 已完成，唤醒 hotel_agent”
- Coordinator POST 到 `hotel_agent:9030` 的 Payload，包含 `context`
- HotelAgent POST 到 `hotel_mcp:8003` 的 JSON-RPC Payload
- HotelAgent 回传 Coordinator
- Coordinator 汇总最终结果并回传 User

现有 `BaseAgent.log()` 已经能打印 Payload，酒店部分可以直接复用；Coordinator 的流程状态建议额外 `print()` 几行中文说明，便于实验展示。

## 9. 容错策略

虽然你主要负责新 Agent，但酒店链路可以顺手满足一部分“分布式网络容错”要求：

- `hotel_agent` 调用 `hotel_mcp` 时设置 `timeout=10`。
- MCP 调用失败时，`hotel_agent` 不阻塞，回传标准错误结构：

```json
{
  "source": "hotel_agent",
  "target": "coordinator",
  "task_id": "1001",
  "status": "error",
  "error": {
    "code": "HOTEL_MCP_UNAVAILABLE",
    "message": "酒店 MCP 服务不可用或超时"
  },
  "instruction": "抱歉，酒店推荐服务暂时不可用，但行程规划结果仍然有效。"
}
```

- Coordinator 收到酒店错误时，仍然把 TourAgent 的行程结果返回用户，并说明酒店节点不可用，防止系统卡死。

## 10. 启动与演示命令

预计需要 5 到 6 个终端：

```bash
python weather_mcp.py
python tour_mcp.py
python hotel_mcp.py
python coordinator.py --api_key YOUR_KEY
python tour_agent.py --api_key YOUR_KEY
python hotel_agent.py --api_key YOUR_KEY
python user.py
```

如果只演示“景点 -> 酒店”依赖，可以不启动天气相关进程。

示例用户输入：

```text
帮我规划上海两日游，安排几个经典景点，并根据行程推荐性价比高、交通方便的酒店。
```

预期效果：

- Coordinator 先派发给 TourAgent。
- TourAgent 完成后，Coordinator 再派发给 HotelAgent。
- 最终用户看到“行程规划 + 酒店推荐”的合并结果。

## 11. 实现顺序建议

1. 先轻量增强 `tour_mcp.py` 的 mock 数据字段，保证景点带有 `area` 等位置线索。
2. 再增强 `tour_agent.py` 的回传 Payload，补充 `structured_data`，但不改变现有 `instruction`。
3. 新增 `hotel_mcp.py`，用固定模拟数据跑通 JSON-RPC。
4. 新增 `hotel_agent.py`，让它接收 `context.tour_*` 并调用 HotelMCP。
5. 修改 `coordinator.py`，加入 `tour_then_hotel` 串行状态机。
6. 最后补充日志和演示文档，确保控制台能看出网络拓扑和条件触发。

## 12. Review 时重点确认

- `hotel_agent` 端口是否固定为 `9030`，`hotel_mcp` 是否固定为 `8003`。
- TourAgent 的 `structured_data` 字段是否按本计划由我们轻量补充，并保持不影响同学原来的自然语言输出。
- Coordinator 是只在“行程 + 酒店”复合请求时触发串行流程，还是所有旅游请求都自动追加酒店推荐。
- 最终展示时是否需要保留天气 Agent，还是只展示 TourAgent + HotelAgent 的扩展链路。
