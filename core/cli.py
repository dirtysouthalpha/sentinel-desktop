"""CLI mode for Sentinel Desktop."""
from core.legacy_engine import CommandEngine
from core.legacy_brain import BrainClient
from core.config_legacy import VERSION


def cli_main():
    print(f"Sentinel Desktop v{VERSION} - CLI Mode")
    print("Type 'exit' to quit.\n")

    brain = BrainClient()
    engine = CommandEngine(brain)

    while True:
        try:
            text = input("> ").strip()
            if not text:
                continue
            if text.lower() in ["exit", "quit", "q"]:
                print("Goodbye.")
                break

            result = engine.execute(text)
            if result.success:
                print(f"\n{result.message}\n")
            else:
                print(f"\n[!] {result.message}\n")
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
