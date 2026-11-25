"""Deterministic local chat model for the demo agents.

The platform is model-agnostic: any LangChain chat model can be plugged
in. The demo agents run on this local deterministic model so the whole
platform runs offline, reproducibly, with no API key — which is what
makes the durability, trace, approval-gate, and eval features testable
here. The model is a rule-based ReAct policy: it derives a step plan
from the task text, then executes the steps in order through tool calls,
and produces a final answer when the plan is done.

Token counting is a word-count proxy (see `estimate_tokens`) and cost is
an estimate using the reference rates in config.py — both are documented
as estimates, not metered usage.
"""
import re
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .. import config


def estimate_tokens(text):
    """Rough token proxy: word count. Documented as an estimate."""
    if not text:
        return 0
    return max(1, len(str(text).split()))


def estimate_cost(input_tokens, output_tokens):
    return (
        input_tokens * config.COST_INPUT_PER_MTOK
        + output_tokens * config.COST_OUTPUT_PER_MTOK
    ) / 1_000_000


def extract_subject(task):
    """Extract the subject (usually a vendor/company name) from a task."""
    m = re.search(r'"([^"]+)"', task)
    if m:
        return m.group(1)
    # Capitalised multi-word phrase, e.g. "Acme Corp"
    m = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", task)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z][a-z]+)\b", task)
    if m:
        return m.group(1)
    return "Acme Corp"


def derive_plan(task):
    """Derive an ordered step list from the task text.

    Each step is {"tool": name, "why": reason}. The order is the
    execution order. Risky tools (crm_update, send_message, delete_file)
    are placed last so the approval gate is hit after the safe work.
    """
    t = task.lower()
    steps = []
    if any(w in t for w in ("research", "vendor", "supplier", "company", "look up", "find")):
        steps.append({"tool": "web_search", "why": "find sources on the subject"})
    if any(w in t for w in ("research", "vendor", "supplier", "company")):
        steps.append({"tool": "web_fetch", "why": "read the top source in detail"})
    if any(w in t for w in ("look up", "check", "customer", "record")):
        steps.append({"tool": "crm_lookup", "why": "look up the customer record"})
    if any(w in t for w in ("cost", "price", "total", "quote", "seats", "compute")):
        steps.append({"tool": "calculator", "why": "compute the total"})
    if any(w in t for w in ("save", "file", "summary", "report", "write")):
        steps.append({"tool": "file_writer", "why": "save a summary file"})
    if any(w in t for w in ("crm", "update the record", "update crm")):
        steps.append({"tool": "crm_update", "why": "update the CRM record with the quote"})
    if any(w in t for w in ("send", "message", "notify", "email")):
        steps.append({"tool": "send_message", "why": "send the message"})
    if "delete" in t:
        steps.append({"tool": "delete_file", "why": "delete the file"})
    if not steps:
        steps.append({"tool": "web_search", "why": "gather background"})
    return steps


def _numbers(task):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", task)]


def _build_expression(task):
    nums = _numbers(task)
    if len(nums) >= 2:
        expr = f"{nums[0]}*{nums[1]}"
        if len(nums) >= 3 and any(w in task.lower() for w in ("plus", "setup", "fee", "and")):
            expr += f"+{nums[2]}"
        return expr
    if len(nums) == 1:
        return str(nums[0])
    return "0"


def _tool_result(messages, tool_name):
    """Return the parsed JSON content of the last ToolMessage for a tool."""
    import json

    for m in reversed(messages):
        if isinstance(m, ToolMessage) and getattr(m, "name", None) == tool_name:
            try:
                return json.loads(m.content)
            except Exception:
                return {"raw": m.content}
    return None


