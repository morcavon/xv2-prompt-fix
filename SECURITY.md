# Security Policy

## Supported Versions

| Version | Security support |
|---|---|
| 0.4.x | Supported |

## Reporting a Vulnerability

Use GitHub's **Private vulnerability reporting** feature. Do not first publish vulnerability details or an actionable reproduction procedure in a public Issue.

Include as much of the following information as possible:

- The affected version and commit
- Windows and Python versions
- Reproduction conditions
- The affected language-resource code or filename pattern
- The expected impact
- A redacted log or minimal reproduction code

Do not attach the following files or information:

- Game CPK or backup CPK files
- Extracted game resources
- Steam QR codes
- Steam account names, session tokens, or `account.config`
- Logs that still contain personal paths

A vulnerability in an external tool may also need to be reported to that tool's upstream project. Report it to this repository when the cause is this project's download verification, dynamic language detection, invocation method, or integration code.
