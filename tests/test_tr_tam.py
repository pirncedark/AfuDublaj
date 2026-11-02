"""Test completeness and validity of Turkish (tr.json), German (de.json) and Russian (ru.json) locales.

Verifies:
1. Every static t('...') call in src/afudublaj/**/*.py exists in tr.json, de.json, and ru.json.
2. Every key in tr.json has a non-empty translation.
3. Every translation in tr.json is different from its key, unless the key is a recognized
   proper noun, brand, or technical acronym (WHITELIST_SAME).
4. Missing keys produce red/clear failure output with the exact missing key names.
"""
import ast
import json
from pathlib import Path
import pytest

from afudublaj.i18n import LOCALES_DIR

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'afudublaj'

# Technical acronyms, brand names or untranslated UI constants allowed to match their key in tr.json
WHITELIST_SAME = {
    'Normal',     # TTS voice speed label / common Turkish usage
    'OCR ms',     # Technical acronym / metric
    'Overlay',    # UI window technical term widely adopted in Turkish gaming
    'Plan:',      # Plan (Turkish and English identical spelling)
    'Pro',        # Brand/edition name
    'Pro plan',   # Subscription plan tier name
}


def collect_source_t_strings() -> dict[str, list[str]]:
    """Extract all static string literals passed to t('...') across src/afudublaj."""
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob('*.py')):
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except Exception:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 't'
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                key = node.args[0].value
                found.setdefault(key, []).append(f"{rel}:{node.lineno}")
    return found


def test_tr_has_all_source_strings():
    """Every static t('...') string in src/afudublaj must exist in tr.json."""
    tr_path = LOCALES_DIR / 'tr.json'
    assert tr_path.exists(), "tr.json does not exist"
    tr_data = json.loads(tr_path.read_text(encoding='utf-8'))

    source_strings = collect_source_t_strings()
    missing = {k: locs for k, locs in source_strings.items() if k not in tr_data}

    if missing:
        lines = [f"\n[FAIL] Missing {len(missing)} keys in tr.json:"]
        for k, locs in sorted(missing.items()):
            lines.append(f"  - Key: {k!r} (used at: {', '.join(locs)})")
        pytest.fail("\n".join(lines))


def test_de_and_ru_have_all_source_strings():
    """Every static t('...') string in src/afudublaj must exist in de.json and ru.json."""
    source_strings = collect_source_t_strings()

    for loc in ('de', 'ru'):
        path = LOCALES_DIR / f'{loc}.json'
        assert path.exists(), f"{loc}.json does not exist"
        data = json.loads(path.read_text(encoding='utf-8'))
        missing = {k: locs for k, locs in source_strings.items() if k not in data}
        if missing:
            lines = [f"\n[FAIL] Missing {len(missing)} keys in {loc}.json:"]
            for k, locs in sorted(missing.items()):
                lines.append(f"  - Key: {k!r} (used at: {', '.join(locs)})")
            pytest.fail("\n".join(lines))


def test_tr_translations_are_non_empty_and_translated():
    """Every translation in tr.json must be non-empty and translated (different from key unless whitelisted)."""
    tr_path = LOCALES_DIR / 'tr.json'
    tr_data = json.loads(tr_path.read_text(encoding='utf-8'))

    empty_keys = []
    untranslated_keys = []

    for k, v in tr_data.items():
        if k.startswith('_meta'):
            continue
        if not v or not v.strip():
            empty_keys.append(k)
        elif k == v and k not in WHITELIST_SAME:
            untranslated_keys.append(k)

    failures = []
    if empty_keys:
        failures.append(f"Empty translations in tr.json ({len(empty_keys)}):\n  " + "\n  ".join(empty_keys))
    if untranslated_keys:
        failures.append(f"Untranslated (value == key) in tr.json ({len(untranslated_keys)}):\n  " + "\n  ".join(untranslated_keys))

    if failures:
        pytest.fail("\n".join(failures))


def test_de_and_ru_translations_are_non_empty():
    """de.json and ru.json values must be non-empty."""
    for loc in ('de', 'ru'):
        path = LOCALES_DIR / f'{loc}.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        empty = [k for k, v in data.items() if not k.startswith('_meta') and (not v or not v.strip())]
        if empty:
            pytest.fail(f"Empty translations in {loc}.json ({len(empty)}):\n  " + "\n  ".join(empty))
