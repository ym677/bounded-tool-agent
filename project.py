"""带参数校验、步骤预算和重复调用保护的工具规划实验。"""

import ast
import json
import math
import operator
from pathlib import Path
import re


SPEC = {
    "title": "有界工具规划 Agent",
    "subtitle": "把自然语言问题拆成可检查的工具调用，逐步执行并保留证据轨迹。",
    "slug": "04-bounded-tool-agent",
    "accent": "#c26735",
    "sample_input": "分析设备 P-101 最近 5 次温度，计算平均值超过阈值 70 的差值。",
    "input_label": "设备分析任务",
}

MAX_STEPS = 5
DATA_PATH = Path(__file__).parent / "data" / "synthetic_sensors.json"
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub,
             ast.Mult: operator.mul, ast.Div: operator.truediv}
METRICS = {"温度": "temperature", "压力": "pressure", "振动": "vibration"}


def calculate(expression):
    """解释一个受限的算术语法树，不执行 Python 代码。"""
    if not isinstance(expression, str) or not 1 <= len(expression) <= 100:
        raise ValueError("expression 必须是 1～100 个字符的字符串")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("算术表达式格式错误") from exc
    if len(list(ast.walk(tree))) > 32:
        raise ValueError("表达式过于复杂")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(node.value)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            try:
                value = OPERATORS[type(node.op)](visit(node.left), visit(node.right))
            except ZeroDivisionError as exc:
                raise ValueError("不能除以零") from exc
        else:
            raise ValueError("只允许数字、括号和加减乘除")
        if not math.isfinite(value) or abs(value) > 1e12:
            raise ValueError("计算结果超出允许范围")
        return value

    return {"value": round(visit(tree.body), 6), "expression": expression}


def sensor_summary(equipment="P-101", metric="temperature", window=5):
    if not isinstance(equipment, str) or not re.fullmatch(r"P-\d{3}", equipment):
        raise ValueError("设备编号格式应为 P-101")
    if metric not in METRICS.values():
        raise ValueError("metric 只支持 temperature、pressure、vibration")
    if type(window) is not int or not 1 <= window <= 100:
        raise ValueError("window 必须是 1～100 的整数")
    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
    selected = [row for row in records if row["equipment"] == equipment][-window:]
    if not selected:
        raise ValueError("示例数据中没有这个设备")
    values = [row[metric] for row in selected]
    return {"equipment": equipment, "metric": metric, "samples": len(values),
            "mean": round(sum(values) / len(values), 6), "minimum": min(values),
            "maximum": max(values), "source": "data/synthetic_sensors.json（合成）"}


def invoke(tool, arguments):
    if not isinstance(arguments, dict):
        raise ValueError("arguments 必须是 JSON 对象")
    definitions = {
        "sensor_summary": (sensor_summary, {"equipment", "metric", "window"}),
        "calculate": (calculate, {"expression"}),
    }
    if not isinstance(tool, str) or tool not in definitions:
        raise ValueError("工具不在白名单中")
    function, allowed = definitions[tool]
    if set(arguments) - allowed:
        raise ValueError("工具参数包含未知字段")
    try:
        return function(**arguments)
    except TypeError as exc:
        raise ValueError("工具参数缺失或类型不正确") from exc


def parse_action(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        action = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("规划器需要返回单个 JSON 对象") from exc
    if not isinstance(action, dict):
        raise ValueError("规划结果必须是对象")
    return action


def local_parameters(question):
    match = re.search(r"P-\d{3}", question)
    equipment = match.group() if match else "P-101"
    metric = next((value for key, value in METRICS.items() if key in question), "temperature")
    match = re.search(r"最近\s*(\d+)", question)
    window = int(match.group(1)) if match else 5
    match = re.search(r"阈值\s*(-?\d+(?:\.\d+)?)", question)
    default_limits = {"temperature": 70, "pressure": 1.5, "vibration": 0.3}
    limit = float(match.group(1)) if match else default_limits[metric]
    return {"equipment": equipment, "metric": metric, "window": window}, limit


def run(payload, client):
    question = payload.get("text", "").strip()
    if not question:
        raise ValueError("请输入设备分析任务")
    if not client.enabled and not re.search(r"设备|温度|压力|振动|P-\d{3}", question):
        raise ValueError("本地模式支持合成设备的温度、压力、振动统计，请使用示例任务或启用 API 模式")
    params, limit = local_parameters(question)
    trace = []
    seen = set()
    status = "completed"
    answer = ""
    system = (
        "你是工具规划器。只返回一个JSON对象。可用工具 sensor_summary 的 arguments 为"
        "{equipment:P-101或P-102,metric:temperature或pressure或vibration,window:1到100整数}，"
        "calculate 的 arguments 为 {expression:仅数字和加减乘除括号}。"
        "每次返回 {tool:工具名,arguments:参数}，证据充足后返回 {answer:中文结论}。"
        "只能依据工具返回内容作答，注明合成数据，不能执行代码。"
    )
    for step in range(MAX_STEPS):
        if client.enabled:
            action = parse_action(client.complete(
                system, json.dumps({"task": question, "observations": trace}, ensure_ascii=False),
                max_tokens=500))
        elif step == 0:
            action = {"tool": "sensor_summary", "arguments": params}
        elif step == 1:
            if "error" in trace[0]["result"]:
                action = {"answer": "工具未取得设备数据，原因是 " + trace[0]["result"]["error"]}
                answer = action["answer"]
                status = "tool_error"
                break
            mean = trace[0]["result"]["mean"]
            action = {"tool": "calculate", "arguments": {"expression": f"{mean} - {limit}"}}
        else:
            summary, delta = trace[0]["result"], trace[1]["result"]["value"]
            action = {"answer": f"合成设备 {summary['equipment']} 的 {summary['samples']} 条"
                      f"{summary['metric']}记录平均值为 {summary['mean']}。相对阈值 {limit} 的差值为"
                      f" {delta}。这是示例数据分析，不能据此判断真实设备故障。"}

        if isinstance(action.get("answer"), str) and action["answer"].strip():
            if not trace or not any("error" not in event["result"] for event in trace):
                raise ValueError("规划器必须先调用工具获取证据")
            answer = action["answer"]
            break
        tool, arguments = action.get("tool"), action.get("arguments", {})
        signature = json.dumps([tool, arguments], sort_keys=True, ensure_ascii=False)
        if signature in seen:
            status = "repeat_stopped"
            answer = "检测到重复的工具调用，已停止。可以根据下方已取得的结果继续分析。"
            break
        seen.add(signature)
        try:
            observation = invoke(tool, arguments)
        except ValueError as exc:
            observation = {"error": str(exc)}
        trace.append({"step": step + 1, "tool": tool, "arguments": arguments, "result": observation})
    else:
        status = "budget_exhausted"
        answer = "已达到工具步骤预算，展示目前取得的结果，尚未生成最终结论。"

    return {
        "summary": answer,
        "metrics": {"工具调用": len(trace), "步骤预算": MAX_STEPS, "执行状态": status},
        "sections": [
            {"title": "可检查的执行轨迹", "table": {
                "columns": ["步骤", "工具", "参数", "实际结果"],
                "rows": [[event["step"], event["tool"],
                          json.dumps(event["arguments"], ensure_ascii=False),
                          json.dumps(event["result"], ensure_ascii=False)] for event in trace]}},
            {"title": "数据与执行边界", "items": [
                "所有传感器记录都是本项目编写的合成数据。",
                "本地模式由确定性规划执行统计与计算，API 模式由模型逐步规划。",
                "仅运行白名单函数，参数经校验，并记录重复调用和预算耗尽状态。"]},
        ],
    }
