# Contributing

Thank you for contributing. This project is a source-only tool that does not include game files or third-party binaries in the repository.

## Development environment

- Windows 10/11
- Python 3.11 or newer
- Prefer the Python standard library

```powershell
py -3 -m compileall -q xv2_prompt_fix tests scripts
py -3 -m unittest discover -s tests -v
py -3 scripts\check_public_tree.py
```

## Change guidelines

- Do not commit actual game CPK files, extracted resources, executables, logs, or account data.
- Before adding a Python dependency, explain why it is needed and assess its supply-chain impact.
- Do not attach third-party executables to the repository or to a release.
- When changing an external tool version or hash, download it again from the official upstream source and review its size, SHA-256, and license.
- Changes that weaken patching or restoration safeguards require failure-path and rollback tests.
- When changing language detection or mapping, add tests for English and Japanese exclusions, incomplete three-file resource sets, exact and alias matches, no match, multiple matches, and the intersection between the current and reference CPK files.
- Write Python comments and docstrings in English.
- Write all source code, comments, docstrings, tests, configuration, issue templates, and documentation in English. The Korean locale data in `xv2_prompt_fix/locales/ko.json` and the explicitly marked Korean section in `README.md` are the only exceptions.
- Keep English UI text in Python source and add matching Korean translations to `xv2_prompt_fix/locales/ko.json`. Use `tr(text, **values)` for lookup and named-value formatting.
- Test that logs never record absolute user paths or credentials.
- Do not use `assert` for runtime validation.
- Do not introduce `shell=True`, `os.system`, `eval`, `exec`, or `pickle`.

## License

By submitting project code in a pull request, you agree to provide it under the repository's MIT License. If you use or modify code from another source, identify the source and its license. Do not import code that has no explicit license.

## Reporting bugs

Use the Issue template and redact paths and personal information. Do not attach game files. When possible, provide the detected language code and either a synthetic fixture or minimal reproduction steps.
