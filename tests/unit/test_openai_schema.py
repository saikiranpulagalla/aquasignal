from signallock.contracts.schema import SafetyContract
from signallock.providers.openai_http import _strict_schema


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_strict_schema_objects_require_all_properties():
    schema = _strict_schema(SafetyContract.model_json_schema())
    for node in _walk(schema):
        if node.get("type") == "object" and "properties" in node:
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(node["properties"])
        assert "default" not in node
