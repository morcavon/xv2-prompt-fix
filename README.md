<!-- BEGIN ALLOWED KOREAN README SECTION -->

# XV2 입력 프롬프트 수정 도구

Dragon Ball Xenoverse 2 Steam판의 특정 업데이트에서 일부 언어의 컨트롤러·키보드 버튼 이미지가 `<IMG UNKNOWN>` 등으로 표시되는 문제를 우회하는 **비공식 Windows Python 도구**입니다.

> 이 저장소는 Python 소스만 제공합니다. 실행 파일, 게임 파일, 추출한 게임 리소스 및 제3자 실행 파일은 포함하거나 배포하지 않습니다.

## 핵심 동작

- Steam 앱 매니페스트에서 현재 설치 언어를 읽습니다.
- 현재 `data1.cpk`와 정상 버전 `data1.cpk`에서 다음 세 파일이 모두 존재하는 언어 리소스 세트를 찾습니다.

```text
data/system/iggy/sysfont01_ab_<code>.iggy
data/system/iggy/sysfont01_ab_<code>.iggytex
data/system/iggy/sysfont01_ab_<code>.iggyted
```

- Steam 언어 식별자를 두 CPK에 공통으로 존재하는 리소스 코드 후보와 대조하고, 정확히 하나만 일치할 때 그 언어만 처리합니다.
- 접미사가 없는 기본 리소스와 알려진 영어·일본어 코드는 대상에서 제외합니다.
- 검증된 문제 형태인 “`.iggy`와 `.iggyted`는 함께 다르고 `.iggytex`는 동일한 상태”만 허용합니다.
- 정상 버전의 `.iggy`를 일반 교체하고, CRILAYLA 압축 상태의 `.iggyted`는 원시 엔트리 형태로 이식합니다. 동일한 `.iggytex`는 현재 파일을 유지합니다.
- CPK 크기·헤더·엔트리 집합·압축 상태·재추출 SHA-256을 검증한 뒤에만 원본을 백업하고 결과를 적용합니다.
- 그래픽 사용자 인터페이스는 기본 `ko`(한국어)이며 우측 상단에서 `en`(English)으로 전환할 수 있습니다.

## 지원 환경

| 항목 | 내용 |
|---|---|
| 애플리케이션 버전 | `0.4.0` |
| 운영체제 | Windows 10/11 x64 |
| Python | 3.11 이상 |
| 게임 | Steam판 Dragon Ball Xenoverse 2 |
| 사용자 인터페이스 로캘 | `ko`, `en` |
| 패치 대상 | Steam 설치 언어가 두 CPK의 공통 리소스 코드 하나와 안전하게 매칭되는 경우 |
| 검증된 Steam 빌드 식별자 | `23988437` |
| 정상 소스 매니페스트 | `7238901667150908628` |
| 실제 게임 검증 | 검증 대상 Steam Windows 설치에서 정상 동작 확인 |
| 온라인 및 EAC | 지원하지 않음 |

공식 업데이트로 빌드 식별자가 바뀌거나 문제가 해결된 경우 기본 설정에서는 적용을 중단합니다. 알 수 없는 빌드 허용은 파일 구조와 문제가 동일하다고 직접 확인한 경우에만 사용하세요.

## 안전한 처리 흐름

1. 게임 설치 경로, Steam 빌드 식별자와 설치 언어를 확인합니다.
2. 사용자가 보유한 정상 버전 `data1.cpk`를 선택하거나 지정 Steam 매니페스트를 다운로드합니다.
3. 현재 CPK와 정상 CPK에서 완전한 세 파일 리소스 세트를 탐지합니다.
4. Steam 언어 식별자와 공통 리소스 코드 후보를 대조해 대상 코드 하나를 결정합니다.
5. 두 CPK에서 `.iggy`와 `.iggyted`가 함께 다르고 `.iggytex`가 동일한지 확인합니다.
6. 현재 CPK 사본에 정상 버전 `.iggy`와 원시 압축 `.iggyted`를 순서대로 이식합니다.
7. CPK 구조와 대상 파일 해시를 다시 검증합니다.
8. 모든 검증을 통과한 경우에만 원본을 백업하고 교체본을 원자적으로 적용합니다.

