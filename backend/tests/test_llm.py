import json
from app import llm

def test_strip_fence_bare_json_passthrough():
    assert llm._strip_fence('{"a": 1}') == '{"a": 1}'

def test_strip_fence_lowercase_fence():
    text = '```json\n{"a": 1}\n```'
    assert json.loads(llm._strip_fence(text)) == {"a": 1}

def test_strip_fence_uppercase_fence():
    text = '```JSON\n{"a": 1}\n```'
    assert json.loads(llm._strip_fence(text)) == {"a": 1}

def test_strip_fence_preserves_interior_backticks():
    text = '```json\n{"note": "see ```code``` here"}\n```'
    result = llm._strip_fence(text)
    parsed = json.loads(result)
    assert parsed == {"note": "see ```code``` here"}
