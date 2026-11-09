"""CPU demos and explicit opt-in API calls for the portfolio projects."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request as web_request
from werkzeug.exceptions import RequestEntityTooLarge


class ModelError(RuntimeError):
    pass


def read_settings(directory):
    settings = {}
    env_file = Path(directory) / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip().strip("\"'")
    settings.update(os.environ)
    return settings


class ModelClient:
    def __init__(self, directory, enabled=False):
        self.settings = read_settings(directory)
        self.enabled = enabled
        self.calls = []
        self.attempts = 0
        if enabled:
            for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
                if not self.settings.get(key):
                    raise ModelError(f"请在项目 .env 文件中配置 {key}，或选择本地演示模式。")

    def complete(self, system, user, max_tokens=700, model=None, temperature=0.5):
        if not self.enabled:
            raise ModelError("当前处于本地演示模式，尚未启用云端模型。")
        if self.attempts >= 6:
            raise ModelError("本次运行已达到 6 次 API 调用上限。")
        base_url = self.settings["LLM_BASE_URL"].rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ModelError("远程 API 地址请使用 HTTPS。")
        selected_model = model or self.settings["LLM_MODEL"]
        body = {
            "model": selected_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": min(max(int(max_tokens), 32), 2000),
            "temperature": temperature,
            "stream": False,
        }
        if parsed.hostname == "api.deepseek.com":
            body["thinking"] = {"type": "disabled"}
        api_request = request.Request(
            base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.settings["LLM_API_KEY"], "Content-Type": "application/json"},
            method="POST",
        )
        self.attempts += 1
        start = time.perf_counter()
        try:
            with request.urlopen(api_request, timeout=45) as response:
                data = json.load(response)
        except error.HTTPError as exc:
            raise ModelError(f"模型服务返回 HTTP {exc.code}。请检查账号、余额和模型名称。") from exc
        except (error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ModelError("模型请求未完成。请检查网络与 API 配置后重试。") from exc
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty response")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelError("模型服务未返回可用的文本回答。") from exc
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        self.calls.append({"model": selected_model, "latency_ms": round((time.perf_counter() - start) * 1000), "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")})
        return content


def create_app(spec, runner, directory):
    directory = Path(directory)
    app = Flask(spec["slug"], template_folder=str(directory / "templates"), static_folder=str(directory / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 128 * 1024

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(error):
        return jsonify(error="请求体过大，请缩短输入后重试。"), 413

    @app.get("/")
    def index():
        return render_template("lab.html", spec={**spec, "number": directory.name[:2]})

    @app.post("/api/run")
    def run_project():
        payload = web_request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            return jsonify(error="请提交包含 text 字符串的 JSON。"), 400
        payload["text"] = payload["text"].strip()
        if not payload["text"]:
            return jsonify(error="请输入问题或实验文本。"), 400
        if len(payload["text"]) > 20000:
            return jsonify(error="单次输入请控制在 20,000 个字符以内。"), 400
        mode = payload.get("mode", "demo")
        if mode not in ("demo", "live"):
            return jsonify(error="模式必须为 demo 或 live。"), 400
        payload["mode"] = mode
        start = time.perf_counter()
        client = None

        def execution_info():
            return {"mode": mode, "duration_ms": round((time.perf_counter() - start) * 1000, 2), "api_attempts": client.attempts if client else 0, "api_calls": client.calls if client else []}

        try:
            client = ModelClient(directory, enabled=mode == "live")
            result = runner(payload, client)
            result["execution"] = execution_info()
            return jsonify(result)
        except (ModelError, ValueError) as exc:
            return jsonify(error=str(exc), execution=execution_info()), 400
        except Exception:
            app.logger.exception("Project execution failed")
            return jsonify(error="运行失败，请查看 PyCharm 运行窗口中的错误信息。", execution=execution_info()), 500

    return app