언어 값이 알려진 별칭과 매칭되지 않거나, 후보 코드가 없거나 둘 이상이면 안전을 위해 아무 파일도 수정하지 않습니다. Steam 언어 값 자체가 CPK 리소스 코드와 같으면 정확 일치 방식도 지원합니다.

## 준비 및 실행

필요 사항:

- python.org에서 설치한 Windows용 Python 3.11 이상
- Tcl/Tk가 포함된 일반 Python 설치
- Steam과 Dragon Ball Xenoverse 2 설치
- 대상 드라이브에 약 6~7 GiB 이상의 여유 공간
- 게임과 Steam 업데이트 작업이 종료된 상태

런타임 Python 패키지 의존성은 없습니다.

```powershell
py -3 -m xv2_prompt_fix
```

Python 실행 관리자가 없다면:

```powershell
python -m xv2_prompt_fix
```

버전 확인:

```powershell
py -3 -m xv2_prompt_fix --version
```

선택적 가상환경:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m xv2_prompt_fix
```

실행 정책 변경이나 관리자 권한은 기본적으로 필요하지 않습니다.

## 사용법

1. 게임을 종료합니다.
2. 앱을 실행하고 게임 설치 폴더를 확인합니다.
3. 정상 버전 리소스를 Steam에서 받거나 로컬 `data1.cpk`를 선택합니다.
4. 필요하면 우측 상단에서 사용자 인터페이스 로캘을 변경합니다.
5. **자동 수정 시작**을 누릅니다.
6. 설치 언어와 교체 범위 안내를 읽고 현재 언어에 패치가 필요하다고 확인한 경우만 계속합니다.
7. Steam 자동 다운로드를 선택했다면 QR 인증을 완료합니다.
8. 완료 후 앱을 종료하고 사용자가 직접 게임을 실행해 결과를 확인합니다.

이 도구는 EAC 설정을 변경하거나 온라인 실행을 구성하지 않습니다.

## 정상 버전 리소스 가져오기

### Steam 자동 다운로드

고정된 DepotDownloader 3.4.0을 공식 원본 저장소에서 내려받아 크기와 SHA-256을 검증한 뒤 실행합니다. 별도 콘솔의 QR 코드를 Steam 모바일 앱으로 승인해야 합니다.

이 앱 자체는 Steam 비밀번호를 입력받거나 저장하지 않습니다. DepotDownloader는 QR 인증 후 Steam 계정명과 세션 자료를 Windows의 .NET 로컬 저장소에 기록할 수 있습니다. 이 앱은 해당 자료를 읽거나 업로드하지 않으며 자동으로 삭제하지 않습니다. 패치 범위 안내와 함께 매 실행 시 이 내용을 고지합니다.

### 로컬 정상 버전 CPK

합법적으로 보유한 정상 버전 `data1.cpk`를 직접 선택할 수 있습니다. 이 방식은 Steam QR 인증과 DepotDownloader를 사용하지 않습니다.

자세한 개인정보 처리 내용은 [개인정보 처리 안내](PRIVACY.md)를 확인하세요.

## 원본 복원

**원본 복원**은 적용 당시 기록한 원본·수정본 SHA-256을 확인한 뒤 수행합니다.

- Steam 업데이트나 다른 모드가 현재 CPK를 변경한 경우 기본적으로 복원을 거부합니다.
- 강제 복원은 현재 공식 파일을 백업 파일로 덮어쓸 수 있으므로 특별한 경우에만 사용합니다.
- 상태 파일에는 게임 경로나 백업 절대 경로를 저장하지 않고 같은 `cpk` 폴더의 백업 파일명만 저장합니다.

생성 파일 예시:

```text
cpk\data1.cpk.xv2promptfix-backup-20260803-001500
cpk\.xv2promptfix-state.json
cpk\.xv2promptfix-source\<manifest-id>\data1.cpk
```

## 외부 도구 보안

외부 도구는 저장소에 포함하지 않습니다. 실행 시 [외부 도구 매니페스트](xv2_prompt_fix/external_tools.json)에 고정된 공식 주소에서 내려받고 다음을 검증합니다.

- HTTPS와 허용된 GitHub 호스트
- 정확한 다운로드 크기와 SHA-256
- ZIP 내부 실행 파일의 정확한 이름·크기·SHA-256
- PE 헤더 시그니처와 기대한 x86/x64 아키텍처
- 캐시된 실행 파일의 매 실행 재검증

하나라도 다르면 파일을 실행하지 않습니다.

이 검사는 고정한 파일의 동일성과 PE 헤더 형식을 확인합니다. Authenticode 게시자 코드 서명을 확인하는 것은 아니며, 현재 고정한 두 실행 파일은 Authenticode로 서명되어 있지 않습니다.

## 로컬 생성 파일

| 종류 | 위치 | 내용 |
|---|---|---|
| 로그 | `%LOCALAPPDATA%\XV2PromptFix\logs` | 마스킹된 실행 로그, 최대 20개·30일 |
| 도구 캐시 | `%LOCALAPPDATA%\XV2PromptFix\tools` | 해시 검증된 외부 도구 |
| 상태 | 게임 `cpk` 폴더 | 상대 백업 파일명과 해시 |
| 원본 백업 | 게임 `cpk` 폴더 | 적용 전 `data1.cpk` |
| 정상 소스 캐시 | 선택 시 게임 `cpk` 폴더 | 사용자가 보관을 켠 경우 |

## 개발 및 테스트

```powershell
py -3 -m compileall -q xv2_prompt_fix tests scripts
py -3 -m unittest discover -s tests -v
py -3 scripts\check_public_tree.py
```

- 테스트는 합성 CPK 시험 자료만 사용하며 실제 게임 파일을 포함하지 않습니다.
- Python 코드의 주석과 문서 문자열은 영어로 작성합니다.
- 코드, 주석, 테스트와 문서는 영어로 작성합니다. 한국어 번역 데이터와 명시적으로 표시된 README의 한국어 구간만 예외입니다.
- 언어 매핑을 변경할 때는 정확 일치, 별칭 일치, 미일치와 다중 일치 테스트를 추가합니다.

기여 규칙은 [기여 안내](CONTRIBUTING.md)를 참고하세요.

## 알려진 한계

- Steam 언어 식별자와 게임의 CPK 파일 접미사는 서로 다른 명명 체계를 사용할 수 있습니다.
- 새 Steam 언어 식별자나 CPK 코드가 나타나면 별칭 후보 갱신과 실제 게임 검증이 필요할 수 있습니다.
- 세 파일 중 하나라도 없거나 두 CPK 중 한쪽에만 있으면 해당 코드를 사용할 수 없습니다.
- `.iggy`와 `.iggyted`의 변경 상태가 서로 다르거나 `.iggytex`까지 다르면 검증된 문제 형태가 아니므로 중단합니다.
- CriPakTools는 오래된 외부 도구이므로 미래의 모든 CPK 구조를 보장할 수 없습니다.
- Steam이 과거 매니페스트 접근을 차단하면 자동 다운로드가 실패할 수 있습니다.
- 실제 사용자 설치본과의 최종 호환성은 해당 Windows PC에서 확인해야 합니다.

문제 해결은 [문제 해결 안내](docs/TROUBLESHOOTING.md), 검증 범위는 [호환성 안내](docs/COMPATIBILITY.md)를 참고하세요.

## 라이선스와 비공식 고지

이 저장소에 포함된 프로젝트 자체 Python 소스는 [MIT 라이선스](LICENSE)로 제공됩니다. 외부 도구와 게임 리소스에는 각각의 권리와 조건이 별도로 적용됩니다. 자세한 내용은 [제3자 고지](THIRD_PARTY_NOTICES.md)를 확인하세요.

이 프로젝트는 Valve, Steam, Bandai Namco Entertainment, Dimps 또는 관련 권리자와 제휴하거나 보증받은 프로젝트가 아닙니다. 모든 제품명과 상표는 각 권리자에게 귀속됩니다.

<!-- END ALLOWED KOREAN README SECTION -->

---

# XV2 Input Prompt Fix

This **unofficial Windows Python tool** works around a problem in certain Dragon Ball Xenoverse 2 Steam updates where controller and keyboard button images for some languages appear as `<IMG UNKNOWN>` or similar placeholders.

> This repository provides Python source only. It does not include or distribute executables, game files, extracted game resources, or third-party binaries.

## Key behavior

- Reads the installed language from the Steam app manifest.
- Finds complete language-resource sets in both the current and reference `data1.cpk` files:

```text
data/system/iggy/sysfont01_ab_<code>.iggy
data/system/iggy/sysfont01_ab_<code>.iggytex
data/system/iggy/sysfont01_ab_<code>.iggyted
```

- Matches the Steam language identifier against resource-code candidates shared by both CPK files and proceeds only when exactly one code matches.
- Excludes unsuffixed default resources and known English and Japanese codes.
- Accepts only the validated fault pattern: `.iggy` and `.iggyted` must both differ while `.iggytex` must be identical.
- Replaces the reference `.iggy` normally, transplants the CRILAYLA-compressed `.iggyted` in its raw storage form, and keeps the identical current `.iggytex`.
- Validates archive size, headers, the complete entry set, compression state, and re-extracted SHA-256 values before backing up the original and applying the result.
- The graphical interface defaults to locale `ko` (Korean) and can be switched to locale `en` (English) in the upper-right corner.

## Supported environment

| Item | Details |
|---|---|
| Application version | `0.4.0` |
| Operating system | Windows 10/11 x64 |
| Python | 3.11 or newer |
| Game | Dragon Ball Xenoverse 2 for Steam |
| User-interface locales | `ko`, `en` |
| Patch target | An installed Steam language that maps safely to exactly one resource code shared by both CPK files |
| Validated Steam build ID | `23988437` |
| Reference-source manifest | `7238901667150908628` |
| Actual-game validation | Passed on the validated Steam Windows installation |
| Online play and EAC | Not supported |

By default, the application stops if an official update changes the build ID or fixes the problem. Allow an unknown build only after personally confirming that the file structure and fault pattern are unchanged.

## Safe processing flow

1. Validate the game installation, Steam build ID, and installed language.
2. Select a lawfully owned reference `data1.cpk` or download the specified Steam manifest.
3. Detect complete three-file resource sets in the current and reference CPK files.
4. Match the Steam language identifier to exactly one common resource code.
5. Confirm that `.iggy` and `.iggyted` both differ and `.iggytex` is identical.
6. Transplant the reference `.iggy` and raw compressed `.iggyted` into a copy of the current CPK.
7. Revalidate the archive structure and target-file hashes.
8. Back up the original and atomically apply the replacement only after every validation passes.

No file is modified when the language identifier has no known match, no candidate exists, or more than one candidate matches. An exact match is also accepted when the Steam language value itself equals a CPK resource code.

## Preparation and execution

Requirements:

- Python 3.11 or newer for Windows, installed from python.org
- A standard Python installation that includes Tcl/Tk
- Steam and Dragon Ball Xenoverse 2 installed
- Approximately 6–7 GiB or more of free space on the target drive
- The game closed and all Steam update operations finished

There are no runtime Python package dependencies.

```powershell
py -3 -m xv2_prompt_fix
```

If the Python Launcher is unavailable:

```powershell
python -m xv2_prompt_fix
```

Check the version:

```powershell
py -3 -m xv2_prompt_fix --version
```

Optional virtual environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m xv2_prompt_fix
```

