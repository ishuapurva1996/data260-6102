"""Decode mocked HTTP replies through the installed Ollama/LangChain stack."""

import json
from uuid import UUID

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from langchain_ollama import ChatOllama
from ollama import ResponseError

from src.model_client import build_ollama_client

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search public listings.",
            "parameters": {"type": "object", "properties": {"criteria": {"type": "string"}}},
        },
    }
]


@pytest.fixture
def http_model(monkeypatch):
    """Replace only HTTP transport, leaving provider decoding and model invocation real."""
    real_client = httpx.Client
    clients = []
    requests = []
    replies = []
    prepared_requests = []

    class ObservedClient(real_client):
        def build_request(self, *args, **kwargs):
            request = super().build_request(*args, **kwargs)
            prepared_requests.append(request)
            return request

    def respond(request):
        assert int(request.headers["content-length"]) == len(request.content)
        assert request.headers["x-protocol-test"] == "preserved"
        assert request.extensions["timeout"]["read"] == 10
        payload = json.loads(request.content)
        if not any(
            message.get("tool_call_id") or message.get("tool_calls")
            for message in payload["messages"]
        ):
            assert request is prepared_requests[-1], "Non-tool requests must remain untouched"
        requests.append(payload)
        assert replies, "The adapter made an unrequested extra model call"
        return replies.pop(0)

    def create_client(**kwargs):
        kwargs["headers"]["x-protocol-test"] = "preserved"
        client = ObservedClient(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", create_client)
    model = build_ollama_client("offline-model", "http://127.0.0.1:11434", 0, 10)
    assert isinstance(model._model, ChatOllama)
    yield model, replies, requests
    for client in clients:
        client.close()


def provider_reply(calls=None, *, content="", input_tokens=11, output_tokens=5, chunks=False):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    payload = {
        "model": "offline-model",
        "message": message,
        "done": True,
        "prompt_eval_count": input_tokens,
        "eval_count": output_tokens,
    }
    if chunks:
        first = {"model": "offline-model", "message": message, "done": False}
        payload["message"] = {"role": "assistant", "content": ""}
        body = "\n".join(json.dumps(item) for item in (first, payload)) + "\n"
        return httpx.Response(200, text=body, headers={"content-type": "application/x-ndjson"})
    return httpx.Response(200, json=payload)


@pytest.mark.parametrize("chunks", [False, True])
@pytest.mark.parametrize("call_id", ["wire-call-7", None])
def test_wire_malformed_arguments_preserve_diagnostic_and_allow_next_completion(
    http_model,
    chunks,
    call_id,
):
    client, replies, requests = http_model
    call = {"function": {"name": "search", "arguments": "{"}}
    if call_id is not None:
        call["id"] = call_id
    replies.append(provider_reply([call], chunks=chunks))

    result = client.complete([("user", "Find parking")], tools=TOOLS)

    assert len(requests) == 1
    assert result.raw_response.tool_calls == []
    (invalid,) = result.raw_response.invalid_tool_calls
    assert invalid["name"] == "search" and invalid["args"] == "{"
    assert invalid["error"]
    if call_id is not None:
        assert invalid["id"] == call_id
    else:
        assert str(UUID(invalid["id"])) == invalid["id"]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 5)
    assert result.usage.reported
    assert client.stats.turn_count == 1

    # The caller supplies the repair history; complete must not make a hidden retry.
    repair_history = [
        ("user", "Find parking"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": invalid["id"],
                    "name": invalid["name"],
                    "args": {},
                }
            ],
        ),
        ToolMessage(
            content="Invalid arguments; repair the call.",
            tool_call_id=invalid["id"],
            name=invalid["name"],
        ),
    ]
    replies.append(
        provider_reply(content="Please give a search area.", input_tokens=9, output_tokens=4)
    )
    followup = client.complete(repair_history, tools=TOOLS)

    assert len(requests) == 2
    assert [item["role"] for item in requests[1]["messages"]] == ["user", "assistant", "tool"]
    assert requests[1]["messages"][1]["tool_calls"][0]["function"]["arguments"] == {}
    assert followup.content == "Please give a search area."
    assert followup.raw_response.invalid_tool_calls == []
    assert (followup.usage.input_tokens, followup.usage.output_tokens) == (9, 4)
    assert (client.stats.turn_count, client.stats.input_tokens, client.stats.output_tokens) == (
        2,
        20,
        9,
    )


