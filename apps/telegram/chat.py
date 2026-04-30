from openai import OpenAI
import os

# Get API key from environment variable (recommended for security)
# Set it with: $env:NVAPI_KEY="your-api-key" in PowerShell
api_key = os.environ.get("NVAPI_KEY")
if not api_key:
    raise ValueError("Set NVAPI_KEY environment variable with your NVIDIA API key")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

completion = client.chat.completions.create(
    model="tiiuae/falcon3-7b-instruct",
    messages=[{"content": "proceed", "role": "user"}],
    temperature=0.2,
    top_p=0.7,
    max_tokens=1024,
    stream=True
)

for chunk in completion:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
