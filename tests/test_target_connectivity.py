"""Make one connectivity request to the instructor's OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dotenv import load_dotenv

from providers.llm_config import TARGET_MODEL, TARGET_URL


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def main() -> int:
    load_dotenv()
    endpoint = os.getenv("TARGET_URL", TARGET_URL).strip()
    model = os.getenv("TARGET_MODEL", TARGET_MODEL).strip()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: TARGET_OK"}],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = build_opener(NoRedirectHandler())

    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if 300 <= error.code < 400:
            print("TARGET API: ERROR")
            return 1
        status = error.code
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
    except (TimeoutError, socket.timeout):
        print("TARGET API: TIMEOUT")
        return 1
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            print("TARGET API: TIMEOUT")
        else:
            print("TARGET API: ERROR")
        return 1
    except (OSError, json.JSONDecodeError):
        print("TARGET API: ERROR")
        return 1

    try:
        response_text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        response_text = ""

    print(f"Model: {model}")
    print(f"TARGET API: HTTP {status}")
    print(f"Response: {response_text}")
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
