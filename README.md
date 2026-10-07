# BG3 2024 Level20 — 프로젝트 뼈대와 제작 CLI

옵시디언 `BG3_2024_Level20_Vault/15_Mod_Plan`의 모듈 기획과 첫 구현 순서를 반영한 개발 시작점입니다. **현재 게임 규칙을 변경하는 모드는 아닙니다.** 모듈별 소스 폴더, 메타데이터 생성, 검사·빌드·패키징 명령을 제공합니다.

## 빠른 시작

Python 3.10 이상에서 프로젝트 폴더를 열고 실행합니다. 외부 Python 패키지는 필요 없습니다.

```sh
python3 -m bg3tool doctor
python3 -m bg3tool status
python3 -m bg3tool validate
python3 -m bg3tool build
python3 -m bg3tool pack
python3 -m unittest discover -s tests -v
```

Windows에서는 `python3` 대신 `python`을 사용할 수 있습니다. 다른 폴더에서 실행한다면 `--project /path/to/project`를 하위 명령 앞에 지정하세요. 선택적으로 `python3 -m pip install -e .` 후 `bg3mod` 명령을 사용할 수 있습니다.

## 구성

| 모듈 | 책임 | 직접 의존성 |
|---|---|---|
| RulesCore | 행동·슬롯·집중·상태·판정 | 없음 |
| Classes2024 | 직업 성장·자원·선택 | RulesCore |
| LegacyCompatibility | 기존 종족·서브클래스 연결 | RulesCore, Classes2024 |
| Origins2024 | 배경·Species·Origin Feat | RulesCore |
| Level20 | 상한·UI·고레벨 슬롯·성장 연결 | Classes2024 |
| Spells2024 | 주문 갱신·고레벨 주문 | RulesCore, Level20 |
| CampaignPatches | 별도 XP·조우·호환 패치 | RulesCore, Classes2024, Level20, Spells2024 |

기본 `prototype` 프로필은 RulesCore, Classes2024, LegacyCompatibility, Level20, Spells2024를 의존 순서로 구성합니다. `--profile all-scaffolds`는 일곱 모듈 모두를 포함합니다. 이는 개발 프로필이며 검증된 배포 조합을 의미하지 않습니다. Spells2024는 첫 프로토타입의 고레벨 주문을 포함하므로 Level20을 요구하도록 정했습니다. CampaignPatches의 의존성은 개발용 기본값이며, 코어는 캠페인 패치를 요구하지 않습니다.

```text
modproject.json             모듈 UUID·버전·의존성·빌드 프로필
modules/<모듈>/source/       PAK 안에 들어갈 Mods/Public/Localization 경로
data/milestones.json         첫 구현 작업·필수 검증 증거·테스트 레벨
bg3tool/                    제작 CLI
tests/                      도구 자동 검증
build/stage-*/              개별 모듈 스테이징 및 SHA-256 보고서
dist/stage-*/               실제 패키징 결과
local/                     개인 원본 데이터·관찰 기록 (Git 제외)
```

UUID는 이 프로젝트의 새 모듈 식별자입니다. 게임 원본 UUID가 아니며, 배포 후에도 유지해야 합니다. `version64`의 기본값은 1.0.0.0 표현입니다. 생성되는 `meta.lsx`의 XML 버전은 초기 템플릿이며, 지원할 게임 빌드의 Toolkit 출력과 대조해야 합니다.

## 소스 추가와 검사

파일을 `modules/<모듈>/source/Public/BG3_2024_<모듈>/...` 등에 넣은 후 `validate`와 `build`를 실행합니다. `meta.lsx`는 manifest를 기준으로 자동 생성되므로 직접 추가하지 않습니다. `.gitkeep`은 패키지에 들어가지 않습니다. 새 빌드는 항상 새 디렉터리를 만들며 이전 결과를 덮어쓰지 않습니다. 같은 입력의 모듈 파일과 SHA-256 보고서는 동일합니다.

검사는 모듈 UUID·의존성·순환 참조, 소스 경로 충돌, XML/JSON 문법을 확인합니다. **BG3 Stats 문법, 게임 객체 참조, 직업 성장의 의미, 게임 내 로딩을 검증하지는 않습니다.** 모듈간 의도적인 동일 파일 오버라이드도 현재는 충돌로 거부합니다.

## 원본 조사

개인이 추출하고 LSX로 변환한 원본 파일을 `local/`에 두고 조사합니다. 추출 도구나 게임 데이터를 저장소에 포함하지 않습니다.

```sh
python3 -m bg3tool inspect local/Progressions.lsx > local/progressions.json
```

출력은 원본 SHA-256, 노드 ID, 실제 속성 ID·타입·값입니다. 변경 전 기준값과 새 소스를 비교하는 데 사용하세요. 바이너리 LSF/PAK는 먼저 적절한 도구로 변환해야 합니다. 게임 빌드를 확인한 뒤 `modproject.json`의 `game_build`에 기록합니다.

## PAK 생성

`pack`은 기본적으로 빌드 후 Divine 인자 목록만 출력합니다. 각 모듈을 독립 PAK로 만드는 명령이며 자동 설치·배포는 하지 않습니다.

```sh
python3 -m bg3tool pack --divine /path/to/divine --execute
```

실행 가능한 LSLib Divine을 별도로 준비해야 합니다. `BG3_DIVINE` 환경변수도 지원합니다. macOS에서 Windows용 `Divine.exe`를 직접 실행할 수 있다고 가정하지 않습니다. 도구가 실행되는 환경에서 패키징하거나 사용자가 준비한 실행 래퍼를 지정하세요. 이 저장소는 LSLib을 자동 설치하지 않습니다. 빈 모듈도 개발 확인용으로 패키징할 수 있지만 게임플레이 구현을 포함하지 않습니다.

## 다음 구현 순서

1. 지원할 BG3 빌드의 원본 UUID·성장표·슬롯·자원·지급 시점을 조사하고 대조표를 작성합니다.
2. Fighter/Champion과 Wizard/Evoker를 1~20레벨로 연결합니다.
3. Vex/Nick/Topple, Light 추가 공격, 지정된 기존·고레벨 주문과 턴 코어를 구현합니다.
4. 1/5/11/13/17/20레벨 고정 조우와 12/13/19/20레벨 저장·로드·재육성을 검증합니다.

1~12레벨 XP는 최대한 보존하고 13~20레벨 XP는 별도 설계합니다. 미확인 숫자나 Chionthar Wilds의 맵·퀘스트 UUID를 코어에 넣지 않습니다. 고레벨 주문이 빠진 Level20을 완성된 시전자 패키지로 표시하지 않습니다. 상세 미구현 항목은 `status`에서 확인합니다.

## 확인한 근거와 한계

2026-10-07 Obsidian 앱에서 「기획 — 모듈과 플랫폼」, 「기획 — 첫 구현과 개발 순서」, 「기획 — 캠페인과 밸런스」를 확인했습니다. macOS의 Documents 직접 읽기 제한으로 Vault 전체를 가져오지는 않았습니다. 다른 기획 노트의 세부 규칙은 아직 이 코드의 구현 근거에 포함하지 않았습니다.

- [Larian 공식 Toolkit 프로젝트 구조](https://docs.baldursgate3.game/Getting_Started:_Creating_a_New_Mod)
- [LSLib 원본 및 배포](https://github.com/Norbyte/lslib)
- [Divine 명령행 인자 정의](https://github.com/Norbyte/lslib/blob/master/Divine/CLI/CommandLineArguments.cs)

실제 게임 실행, Toolkit 프로젝트 가져오기, 실제 Divine PAK 생성은 아직 검증하지 않았습니다.
