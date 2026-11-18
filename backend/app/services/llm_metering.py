"""Conservative token reservation for text and vision calls."""
import json
import uuid
from app.services.billing import reserve_call, finish_call


def begin(company_id, messages, max_tokens):
    # UTF-8 bytes conservatively bound common tokenizer usage; remote images
    # reserve an additional allowance. Final settlement uses provider usage.
    prompt_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
    images = sum(len(m.get('content', [])) for m in messages if isinstance(m.get('content'), list))
    prompt_bound += images * 8192
    key = 'llm:' + uuid.uuid4().hex
    reserve_call(company_id, key, 'llm', input_tokens=prompt_bound, output_tokens=max_tokens)
    return key


def unknown(key):
    if key: finish_call(key, 'unknown')


def release(key):
    if key: finish_call(key, 'release')


def settle(key, usage):
    if not key: return
    if (not isinstance(usage, dict) or not all(type(usage.get(f)) is int and usage[f] >= 0
                                             for f in ('prompt_tokens', 'completion_tokens'))):
        unknown(key)
        return
    finish_call(key, 'settle', input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'])
