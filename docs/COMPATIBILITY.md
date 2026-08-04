# Compatibility

## Current validation scope

| Item | Value |
|---|---|
| Application version | `0.4.0` |
| Game platform | Steam Windows |
| GUI locales | `ko`, `en` |
| Known affected build ID | `23988437` |
| Reference depot manifest | `7238901667150908628` |
| Steam App ID | `454650` |
| Depot ID | `454651` |
| Actual-game prompt rendering | Passed on the validated Steam Windows installation |
| Validation date | 2026-08-04 |

The patched input prompts were tested in the actual Windows game for this validated installation, and no rendering issue was observed. This result is scoped to the validated installation and does not imply that every language-resource mapping has been tested.

The implementation is language-neutral, but each Steam-language identifier and CPK resource-code combination still requires validation in the actual game. A generic mapping capability does not imply that every language has been tested.

## Language-resource detection rules

The application requires one complete resource set with the following paths in both the current and reference CPK files:

```text
data/system/iggy/sysfont01_ab_<language-code>.iggy
data/system/iggy/sysfont01_ab_<language-code>.iggytex
data/system/iggy/sysfont01_ab_<language-code>.iggyted
```

Detection conditions:

1. Exactly one file of each type must exist for the same code.
2. The complete set must exist in both the current and reference CPK files.
3. Unsuffixed default resources and known English codes (`en`, `eng`, `english`, `us`, `uk`) are excluded.
4. Known Japanese codes (`ja`, `jp`, `jpn`, `japanese`) are excluded.
5. Resource-code matching is case-insensitive and treats hyphens and underscores as equivalent for comparison.

## Steam-language mapping

The installed language is read from the Steam app manifest. The application then compares that identifier with the complete resource codes shared by both CPK files.

- An exact identifier-to-code match is accepted.
- Common Steam identifiers can expand to multiple candidate suffixes, such as `french → fr` or `brazilian → pt_br / br`.
- A target is accepted only when exactly one candidate exists in the shared resource-code set.
- No file is modified when there is no match or more than one match.

This design prevents a fallback to an unrelated language when a new or unexpected identifier is encountered.

## Validated replacement relationship

For the selected language code, the source and current hashes must have this relationship:

| Resource | Required relationship | Action |
|---|---|---|
| `.iggy` | Different | Replace through CriPakTools |
| `.iggytex` | Identical | Keep the current entry |
| `.iggyted` | Different and CRILAYLA-compressed in both CPK files | Transplant the raw compressed entry |

The `.iggy` and `.iggyted` files must change together. Any other combination is rejected because it does not match the validated fault pattern.

## Procedure for validating a new game build or language

1. Confirm that the input-prompt problem is reproducible.
2. Record the Steam manifest language value.
3. List complete three-file resource sets in the current and reference CPK files.
4. Confirm that the language value resolves to exactly one shared resource code.
5. Verify that `.iggy` and `.iggyted` differ while `.iggytex` is identical.
6. Confirm that both `.iggyted` entries are CRILAYLA-compressed and that the reference raw entry fits in the current entry's allocated storage.
7. Verify the CPK `ContentOffset`, `ContentSize`, alignment, TOC offsets, and complete entry set.
8. Re-extract the three target files and compare their SHA-256 values with the expected mixed result.
9. Test prompt rendering in the actual Windows game with offline mode enabled and EAC disabled.
10. Verify original-file restoration.
11. If an official patch has fixed the problem, do not add that build to the target list.

## Unsupported scope

- Unsuffixed, English, or Japanese resources
- A Steam language that does not map uniquely to a shared resource code
- Resource sets missing `.iggy`, `.iggytex`, or `.iggyted`
- Hash relationships other than the validated two-file replacement pattern
- Uncompressed or structurally unsupported `.iggyted` entries
- Console and Microsoft Store editions
- Online or EAC-enabled environments
- Arbitrary modded CPK combinations
- Future CPK structures that fail structural validation

Allowing an unknown build is an experimental option and does not imply compatibility.
