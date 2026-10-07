# 개발 재개 메모

2026-10-07: 프로젝트 뼈대와 Python CLI까지 구현했습니다. 자동 테스트 14개와 일곱 모듈 구조 검사를 통과했습니다. 게임 규칙 변경 소스는 아직 없으며, 실제 Divine 패키징과 게임 실행은 미검증입니다.

## 데스크톱에서 시작

```sh
git clone https://github.com/jhwan159/BG3-5.5e-mod-20-level.git
cd BG3-5.5e-mod-20-level
python -m unittest discover -s tests -v
python -m bg3tool doctor
python -m bg3tool status
```

이미 체크아웃이 있다면 해당 폴더에서 `git pull --ff-only`를 실행합니다. Python 3.10 이상이 필요하며 macOS/Linux에서는 `python3`을 사용할 수 있습니다.

## 우선순위와 다음 작업

아래 순서로 작은 단위를 구현하고 각 단위의 검증을 마친 뒤 다음으로 진행합니다. 이 목록은 착수 순서이며 아직 구현 완료된 작업은 없습니다.

| 순서 | 작업 단위 | 완료 기준 |
|---|---|---|
| 1 | 원본 LSX 스냅샷 수집 CLI | 지원 빌드·파일 해시·UUID·속성을 기록하고 중복 식별자를 감지 |
| 2 | 스냅샷 비교 CLI | 추가·삭제·속성 변경을 출력하고 노드 순서 변경에 영향받지 않음 |
| 3 | 실제 원본 데이터 기준선 | 설치 빌드와 Fighter/Champion·Wizard/Evoker 성장표·슬롯·자원 UUID 대조표 확보 |
| 4 | Fighter 기본 성장 | 1~12레벨 Second Wind·Action Surge·추가 공격 지급 시점 검증 |
| 5 | Fighter/Champion 후반 성장 | 13~20레벨 기능과 4회 공격 연결 검증 |
| 6 | Wizard 슬롯 성장 | 1~20레벨 슬롯·준비·주문서와 7~9레벨 UI 확인 |
| 7 | Wizard/Evoker 후반 특성 | 무료 시전 및 후반 기능 지급·저장 검증 |
| 8 | 턴 코어 | 집중과 턴당 슬롯 시전 제한의 반응·경계값 검증 |
| 9 | 기존 주문 개별 변환 | Cure Wounds → Healing Word → True Strike → Guidance 순서로 수치·비용·집중 대조 |
| 10 | Mastery 개별 구현 | Vex → Nick/Light → Topple 순서로 구현하고 Action Surge 상호작용 검증 |
| 11 | 고레벨 주문 개별 구현 | Finger of Death → Sunburst → Power Word Kill의 슬롯·원문 효과 검증 |
| 12 | 저장·재육성과 패키징 | 12/13/19/20레벨 저장·로드·재육성, 실제 PAK 로딩 검증 |

첫 착수 대상은 1번입니다. 이전 턴에서는 코드 확인과 원본 경로 질문까지만 진행했으며, 스냅샷/비교 코드는 아직 작성하지 않았습니다. 게임 설치 폴더 또는 추출된 LSX/Stats 경로는 아직 전달받지 않았습니다. 원본이 없어도 1~2번은 합성 테스트 데이터로 개발할 수 있습니다. 실제 게임 UUID와 수치를 임의로 넣지 않습니다.

옵시디언에서 확인한 기획 노트와 도구 사용법은 README.md, 첫 프로토타입의 필수 검증 증거는 data/milestones.json에 있습니다. 코어에는 캠페인 패치나 Chionthar Wilds 맵·퀘스트 UUID를 직접 넣지 않습니다.
