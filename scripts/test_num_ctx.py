"""Test if Ollama num_ctx parameter is working correctly."""

import ollama
import os
from dotenv import load_dotenv

load_dotenv()

# Create a long prompt to test num_ctx
long_text = 'Test word. ' * 5000  # About 10,000 tokens

print('Testing with Ollama native API and num_ctx=32768...')
response = ollama.chat(
    model=os.getenv('OLLAMA_MODEL'),
    messages=[{'role': 'user', 'content': f'Count words in this text (just say the number): {long_text}'}],
    options={'num_ctx': 32768}
)
print('Response:', response['message']['content'][:200])
if 'prompt_eval_count' in response:
    print('Prompt tokens:', response.get('prompt_eval_count'))
if 'eval_count' in response:
    print('Response tokens:', response.get('eval_count'))
