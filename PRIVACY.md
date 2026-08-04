# Privacy

## Summary

This application does not use an operator-controlled server, telemetry, analytics SDK, or automatic upload feature. No user information is sent automatically to the project maintainers.

## Local information the application reads

- Steam library locations
- The Dragon Ball Xenoverse 2 installation path
- The build ID and installed language from the Steam app manifest
- The current `data1.cpk` and the reference `data1.cpk` selected by the user
- Internal file-path listings from both CPK files
- SHA-256 values of the selected target resources
- Whether the game process is running
- State and backup files created by the application

The app-manifest language value and internal CPK paths are used locally to select exactly one matching input-prompt resource code. Extracted game files, hashes, manifest contents, and file listings are not sent anywhere.

## Information the application stores

- Execution logs in `%LOCALAPPDATA%\XV2PromptFix\logs`
- The external-tool cache and integrity metadata in `%LOCALAPPDATA%\XV2PromptFix\tools`
- The original backup and state file in the game's `cpk` directory
- A reference CPK when the user chooses to keep it

State files and tool metadata do not store the user's home path or the absolute game-installation path. A state file may contain the Steam build ID, selected resource-path hashes, a relative backup filename, and external-tool hashes. Logs replace known user-profile, AppData, and temporary-directory paths with environment-variable notation and retain no more than 20 files or 30 days of history.

Runtime files use generic names such as `.xv2promptfix-state.json` and `data1.cpk.xv2promptfix-backup-*`.

## Network communication

The application has no operator-controlled server. The only network communication is:

- Downloading pinned external tools from their GitHub upstream sources
- DepotDownloader downloading a specified depot manifest from Steam servers

Selecting a local reference CPK avoids both Steam authentication and DepotDownloader. The installed language is still read from the local Steam app manifest.

## Steam QR authentication

The application itself does not request or store a Steam password. The third-party DepotDownloader program handles the Steam QR sign-in screen and session.

The reviewed DepotDownloader 3.4.0 implementation may store the Steam account name, refresh token, and GuardData in Windows .NET Isolated Storage after successful QR authentication. This application neither reads nor uploads that storage. It also does not delete the data automatically because doing so could disrupt other DepotDownloader usage.

When Steam automatic download is selected, the application presents this information together with the patch scope on every run. Users who do not want session data stored should use a local reference CPK.

## Sharing logs or Issues

Do not post the following material in a public Issue:

- `data1.cpk` or a backup CPK
- Extracted `.iggy`, `.iggytex`, or `.iggyted` files
- A Steam QR code screen
- A Steam account name, refresh token, or `account.config`
- Unredacted Windows paths
- A raw state file

Logs are redacted automatically, but error messages or user-supplied descriptions may still contain personal information. Before sharing, check again for the Windows user name, Steam library paths, and personal directory names.

## Deleting local data

After deleting the application source directory, delete the following directory separately to remove logs and the tool cache:

```text
%LOCALAPPDATA%\XV2PromptFix
```

Before deleting backups and state files from the game's `cpk` directory, confirm whether the original CPK must be restored. Revoke Steam authentication sessions from the Steam account security settings.
