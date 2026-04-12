from openai import OpenAI

def ask_llm(system_prompt, user_input, temperature=0.1, model="deepseek-chat"):
    """
    通用 LLM 调用接口
    model: 可以是 "gpt-4o", "deepseek-chat" 等
    """
    # 如果用 DeepSeek: base_url="https://api.deepseek.com"
    # 如果用 OpenAI: base_url="https://api.openai.com/v1"
    
    client = OpenAI(
        api_key="你的_API_KEY", 
        base_url="https://api.deepseek.com" # 以 DeepSeek 为例
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            stream=False,
            # 这里的 temperature 设低一点（如 0），对于路由决策这种需要精准结果的场景更好
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ LLM 调用出错: {e}")
        return "none"