def test_valid_wire_tool_call_and_usage_keep_normal_langchain_decoding(http_model):
    client, replies, requests = http_model
    replies.append(
        provider_reply(
            [
                {
                    "function": {"name": "search", "arguments": {"criteria": "parking"}},
                }
            ],
            input_tokens=13,
            output_tokens=4,
            chunks=True,
        )
    )

    result = client.complete([("user", "Find parking")], tools=TOOLS)

    assert len(requests) == 1
    (call,) = result.raw_response.tool_calls
    assert call["name"] == "search" and call["args"] == {"criteria": "parking"}
    assert str(UUID(call["id"])) == call["id"]
    assert result.raw_response.invalid_tool_calls == []
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) == (
        13,
        4,
        17,
    )
    assert result.usage.reported
    assert (client.stats.turn_count, client.stats.total_tokens) == (1, 17)


def test_response_hook_is_only_installed_on_sync_client(http_model):
    client, _, _ = http_model
    assert client._model.sync_client_kwargs["event_hooks"]["response"]
    assert "event_hooks" not in client._model.async_client_kwargs


def test_rejected_arguments_are_not_added_to_langchain_error_metadata(http_model):
    client, replies, _ = http_model
    errors = []

    class ObserveErrors(BaseCallbackHandler):
        def on_llm_error(self, error, **kwargs):
            errors.append((str(error), kwargs))

    client._model.callbacks = [ObserveErrors()]
    raw_arguments = '{"criteria":"PRIVATE_SENTINEL"'
    replies.append(
        provider_reply(
            [
                {
                    "function": {"name": "search", "arguments": raw_arguments},
                }
            ]
        )
    )

    result = client.complete([("user", "Find parking")], tools=TOOLS)

    assert result.raw_response.invalid_tool_calls[0]["args"] == raw_arguments
    assert errors
    assert "PRIVATE_SENTINEL" not in str(errors)


def test_wire_malformed_arguments_without_counts_keep_usage_unreported(http_model):
    client, replies, requests = http_model
    replies.append(
        httpx.Response(
            200,
            json={
                "model": "offline-model",
                "done": True,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {"name": "search", "arguments": "{"},
                        }
                    ],
                },
            },
        )
    )

    result = client.complete([("user", "Find parking")], tools=TOOLS)

    assert len(requests) == 1
    assert result.raw_response.invalid_tool_calls[0]["args"] == "{"
    assert not result.usage.reported


@pytest.mark.parametrize("model_error", [False, True])
def test_native_id_request_scope_ends_after_success_or_error(http_model, model_error):
    client, replies, _ = http_model
    messages = [
        ("user", "Find parking"),
        AIMessage(content="", tool_calls=[{"id": "scoped-id", "name": "search", "args": {}}]),
        ToolMessage(content="No matches.", tool_call_id="scoped-id", name="search"),
    ]
    if model_error:
        replies.append(httpx.Response(500, json={"error": "offline failure"}))
        with pytest.raises(ResponseError, match="offline failure"):
            client.complete(messages, tools=TOOLS)
    else:
        replies.append(provider_reply(content="No matches."))
        client.complete(messages, tools=TOOLS)

    # Reusing the public Auth outside complete must not inherit its old history.
    request = httpx.Request(
        "POST",
        "http://127.0.0.1:11434/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "Find parking"},
                {
                    "role": "assistant",
                    "tool_calls": [{"function": {"name": "search", "arguments": {}}}],
                },
                {"role": "tool", "content": "No matches."},
            ],
        },
    )
    auth = client._model.sync_client_kwargs["auth"]
    assert next(auth.sync_auth_flow(request)) is request


def test_real_decoder_and_handwritten_loop_repair_one_wire_operation(http_model):
    import io

    from src.tool_agent.loop import run_agent

    client, replies, requests = http_model
    replies.extend(
        [
            provider_reply(
                [{"id": "bad-native", "function": {"name": "count_rentals", "arguments": "{"}}],
                chunks=True,
            ),
            provider_reply(
                [{"function": {"name": "count_rentals", "arguments": {"manager_id": 98}}}],
                chunks=True,
            ),
            provider_reply(content="There are three rentals.", chunks=True),
        ]
    )
    invoked, stream = [], io.StringIO()

    def execute(name, inputs):
        invoked.append((name, inputs))
        return '{"ok":true,"data":{"count":3},"error":null}'

    result = run_agent(
        "Count manager 98 rentals.", model=client, executor=execute, log_stream=stream
    )
    assert result.stop_reason == "completed" and len(requests) == 3
    assert invoked == [("count_rentals", {"manager_id": 98})]
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len([e for e in events if e["event"] == "proposal"]) == 1
    assert next(e for e in events if e["event"] == "repair")["final_valid"]
    repair_messages = requests[1]["messages"]
    assert next(m for m in repair_messages if m["role"] == "tool")["tool_call_id"] == "bad-native"
    assert (
        next(m for m in repair_messages if m["role"] == "assistant")["tool_calls"][0]["id"]
        == "bad-native"
    )
