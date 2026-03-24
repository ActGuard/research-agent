#!/usr/bin/env python3
"""Send an HMAC-signed JSON-RPC request to the A2A endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "a2a_auth.json"
load_dotenv(CONFIG_PATH.parent.parent / ".env")


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text())
    secret = os.environ[config["secret_env"]].encode()

    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Tell me everything you know about accionlabs.com. Where are they from? Are they recruiting company? Why did their recruiter contact me?"}],
                    "messageId": str(uuid.uuid4()),
                }
            },
        }
    ).encode()

    host = "localhost:10000"
    path = "/"
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    content_sha256 = hashlib.sha256(payload).hexdigest()

    canonical = f"POST\n{host}\n{path}\n{timestamp}\n{nonce}\n{content_sha256}"
    signature = "v1=" + hmac.new(secret, canonical.encode(), hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Host": host,
        "X-A2A-Timestamp": timestamp,
        "X-A2A-Nonce": nonce,
        "X-A2A-Content-SHA256": content_sha256,
        "X-A2A-Signature": signature,
        "X-A2A-Key-Id": config["key_id"],
    }

    resp = httpx.post(f"http://{host}{path}", content=payload, headers=headers, timeout=360)
    print(f"Status: {resp.status_code}")

    console = Console()
    try:
        data = resp.json()
        result = data.get("result", {})
        # Collect text parts from artifacts or message
        text_parts: list[str] = []
        for artifact in result.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("kind") == "text":
                    text_parts.append(part["text"])
        if not text_parts:
            message = result.get("message", {})
            for part in message.get("parts", []):
                if part.get("kind") == "text":
                    text_parts.append(part["text"])
        if text_parts:
            for text in text_parts:
                console.print(Markdown(text))
        else:
            print(resp.text)
    except (json.JSONDecodeError, KeyError):
        print(resp.text)


if __name__ == "__main__":
    main()
