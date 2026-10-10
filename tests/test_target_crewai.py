"""One minimal CrewAI/LiteLLM call against the instructor endpoint."""

from __future__ import annotations

import socket

from providers.llm_config import TARGET_MODEL, get_default_llm


def _is_timeout(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, (TimeoutError, socket.timeout)):
            return True
        if "timeout" in type(current).__name__.lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def main() -> int:
    llm = get_default_llm()
    llm.timeout = 60
    llm.stream = False
    llm.max_tokens = 16
    llm.additional_params = {**llm.additional_params, "num_retries": 0}

    print(f"MODEL: {TARGET_MODEL}")
    print(f"BASE_URL: {llm.base_url}")
    try:
        response = llm.call(
            "Reply with exactly: TARGET_OK",
            tools=None,
            response_model=None,
        )
    except Exception as error:
        print("CREWAI TARGET: TIMEOUT" if _is_timeout(error) else "CREWAI TARGET: ERROR")
        return 1

    response_text = str(response)
    if llm.api_key:
        response_text = response_text.replace(llm.api_key, "[REDACTED]")
    print("CREWAI TARGET: OK")
    print(f"RESPONSE: {response_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