Changing the execution policy or using administrator privileges is not normally required.

## Usage

1. Exit the game.
2. Start the application and confirm the game-installation directory.
3. Download the reference resources from Steam or select a local `data1.cpk`.
4. Change the user-interface locale in the upper-right corner when needed.
5. Click **Start automatic patch**.
6. Review the installed language and replacement scope, then continue only after confirming that the current language needs the patch.
7. If Steam automatic download was selected, complete QR authentication.
8. When the operation finishes, close the application and start the game yourself to verify the result.

This tool does not change EAC settings or configure online execution.

## Obtaining reference resources

### Steam automatic download

The application downloads pinned DepotDownloader 3.4.0 from its official upstream repository, verifies its size and SHA-256, and then runs it. You must approve the QR code shown in a separate console through the Steam mobile app.

The application itself neither requests nor stores a Steam password. After QR authentication, DepotDownloader may store the Steam account name and session data in Windows .NET local storage. This application neither reads nor uploads that data and does not delete it automatically. This information is shown with the patch-scope notice on every run.

### Local reference CPK

You may select a lawfully owned reference `data1.cpk` directly. This method does not use Steam QR authentication or DepotDownloader.

See the [Privacy Policy](PRIVACY.md) for details about data handling.

## Restoring the original

**Restore original** first verifies the original and patched SHA-256 values recorded when the patch was applied.

