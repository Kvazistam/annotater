from datetime import datetime
import os
import requests, base64
from globals import *
import re


invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = True

def parse_stream_to_json(raw: str):
    full_text = ""
    pattern = r"data: {.*}"
    tokens = 0
    # groups = re.findall()
    for line in raw.split('data: '):
        if not line: continue
        line = line.strip(' \\n\n')
        # Игнорируем всё, кроме data: и сигнала конца
        # if not line.startswith("data: "): continue
        if line == "[DONE]": break
            
        try:
            groups = re.search(r"\{[\s\S]*\}", line)
            if not groups:
                raise KeyError
            chunk = json.loads(groups.group(0))
            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            tokens = chunk.get('usage', {}).get('total_tokens', 0)
            if content:
                full_text += content
        except (json.JSONDecodeError, IndexError, KeyError):
            continue
    print(tokens)

    return full_text


def ask_ai(promt):
    headers = {
    "Authorization": f"Bearer {NVIDIA_API_KEY}",
    "Accept": "text/event-stream" if stream else "application/json"
    }

    payload = {
    "model": "mistralai/mistral-medium-3.5-128b",
    "reasoning_effort": "high",
    "messages": [{"role":"user","content":promt}],
    #   "max_tokens": ,
    "temperature": 0.70,
    "top_p": 1.00,
    "stream": stream
    }
    
    response = requests.post(invoke_url, headers=headers, json=payload)
    
    cp = r"checkpoints"
    time = datetime.now().strftime("%H-%M-%S")
    path = os.path.join(cp, "ai_response"+time+".tmp")
    
    if response.status_code != 200:
        return f"Ошибка API: {response.status_code} - {response.text}"
    
    if stream:
        raw_data = response.text
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write(raw_data)
        json_string = parse_stream_to_json(raw_data)
        return json_string
    else:
        try:
            return response.json()
        except Exception as e:
            return f'error with response {e}'
    
    
# print(ask_ai("5+2. send me answer in json format"))

def test(file):
    with open(file, 'r', encoding='utf-8') as fp:
        raw = fp.read()
        print(parse_stream_to_json(raw))
        # with open(r'connections\checkpoints\full_texts\ai_response_test', 'w') as fp:
        #     fp.write(parse_stream_to_json(raw))

# test(r'connections\checkpoints\test')