# Third-Party Notices

This repository and its GitHub releases do not include third-party executables, third-party source code, or game data. The tools below are downloaded on the user's PC from pinned official upstream locations, and their fixed sizes and SHA-256 values are verified before execution.

The integrity checks confirm the exact pinned bytes, PE header signature, and expected architecture. They do not establish an independent safety verdict or publisher identity. Neither currently pinned executable is Authenticode-signed.

## DepotDownloader 3.4.0

- Purpose: Download the user-owned `cpk/data1.cpk` from a specified Steam depot manifest
- Upstream: https://github.com/SteamRE/DepotDownloader
- Download: The upstream 3.4.0 Windows x64 release asset
- License: GPL-2.0
- Included in this project: No

DepotDownloader runs as a separate process. Its use and distribution are governed by its upstream license. Its source code and full license text are available from the upstream repository.

After Steam QR authentication, DepotDownloader may store the account name and session data in Windows local storage. See `PRIVACY.md` for details.

## CriPakTools

- Purpose: Read CPK entry listings, expose paths for automatic language-resource detection, extract target files, and create patched copies
- Upstream: https://github.com/esperknight/CriPakTools
- Pinned revision: `0dbd2229f7c3b519c67d65e89055fd4e610d6dca`
- Included in this project: No
- License status: `NOASSERTION`

No explicit software-license file was found at the root of the reviewed pinned revision. This project's MIT License does not apply to CriPakTools, and this project grants no separate right to copy, distribute, or modify CriPakTools. The executable is downloaded directly to the user's PC from the pinned upstream revision.

## Game data and trademarks

This project does not distribute Dragon Ball Xenoverse 2 CPK files, executables, extracted resources, images, or other copyrighted materials. Users must use a Steam installation and account to which they have lawful access.

Valve, Steam, Bandai Namco Entertainment, Dimps, and all other product names and trademarks belong to their respective owners.
