"""Thin client for Lyzr Studio agents with JSON contracts and a mock fallback."""
import json
import re

import httpx

from .config import settings
from .mock_agents import MOCKS


class AgentError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """Parse the first JSON object in an LLM reply (tolerates ```json fences and prose)."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise AgentError(f"no JSON object in agent reply: {text[:200]}")
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    value = json.loads(text[start:i + 1])
                    break
        else:
            raise AgentError(f"unterminated JSON in agent reply: {text[:200]}")
    if not isinstance(value, dict):
        raise AgentError("agent reply is not a JSON object")
    return value


def _reply_text(body) -> str:
    if isinstance(body, str):
        return body
    for key in ("response", "message", "output", "answer", "result"):
        value = body.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return json.dumps(value)
    return json.dumps(body)


# The key (and its type) every agent's JSON reply must contain; see app/agents/*.md.
REPLY_CONTRACT = {
    "privacy_guard": ("segments", list),
    "extractor": ("commitments", list),
    "curator": ("decisions", list),
    "nudger": ("notifications", list),
    "router": ("intent", str),
    "recall": ("answer", str),
}


def validate_reply(agent: str, reply: dict) -> dict:
    key, kind = REPLY_CONTRACT[agent]
    if not isinstance(reply.get(key), kind):
        got = ", ".join(reply) or "nothing"
        raise AgentError(f"reply has no '{key}' {kind.__name__} (got: {got}). Check the agent's "
                         f"response format in Lyzr Studio: it must be plain text/JSON, not a "
                         f"custom schema")
    return reply


class LyzrClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self.last_error: dict[str, str] = {}

    def mode(self, agent: str) -> str:
        return "lyzr" if settings.agent_is_live(agent) else "mock"

    async def _call_lyzr(self, agent: str, message: str, uid: str, session_id: str) -> str:
        body = {
            "user_id": uid,
            "agent_id": settings.lyzr_agent_ids[agent],
            "session_id": f"{agent}-{session_id}",
            "message": message,
        }
        headers = {"Content-Type": "application/json", "x-api-key": settings.lyzr_api_key}
        async with httpx.AsyncClient(timeout=settings.lyzr_timeout,
                                     transport=self._transport) as client:
            resp = await client.post(settings.lyzr_chat_url, json=body, headers=headers)
        if resp.status_code >= 400:
            raise AgentError(f"Lyzr {agent} HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return _reply_text(resp.json())
        except ValueError:
            return resp.text

    async def run(self, agent: str, payload: dict, *, uid: str, session_id: str) -> tuple[dict, str]:
        """Run an agent. Returns (result, backend) where backend is lyzr | mock | mock-fallback."""
        if settings.agent_is_live(agent):
            message = json.dumps(payload, ensure_ascii=False, default=str)
            try:
                reply = await self._call_lyzr(agent, message, uid, session_id)
                result = validate_reply(agent, extract_json(reply))
                self.last_error.pop(agent, None)
                return result, "lyzr"
            except (AgentError, httpx.HTTPError, json.JSONDecodeError) as exc:
                reason = str(exc) or type(exc).__name__
                print(f"[lyzr] {agent} failed, using mock fallback: {reason}")
                self.last_error[agent] = reason
                return {**MOCKS[agent](payload), "_fallback_reason": reason}, "mock-fallback"
        return MOCKS[agent](payload), "mock"


lyzr = LyzrClient()
