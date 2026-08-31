# Model Client and Token Accounting - Part 4

## Implementation

- `src/model_client.py` is the reusable adapter. Its stable `complete(messages, tools=None)` method is the only place that invokes the underlying Ollama chat model.
- `code/agents_demo.py` obtains its Planner and Reviewer responses through that adapter.
- `code/hw1_client.py` is a command-line demonstration that loads `AGENT.md`, prints per-turn token counts, supports `/stats`, and prints cumulative totals on exit.
- `AGENT.md` requires strict Markdown bullets. All five recorded responses passed the bullet-only check.

## Recorded command

Run from the repository root:

```bash
python code/hw1_client.py --demo --model qwen3:1.7b --temperature 0.0 --timeout 120 \
  --output reports/hw01/raw/part4_five_turn_conversation.txt \
  --metrics-output reports/hw01/raw/part4_token_counts.json
```

## Recorded token results

| Turn | Input tokens | Output tokens | Total tokens |
|---:|---:|---:|---:|
| 1 | 115 | 34 | 149 |
| 2 | 168 | 29 | 197 |
| 3 | 218 | 18 | 236 |
| 4 | 266 | 24 | 290 |
| 5 | 311 | 50 | 361 |

After turn 3, `/stats` reported 501 cumulative input tokens, 81 cumulative output tokens, and 731 serialized-history characters. After turn 5, it reported 1,078 input tokens, 155 output tokens, and 1,348 history characters. `/stats` only reads the counters and serialized history; it does not append a message.

## Required explanations

### Why is prior conversation context resent with every turn?

The model does not keep the earlier chat by itself. The client resends the system prompt and conversation history so the next response can refer to previous questions and answers.

### How is a system prompt different from a user message?

A system prompt defines the model's overall role and response rules, such as the bullet-only review format. A user message supplies the current request. The system instruction has broader scope across the conversation.

### Why do input tokens grow during a conversation?

Each new request includes the earlier messages again. As the history becomes longer, the serialized prompt contains more text and therefore more input tokens.

### What eventually limits that growth?

The model has a finite context window. When the combined system prompt, history, current request, and expected response approach that limit, the client must trim or summarize older history.
