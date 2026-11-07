import json
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from apps.assistant.screens import SCREEN_KEYS, SCREENS

LOCALES = Path(settings.BASE_DIR).parent / "frontend" / "src" / "i18n" / "locales"


def label(data: dict[str, Any], key: str) -> Any:
    for part in key.split("."):
        data = data[part]
    return data


@pytest.mark.parametrize("language", sorted(SCREENS))
def test_screen_names_match_what_the_app_shows(language: str) -> None:
    data = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    assert SCREENS[language] == tuple(label(data, key) for key in SCREEN_KEYS)


def test_every_app_language_has_screen_names() -> None:
    assert sorted(SCREENS) == sorted(path.stem for path in LOCALES.glob("*.json"))
