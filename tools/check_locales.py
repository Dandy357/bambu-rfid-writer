from __future__ import annotations

import json
import string
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "bambu_rfid_diag" / "locales"
REQUIRED = ("cs", "en")


def placeholders(template: str) -> Counter[str]:
    formatter = string.Formatter()
    return Counter(
        field
        for _literal, field, _format_spec, _conversion in formatter.parse(template)
        if field
    )


def load_catalog(locale: str) -> dict[str, str]:
    path = LOCALES / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def main() -> int:
    catalogs = {locale: load_catalog(locale) for locale in REQUIRED}
    reference = catalogs[REQUIRED[0]]
    errors: list[str] = []

    for locale, catalog in catalogs.items():
        missing = sorted(set(reference) - set(catalog))
        extra = sorted(set(catalog) - set(reference))
        if missing:
            errors.append(f"{locale}: missing keys: {', '.join(missing)}")
        if extra:
            errors.append(f"{locale}: unexpected keys: {', '.join(extra)}")

    for key in sorted(set.intersection(*(set(catalog) for catalog in catalogs.values()))):
        expected = placeholders(reference[key])
        for locale, catalog in catalogs.items():
            actual = placeholders(catalog[key])
            if actual != expected:
                errors.append(
                    f"{locale}:{key}: placeholders {dict(actual)} != {dict(expected)}"
                )

    if errors:
        print("Locale validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Locale validation passed: {len(reference)} keys in "
        + ", ".join(REQUIRED)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