- Restoration is refused by default if a Steam update or another mod has changed the current CPK.
- Forced restoration can overwrite a current official file with the stored backup and should be used only in exceptional cases.
- The state file stores neither the game path nor an absolute backup path; it stores only the backup filename in the same `cpk` directory.

Generated-file examples:

```text
cpk\data1.cpk.xv2promptfix-backup-20260803-001500
cpk\.xv2promptfix-state.json
cpk\.xv2promptfix-source\<manifest-id>\data1.cpk
```

## External-tool security

External tools are not included in the repository. At runtime, they are downloaded from official URLs pinned in the [external-tool manifest](xv2_prompt_fix/external_tools.json), and the following properties are verified:

- HTTPS and an allowed GitHub host
- Exact download size and SHA-256
- Exact filename, size, and SHA-256 of the executable inside the ZIP archive
- PE header signature and expected x86/x64 architecture
- Revalidation of cached executables on every run

The file is not executed if any property differs.

These checks confirm the pinned file identity and PE header format. They do not verify an Authenticode publisher signature; neither currently pinned executable is Authenticode-signed.

## Locally generated files

| Type | Location | Contents |
|---|---|---|
| Logs | `%LOCALAPPDATA%\XV2PromptFix\logs` | Redacted execution logs, up to 20 files and 30 days |
| Tool cache | `%LOCALAPPDATA%\XV2PromptFix\tools` | Hash-verified external tools |
| State | The game's `cpk` directory | Relative backup filename and hashes |
| Original backup | The game's `cpk` directory | The pre-patch `data1.cpk` |
| Reference-source cache | The game's `cpk` directory, when selected | Present when the user enables retention |

