# Troubleshooting

## Changing the GUI locale

Select the Korean or English entry from the **Language** list in the upper-right corner. Locale changes are locked while an operation is in progress so that logs and dialog boxes do not mix locales.

## `python` or `py` cannot be found

Install Python 3.11 or newer for Windows from python.org, then open a new terminal.

```powershell
py -3 --version
```

## Tkinter error

Confirm that the Tcl/Tk component was included by the python.org installer. Tkinter may be unavailable in Microsoft Store or minimal Python distributions.

## The game directory cannot be found

Select the root directory that contains both of the following files:

```text
bin\DBXV2.exe
cpk\data1.cpk
```

## The installed Steam language cannot be read

The application reads the final `language` value from the Steam app manifest associated with the selected installation. Confirm that Steam has finished writing the manifest and that the selected game directory belongs to a normal Steam library.

A local reference CPK replaces only the source-acquisition method; the installed-language value is still read from the selected Steam installation.

## The Steam language cannot be mapped to a resource code

A patch target is selected only when the Steam language identifier maps to exactly one complete resource code shared by the current and reference CPK files.

The error message lists:

- The Steam language value
- Candidate codes checked
- Complete resource codes shared by both CPK files

No file is modified when there is no match. For a new identifier or suffix convention, collect the redacted log and synthetic filename examples, then report the required mapping change.

## More than one resource code matches

The application refuses to guess when multiple candidate suffixes are present. Confirm which suffix belongs to the installed language in the actual game, then update the mapping with a regression test that makes the result unambiguous.

## No complete language resource set is found

The current and reference CPK files must both contain all three paths for the same code:

```text
data/system/iggy/sysfont01_ab_<language-code>.iggy
data/system/iggy/sysfont01_ab_<language-code>.iggytex
data/system/iggy/sysfont01_ab_<language-code>.iggyted
```

The code is unavailable when one file is missing, duplicated, or present in only one CPK. Confirm that the selected reference CPK came from the expected manifest.

## The resources do not match the validated replacement pattern

The application expects `.iggy` and `.iggyted` to differ together while `.iggytex` remains identical. It stops without modifying the original when:

- Only `.iggy` differs
- Only `.iggyted` differs
- `.iggytex` also differs
- All three files use another unvalidated combination

This usually means the current or reference CPK came from an unexpected build, another mod changed the archive, or the problem differs from the validated fault pattern.

## The `.iggyted` raw transplant is rejected

Both entries must be CRILAYLA-compressed. The raw compressed reference entry must also fit in the current entry's allocated storage. A larger entry or unsupported storage layout is rejected to preserve archive offsets and total size.

## Steam QR authentication fails

- Confirm that the sign-in request was approved in the Steam mobile app.
- Confirm that the Steam account owns the game.
- Confirm that access to the historical manifest has not been blocked.
- If authentication is unwanted or continues to fail, use a local reference CPK.

## External-tool integrity validation fails

The application refuses to run a tool when its download size, SHA-256, or PE architecture differs from the pinned value. Delete the tool cache and try again.

```text
%LOCALAPPDATA%\XV2PromptFix\tools
```

If validation still fails after a fresh download, the upstream file may have changed. Do not edit the pinned hash arbitrarily; report the problem in an Issue.

## Insufficient disk space

A working CPK is created in addition to the current CPK. The default configuration requires approximately 6–7 GiB of free space, or approximately 9–10 GiB when the reference source is retained.

## Unknown Steam build

An official update may already have fixed the problem or changed the CPK structure. First verify the problem in the game, then follow the validation procedure in [COMPATIBILITY.md](COMPATIBILITY.md).

## Restoration is refused

If the current CPK differs from the patched copy recorded at application time, a Steam update or another mod has changed the file. Forced restoration could overwrite a newer official file with an older original. Steam's integrity check is the safe default.

## Sharing logs

Log location:

```text
%LOCALAPPDATA%\XV2PromptFix\logs
```

Paths are redacted automatically, but before sharing a log, confirm that it contains no Windows user name, Steam account information, QR code, or personal path. Do not attach a CPK, extracted resource, or raw state file.
