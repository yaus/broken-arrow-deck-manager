import json
from pathlib import Path


class LocaleManager:
    def __init__(
        self,
        locales_root: Path,
        resource_root: Path,
        default_language: str = "en",
    ) -> None:
        self._locales_root = locales_root
        self._resource_root = resource_root
        self.current_language = default_language
        self.languages: dict[str, str] = {}
        self.text: dict[str, dict[str, str]] = {}

    def load(self) -> None:
        locales_root = self._locales_root
        if not locales_root.exists():
            bundled_locales_root = self._resource_root / "locales"
            if bundled_locales_root.exists():
                locales_root = bundled_locales_root

        loaded_languages: dict[str, str] = {}
        loaded_text: dict[str, dict[str, str]] = {}

        for path in sorted(locales_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            code = payload.get("code")
            label = payload.get("label")
            strings = payload.get("strings")
            if not isinstance(code, str) or not code:
                continue
            if not isinstance(label, str) or not label:
                continue
            if not isinstance(strings, dict):
                continue

            normalized_strings = {str(key): str(value) for key, value in strings.items()}
            loaded_languages[code] = label
            loaded_text[code] = normalized_strings

        if "en" not in loaded_text:
            raise RuntimeError("Missing required locale file: en.json")

        self.languages = loaded_languages
        self.text = loaded_text

    def translate(self, key: str, **values: object) -> str:
        english = self.text["en"]
        text = self.text.get(self.current_language, english).get(key, english.get(key, key))
        return text.format(**values) if values else text

    def set_language(self, language: str) -> None:
        if language in self.languages:
            self.current_language = language
