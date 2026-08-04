from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .errors import FixError
from .i18n import tr

_RESOURCE_RE = re.compile(
    r"^data/system/iggy/sysfont01_ab(?:_(?P<code>[a-z0-9_-]+))?"
    r"\.(?P<kind>iggy|iggytex|iggyted)$",
    re.IGNORECASE,
)

_EXCLUDED_CODES = frozenset(
    {
        "",
        "en",
        "eng",
        "english",
        "us",
        "uk",
        "ja",
        "jp",
        "jpn",
        "japanese",
    }
)

# Steam language identifiers do not always match the resource suffixes used by
# the game. Candidates are accepted only when exactly one of them exists as a
# complete resource set in both the current and reference CPK files.
_STEAM_LANGUAGE_CODE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "arabic": ("ar",),
    "brazilian": ("pt_br", "br"),
    "bulgarian": ("bg",),
    "czech": ("cs", "cz"),
    "danish": ("da", "dk"),
    "dutch": ("nl",),
    "finnish": ("fi",),
    "french": ("fr",),
    "german": ("de", "ge"),
    "greek": ("el", "gr"),
    "hungarian": ("hu",),
    "indonesian": ("id",),
    "italian": ("it",),
    "koreana": ("kr", "ko"),
    "latam": ("es_419", "es_la", "latam", "la"),
    "norwegian": ("no", "nb"),
    "polish": ("pl",),
    "portuguese": ("pt",),
    "romanian": ("ro",),
    "russian": ("ru",),
    "schinese": ("zh_cn", "cn", "chs"),
    "spanish": ("es", "sp"),
    "swedish": ("sv", "se"),
    "tchinese": ("zh_tw", "tw", "cht"),
    "thai": ("th",),
    "turkish": ("tr",),
    "ukrainian": ("ua",),
    "vietnamese": ("vi",),
}


@dataclass(frozen=True, slots=True)
class LanguageResourceSet:
    code: str
    iggy_path: str
    iggytex_path: str
    iggyted_path: str


@dataclass(frozen=True, slots=True)
class PatchTarget:
    language_code: str
    source_path: str
    current_path: str


def _normalize_entry(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./")


def _normalize_code(value: str) -> str:
    return value.strip().casefold().replace("-", "_")


def discover_language_resource_sets(
    entries: Iterable[str],
) -> dict[str, LanguageResourceSet]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for raw_entry in entries:
        entry = _normalize_entry(raw_entry)
        match = _RESOURCE_RE.fullmatch(entry)
        if not match:
            continue
        code = _normalize_code(match.group("code") or "")
        kind = match.group("kind").casefold()
        grouped.setdefault(code, {}).setdefault(kind, []).append(entry)

    resource_sets: dict[str, LanguageResourceSet] = {}
    for code, by_kind in grouped.items():
        if code in _EXCLUDED_CODES:
            continue
        iggy = by_kind.get("iggy", [])
        iggytex = by_kind.get("iggytex", [])
        iggyted = by_kind.get("iggyted", [])
        if len(iggy) != 1 or len(iggytex) != 1 or len(iggyted) != 1:
            continue
        resource_sets[code] = LanguageResourceSet(
            code=code,
            iggy_path=iggy[0],
            iggytex_path=iggytex[0],
            iggyted_path=iggyted[0],
        )
    return resource_sets


def resolve_patch_targets(
    source_entries: Iterable[str],
    current_entries: Iterable[str],
    *,
    language_code: str,
) -> tuple[PatchTarget, ...]:
    source_sets = discover_language_resource_sets(source_entries)
    current_sets = discover_language_resource_sets(current_entries)
    code = _normalize_code(language_code)
    if not code or code in _EXCLUDED_CODES:
        raise FixError(
            tr(
                "The patch-target language code is invalid: {code}",
                code=language_code or tr("[missing]"),
            )
        )
    if code not in source_sets or code not in current_sets:
        raise FixError(
            tr(
                "A complete input-prompt resource set for the installed Steam language was not found in both the current and reference CPK files.\nLanguage code: {code}",
                code=code,
            )
        )

    source_set = source_sets[code]
    current_set = current_sets[code]
    return (
        PatchTarget(
            language_code=code,
            source_path=source_set.iggy_path,
            current_path=current_set.iggy_path,
        ),
        PatchTarget(
            language_code=code,
            source_path=source_set.iggytex_path,
            current_path=current_set.iggytex_path,
        ),
        PatchTarget(
            language_code=code,
            source_path=source_set.iggyted_path,
            current_path=current_set.iggyted_path,
        ),
    )


def resource_code_for_steam_language(
    steam_language: str | None,
    *,
    available_codes: Iterable[str],
) -> str:
    normalized_language = _normalize_code(steam_language or "")
    normalized_available: dict[str, list[str]] = {}
    for raw_code in available_codes:
        code = raw_code.strip().casefold()
        if not code:
            continue
        normalized_available.setdefault(_normalize_code(code), []).append(code)

    aliases = _STEAM_LANGUAGE_CODE_CANDIDATES.get(normalized_language, ())
    candidate_keys = tuple(
        dict.fromkeys(
            _normalize_code(candidate)
            for candidate in (normalized_language, *aliases)
            if candidate
        )
    )
    matches = tuple(
        code
        for key in candidate_keys
        for code in normalized_available.get(key, ())
    )
    unique_matches = tuple(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]

    available_text = ", ".join(
        sorted(code for codes in normalized_available.values() for code in codes)
    )
    candidate_text = ", ".join(candidate_keys)
    if len(unique_matches) > 1:
        raise FixError(
            tr(
                "More than one CPK resource code matches the installed Steam language, so a safe target cannot be selected.\nSteam language value: {language}\nMatching codes: {matches}",
                language=normalized_language or tr("[unknown]"),
                matches=", ".join(unique_matches),
            )
        )

    raise FixError(
        tr(
            "The installed Steam language could not be mapped to a resource code shared by the current and reference CPK files. Other language resources were not modified.\nSteam language value: {language}\nCandidate codes checked: {candidates}\nCommon resource codes: {available}",
            language=normalized_language or tr("[unknown]"),
            candidates=candidate_text or tr("[none]"),
            available=available_text or tr("[none]"),
        )
    )


def language_codes(targets: Iterable[PatchTarget]) -> tuple[str, ...]:
    return tuple(sorted({target.language_code for target in targets}))
