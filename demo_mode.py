"""Safe demonstration entry point that never calls an LLM or external service."""

from orchestrator import run_demo_mobile, run_demo_web


def main() -> None:
    web = run_demo_web()
    mobile = run_demo_mobile()
    print(f"Web demo passed: {web.passed}")
    print(f"Mobile demo passed: {mobile.passed}")
    print("Agent log:")
    for message in web.state.logs:
        print(f"- {message}")


if __name__ == "__main__":
    main()