def _build_tool_args(tool_name, task, messages):
    subject = extract_subject(task)
    if tool_name == "web_search":
        return {"query": f"{subject} pricing and overview"}
    if tool_name == "web_fetch":
        res = _tool_result(messages, "web_search") or {}
        url = (res.get("results") or [{}])[0].get("url", "https://example.com/acme")
        return {"url": url}
    if tool_name == "crm_lookup":
        return {"customer": subject}
    if tool_name == "calculator":
        return {"expression": _build_expression(task)}
    if tool_name == "file_writer":
        fetch = _tool_result(messages, "web_fetch") or {}
        calc = _tool_result(messages, "calculator") or {}
        total = calc.get("result", "n/a")
        facts = fetch.get("content", "No details fetched.")
        filename = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_") + "_summary.md"
        content = (
            f"# {subject} — research summary\n\n"
            f"## Findings\n{facts}\n\n"
            f"## Total cost\n{total}\n\n"
            f"Prepared by the Scout agent."
        )
        return {"filename": filename, "content": content}
    if tool_name == "crm_update":
        lookup = _tool_result(messages, "crm_lookup") or {}
        calc = _tool_result(messages, "calculator") or {}
        record_id = lookup.get("record_id", "CUST-1042")
        return {
            "record_id": record_id,
            "fields": {"quote_total": calc.get("result", "n/a"), "status": "quoted"},
        }
    if tool_name == "send_message":
        calc = _tool_result(messages, "calculator") or {}
        m = re.search(r"to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", task)
        recipient = m.group(1) if m else subject
        return {
            "recipient": recipient,
            "message": f"Hi {recipient}, the total for {subject} is {calc.get('result', 'n/a')}. Summary saved.",
        }
    if tool_name == "delete_file":
        m = re.search(r"([a-z0-9_]+\.(?:md|txt|json))", task.lower())
        return {"path": m.group(1) if m else "old_summary.md"}
    return {}


class DeterministicModel(BaseChatModel):
    """A rule-based chat model implementing the LangChain interface.

    `available_tools` is the set of tool names the model may call. The
    "degraded" eval variant passes a reduced set (no calculator) so the
    agent must cope with a missing capability.
    """

    available_tools: list = []
    model_name: str = "warden-local-deterministic"

    @property
    def _llm_type(self):
        return "warden-local-deterministic"

    def bind_tools(self, tools, **kwargs):
        names = []
        for t in tools:
            names.append(getattr(t, "name", str(t)))
        return DeterministicModel(available_tools=names, model_name=self.model_name)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # The task is the first human message.
        task = ""
        for m in messages:
            if m.type == "human":
                task = m.content
                break
        # Rejected tools (a human said no) — never call them again.
        rejected = set()
        for m in messages:
            if m.type == "human" and isinstance(m.content, str) and \
                    m.content.startswith("[APPROVAL REJECTED]"):
                rejected.add(m.content.split("]")[1].strip().split(":")[0].strip())
        plan = derive_plan(task)
        # A tool counts as completed only if its last ToolMessage has no error.
        completed = set()
        error_count = {}
        for m in messages:
            if isinstance(m, ToolMessage):
                name = getattr(m, "name", "")
                try:
                    import json
                    parsed = json.loads(m.content)
                    has_error = isinstance(parsed, dict) and "error" in parsed
                except Exception:
                    has_error = False
                if has_error:
                    error_count[name] = error_count.get(name, 0) + 1
                else:
                    completed.add(name)
        # A tool that errored twice is failed — skip it (do not retry forever).
        failed = {t for t, c in error_count.items() if c >= 2}
        # Find the first plan step whose tool is available, not done,
        # not failed, and not rejected.
        next_step = None
        missing_tool = None
        for step in plan:
            tool = step["tool"]
            if tool in completed or tool in failed or tool in rejected:
                continue
            if tool not in self.available_tools:
                missing_tool = tool
                break
            next_step = step
            break
        input_text = "\n".join(str(getattr(m, "content", "")) for m in messages)
        input_tokens = estimate_tokens(input_text)
        if next_step is not None:
            args = _build_tool_args(next_step["tool"], task, messages)
            text = f"Next step: {next_step['tool']} — {next_step['why']}."
            output_tokens = estimate_tokens(text) + estimate_tokens(str(args))
            ai = AIMessage(
                content=text,
                tool_calls=[
                    {
                        "name": next_step["tool"],
                        "args": args,
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            )
        elif missing_tool is not None:
            text = (
                f"I cannot complete this task: the tool '{missing_tool}' is "
                f"not available in this agent version. Completed steps: "
                f"{sorted(completed) or 'none'}. The task is only partially done."
            )
            output_tokens = estimate_tokens(text)
            ai = AIMessage(
                content=text,
                usage_metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            )
        else:
            done = ", ".join(s["tool"] for s in plan if s["tool"] in completed)
            problems = []
            if failed:
                problems.append(f"failed tools: {sorted(failed)}")
            if rejected:
                problems.append(f"rejected by a human: {sorted(rejected)}")
            suffix = (" Partial completion — " + "; ".join(problems) + "."
                      if problems else "")
            text = (
                f"Task complete. I executed: {done or 'nothing'}."
                f"{suffix} All results are recorded in the trace."
            )
            output_tokens = estimate_tokens(text)
            ai = AIMessage(
                content=text,
                usage_metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            )
        return ChatResult(generations=[ChatGeneration(message=ai)])