## Development and testing

```powershell
py -3 -m compileall -q xv2_prompt_fix tests scripts
py -3 -m unittest discover -s tests -v
py -3 scripts\check_public_tree.py
```

- Tests use only synthetic CPK fixtures and do not include actual game files.
- Write Python comments and docstrings in English.
- Write source code, comments, tests, and documentation in English. The Korean locale data and the explicitly marked Korean section of this README are the only exceptions.
- Changes to language mapping require tests for exact matches, alias matches, no match, and multiple matches.

See the [Contributing Guide](CONTRIBUTING.md) for contribution rules.

## Known limitations

- Steam language identifiers and game CPK suffixes can use different naming systems.
- New Steam identifiers or CPK codes may require candidate-alias updates and validation in the actual game.
- A code cannot be used when any of the three files is missing or exists in only one CPK.
- The operation stops when `.iggy` and `.iggyted` do not change together or when `.iggytex` also differs, because that is not the validated fault pattern.
- CriPakTools is an old external tool and cannot guarantee support for every future CPK structure.
- Automatic download can fail if Steam blocks access to a historical manifest.
- Final compatibility with an actual user installation must be verified on that Windows PC.

See the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for problem resolution and the [Compatibility Guide](docs/COMPATIBILITY.md) for the validation scope.

## License and unofficial-project notice

The project's own Python source included in this repository is provided under the [MIT License](LICENSE). External tools and game resources are subject to their own separate rights and terms. See the [Third-Party Notices](THIRD_PARTY_NOTICES.md) for details.

This project is not affiliated with or endorsed by Valve, Steam, Bandai Namco Entertainment, Dimps, or any related rights holder. All product names and trademarks belong to their respective owners.
