import os
from openai import OpenAI

os.environ.pop("OPENAI_BASE_URL", None)
os.environ.pop("OPENAI_API_BASE", None)

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key="",  
)

response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Xin chào!"}],
    model="openai/gpt-4o-mini",
)

print(response.choices[0].message.content)