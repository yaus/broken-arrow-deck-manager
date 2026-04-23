import importlib.util
import sys
from pathlib import Path


def main() -> int:
    script_path = Path(__file__).with_suffix(".py")
    spec = importlib.util.spec_from_file_location("broken_arrow_deck_manager", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
