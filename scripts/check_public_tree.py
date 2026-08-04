from __future__ import annotations

import ast
import json
import re
import string
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISALLOWED_SUFFIXES = {
    ".cpk",
    ".dll",
    ".exe",
    ".iggy",
    ".iggytex",
    ".iggyted",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".ps1",
    ".rar",
    ".spec",
    ".zip",
    ".7z",
}
DISALLOWED_NAMES = {
    ".env",
    ".xv2promptfix-state.json",
    "AGENTS.md",
    "account.config",
    "agents.md",
    "download-metadata.json",
}
REQUIRED_FILES = {
    "README.md",
    "LICENSE",
    "PRIVACY.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "THIRD_PARTY_NOTICES.md",
    "xv2_prompt_fix/external_tools.json",
    "xv2_prompt_fix/i18n.py",
    "xv2_prompt_fix/languages.py",
    "xv2_prompt_fix/locales/ko.json",
}
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
PRIVATE_IP_RE = re.compile(
    r"(?<!\d)(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?!\d)"
)
README_KOREAN_START = "<!-- BEGIN ALLOWED KOREAN README SECTION -->"
README_KOREAN_END = "<!-- END ALLOWED KOREAN README SECTION -->"
SENSITIVE_MARKERS = (
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN RSA " + "PRIVATE KEY-----",
    "github" + "_pat_",
    "gh" + "p_",
    "xo" + "xb-",
    "AK" + "IA",
)
PATH_FIXTURE_ALLOWLIST = {"tests/test_privacy.py"}
NON_ENGLISH_DATA_ALLOWLIST = {"xv2_prompt_fix/locales/ko.json"}


def public_files() -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        path
        for line in result.stdout.splitlines()
        if line and (path := ROOT / line).exists()
    )


def _contains_non_ascii_letter_or_number(text: str) -> bool:
    return any(
        ord(character) > 127 and (character.isalpha() or character.isnumeric())
        for character in text
    )


def _check_english_only_text(relative_path: str, text: str) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()

    if relative_path in NON_ENGLISH_DATA_ALLOWLIST:
        return errors

    if relative_path != "README.md":
        for line_number, line in enumerate(lines, 1):
            if _contains_non_ascii_letter_or_number(line):
                errors.append(
                    f"Non-English text is not allowed: {relative_path}:{line_number}"
                )
        return errors

    start_lines = [
        index for index, line in enumerate(lines, 1) if line.strip() == README_KOREAN_START
    ]
    end_lines = [
        index for index, line in enumerate(lines, 1) if line.strip() == README_KOREAN_END
    ]
    if len(start_lines) != 1 or len(end_lines) != 1:
        errors.append(
            "README.md must contain exactly one explicitly marked Korean section."
        )
        return errors
    if start_lines[0] >= end_lines[0]:
        errors.append("The marked Korean README section has invalid boundaries.")
        return errors

    for line_number, line in enumerate(lines, 1):
        inside_allowed_section = start_lines[0] < line_number < end_lines[0]
        if _contains_non_ascii_letter_or_number(line) and not inside_allowed_section:
            errors.append(
                f"Non-English text is outside the allowed README section: README.md:{line_number}"
            )
    return errors


def _format_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _literal, field_name, _format_spec, _conversion in string.Formatter().parse(
        template
    ):
        if field_name is None:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        fields.add(root)
    return fields


def _translation_source_keys(files: list[Path]) -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    errors: list[str] = []
    for path in files:
        if path.suffix.casefold() != ".py":
            continue
        relative_path = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"Python source could not be parsed: {relative_path}: {exc}")
            continue
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
            ):
                continue
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                errors.append(
                    f"tr() must use exactly one literal English source string: "
                    f"{relative_path}:{node.lineno}"
                )
                continue
            source_text = node.args[0].value
            if not isinstance(source_text, str):
                errors.append(
                    f"tr() source must be a string: {relative_path}:{node.lineno}"
                )
                continue
            keys.add(source_text)
    return keys, errors


def main() -> int:
    errors: list[str] = []
    files = public_files()
    relative = {path.relative_to(ROOT).as_posix() for path in files}

    missing = sorted(REQUIRED_FILES - relative)
    if missing:
        errors.append(f"Required public files are missing: {missing}")

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if not path.exists():
            continue
        if path.name in DISALLOWED_NAMES or path.suffix.casefold() in DISALLOWED_SUFFIXES:
            errors.append(f"File is not allowed in the public repository: {rel}")
            continue
        data = path.read_bytes()
        if len(data) > 1024 * 1024:
            errors.append(f"Tracked file exceeds 1 MiB: {rel} ({len(data)} bytes)")
        if b"\0" in data[:8192]:
            errors.append(f"Tracked file appears to be binary: {rel}")
            continue
        text = data.decode("utf-8", errors="replace")
        errors.extend(_check_english_only_text(rel, text))
        if EMAIL_RE.search(text):
            errors.append(f"Email address pattern found: {rel}")
        if PRIVATE_IP_RE.search(text):
            errors.append(f"Private IP address pattern found: {rel}")
        for marker in SENSITIVE_MARKERS:
            if marker in text:
                errors.append(f"Sensitive marker found: {rel}: {marker}")
        if rel not in PATH_FIXTURE_ALLOWLIST and re.search(
            r"(?i)[A-Z]:\\Users\\[^%<\\\s]+", text
        ):
            errors.append(f"Absolute Windows user path pattern found: {rel}")

    manifest_path = ROOT / "xv2_prompt_fix" / "external_tools.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tools = manifest["tools"]
        for key, tool in tools.items():
            url = tool["download_url"]
            if not isinstance(url, str) or not url.startswith("https://"):
                errors.append(f"{key}: download URL must use HTTPS")
            for field in ("download_sha256", "executable_sha256"):
                value = tool[field]
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                    errors.append(f"{key}: invalid {field}")
            for field in ("download_size", "executable_size"):
                if not isinstance(tool[field], int) or tool[field] < 1:
                    errors.append(f"{key}: invalid {field}")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"External-tool manifest validation failed: {exc}")

    source_keys, source_errors = _translation_source_keys(files)
    errors.extend(source_errors)
    locale_path = ROOT / "xv2_prompt_fix" / "locales" / "ko.json"
    try:
        catalog = json.loads(locale_path.read_text(encoding="utf-8"))
        language_name = catalog["language_name"]
        translations = catalog["translations"]
        if not isinstance(language_name, str) or not language_name:
            errors.append("The Korean locale language name is invalid.")
        if not isinstance(translations, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in translations.items()
        ):
            errors.append("The Korean locale translation table is invalid.")
        else:
            translation_keys = set(translations)
            missing_translations = sorted(source_keys - translation_keys)
            unused_translations = sorted(translation_keys - source_keys)
            if missing_translations:
                errors.append(
                    f"Korean translations are missing for: {missing_translations}"
                )
            if unused_translations:
                errors.append(
                    f"Korean translations are unused: {unused_translations}"
                )
            for source_text, translated_text in translations.items():
                if _format_fields(source_text) != _format_fields(translated_text):
                    errors.append(
                        f"Korean translation placeholders differ: {source_text!r}"
                    )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Korean locale validation failed: {exc}")

    if any(path.parts and path.parts[0] == "src" for path in map(Path, relative)):
        errors.append("The source-only layout must not contain an unnecessary src directory.")

    if errors:
        print("Public tree check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Public tree check passed: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
