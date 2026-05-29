"""
LLM integration with MCP tool loop.

Supports two backends, selected by environment variables:
  1. Claude via Azure AI Foundry (ANTHROPIC_API_KEY + ANTHROPIC_BASE_URL)
  2. Gemini via Google AI (GEMINI_API_KEY)

Claude is used when both ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are set.
"""
VERSION = "20260529"

import json
import logging
import os
from typing import Any

from mcp_client import McpClient

logger = logging.getLogger("ai_assistant.llm")

# Claude / Azure AI Foundry
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
CLAUDE_MODEL       = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")

# Gemini fallback
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_SYSTEM_PROMPT_BASE = """You are a data governance assistant with access to the Informatica
Intelligent Data Management Cloud (IDMC), including Cloud Data Governance & Catalog (CDGC)
and Data Marketplace. Help users search assets, explore business terms, check data quality,
review classifications, and answer questions about their data catalog.

FORMAT RULES — follow these exactly:
- You are responding inside an HTML chat UI. Use HTML tags for formatting, not Markdown.
- Use <strong> for bold, <em> for italic, <br> for line breaks.
- Use <table> with <thead>/<tbody>/<tr>/<th>/<td> for tabular data.
- Use <ul>/<li> for bullet lists, <ol>/<li> for numbered lists.
- Never use Markdown syntax (no **, no ##, no |---|, no backticks for tables).
- Keep responses concise. Summarize data rather than dumping raw JSON.
- If a question requires multiple tool calls, do them efficiently.
{asset_link_instruction}"""

def _build_system_prompt(pod: str = "") -> str:
    instruction = ""
    return _SYSTEM_PROMPT_BASE.format(asset_link_instruction=instruction)


# ---------------------------------------------------------------------------
# Claude via Azure AI Foundry
# ---------------------------------------------------------------------------

async def _chat_claude(user_message: str, mcp: McpClient, history: list[dict], pod: str = "") -> tuple[str, list[dict]]:
    import anthropic

    tool_declarations = await mcp.as_gemini_tools()
    tools = [
        {
            "name": d["name"],
            "description": d["description"],
            "input_schema": d["parameters"],
        }
        for d in tool_declarations
    ]

    messages = []
    for turn in history:
        role = "assistant" if turn["role"] == "model" else turn["role"]
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": user_message})

    # Azure AI Foundry gives the full endpoint URL ending in /v1/messages.
    # The Anthropic SDK appends /v1/messages itself, so we strip that suffix
    # to avoid doubling it. Azure also uses api-key header, not x-api-key.
    base_url = ANTHROPIC_BASE_URL.rstrip("/")
    for suffix in ("/v1/messages", "/messages"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break

    client = anthropic.Anthropic(
        api_key=ANTHROPIC_API_KEY,
        base_url=base_url,
        default_headers={"api-key": ANTHROPIC_API_KEY},
    )

    trace = []
    MAX_ITERATIONS = 10
    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=_build_system_prompt(pod),
            tools=tools,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})
        trace.append({"iteration": iteration + 1, "stop_reason": response.stop_reason})

        if response.stop_reason == "end_turn":
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(text_parts).strip(), trace

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                logger.info("Claude calling tool: %s", block.name)
                tool_entry = {"tool": block.name, "input": block.input, "status": "error", "error": "unknown"}
                result_str = f"Error: tool call did not complete"
                try:
                    result = await mcp.call_tool(block.name, block.input)
                    result_str = result if isinstance(result, str) else json.dumps(result)
                    tool_entry["status"] = "ok"
                    tool_entry["result"] = result_str
                except BaseException as e:
                    logger.error("Tool call failed: %s — %s", block.name, e)
                    result_str = f"Error calling {block.name}: {e}"
                    tool_entry["error"] = str(e)
                    tool_entry["result"] = result_str
                finally:
                    trace.append(tool_entry)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            trace.append({"note": f"Unexpected stop_reason: {response.stop_reason}"})
            break

    return "I was unable to complete the request after multiple attempts.", trace


# ---------------------------------------------------------------------------
# Gemini via Google AI
# ---------------------------------------------------------------------------

async def _chat_gemini(user_message: str, mcp: McpClient, history: list[dict], pod: str = "") -> tuple[str, list[dict]]:
    from google import genai
    from google.genai import types

    tool_declarations = await mcp.as_gemini_tools()
    tools = [
        types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=d["name"],
                description=d["description"],
                parameters=d["parameters"],
            )
            for d in tool_declarations
        ])
    ]

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(system_instruction=_build_system_prompt(pod), tools=tools)

    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"  # Gemini uses "model" not "assistant"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["text"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    trace = []
    MAX_ITERATIONS = 10
    for iteration in range(MAX_ITERATIONS):
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=contents, config=config)
        candidate = response.candidates[0]
        contents.append(candidate.content)
        trace.append({"iteration": iteration + 1})

        tool_calls = [
            p.function_call for p in candidate.content.parts
            if p.function_call and p.function_call.name
        ]

        if not tool_calls:
            return "\n".join(p.text for p in candidate.content.parts if p.text).strip(), trace

        tool_results = []
        for fc in tool_calls:
            logger.info("Gemini calling tool: %s", fc.name)
            tool_entry = {"tool": fc.name, "input": dict(fc.args)}
            try:
                result = await mcp.call_tool(fc.name, dict(fc.args))
                result_str = result if isinstance(result, str) else json.dumps(result)
                tool_entry["status"] = "ok"
                tool_entry["result"] = result_str
            except Exception as e:
                logger.error("Tool call failed: %s — %s", fc.name, e)
                result_str = f"Error calling {fc.name}: {e}"
                tool_entry["status"] = "error"
                tool_entry["error"] = str(e)
            trace.append(tool_entry)
            tool_results.append(
                types.Part(function_response=types.FunctionResponse(
                    name=fc.name, response={"result": result_str})))
        contents.append(types.Content(role="user", parts=tool_results))

    return "I was unable to complete the request after multiple attempts.", trace


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def chat(user_message: str, mcp: McpClient, history: list[dict] | None = None, pod: str = "") -> tuple[str, list[dict]]:
    h = history or []
    if ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL:
        logger.info("Using Claude (%s)", CLAUDE_MODEL)
        return await _chat_claude(user_message, mcp, h, pod=pod)
    logger.info("Using Gemini (%s)", GEMINI_MODEL)
    return await _chat_gemini(user_message, mcp, h, pod=pod)
