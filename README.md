# 교권보호국 시뮬레이터

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://teacher-rights-protection-bureau-simulator-nfs4pkldbqhb7ph6yjp.streamlit.app/)

경기도교육청 교권보호단의 조직 개편을 조직이론(① 조직환경: 개방체계·상황이론, ② 분업과 조정)으로
실험해 보는 발표 시연용 데모입니다. 같은 교권침해 사안 흐름을 여러 조직 구조에 넣고,
교사가 지는 부담과 조직이 지는 조정 비용이 어떻게 달라지는지 비교합니다.

> 처리시간·확률 대부분은 가정값입니다. 결과는 실제 운영 효과의 증거가 아니라 이론의 논리를 보여주는 사고실험으로 다뤄 주세요.

## 대시보드

**👉 [대시보드 바로가기](https://teacher-rights-protection-bureau-simulator-nfs4pkldbqhb7ph6yjp.streamlit.app/)**

### Streamlit Community Cloud 배포
1. [share.streamlit.io](https://share.streamlit.io)에 깃허브 계정으로 로그인
2. **Create app** → 이 레포, 브랜치 `main`, Main file path `app/Home.py`
3. **Advanced settings → Secrets**에 키 입력 (최상위 키는 환경변수로도 읽힘)
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

배포 환경에서는 수집기를 돌리지 않으므로 시드 지식베이스(`config/seed_corpus.yaml`)와
커밋된 원문 스냅샷(`data/snapshot/corpus.jsonl`, 있으면)으로 동작합니다.
배포 앱에 원문을 반영하려면 로컬에서 `python -m collector.pipeline --snapshot` 을 돌린 뒤
`data/snapshot/corpus.jsonl` 을 커밋합니다. 스냅샷에는 법령·판례(저작권법 제7조)와 정부 자료(공공누리)만 들어가고 언론 기사 본문은 빠집니다.

## 수집기

| 수집기 | 대상 | 필요한 것 |
|---|---|---|
| `laws` | 교원지위법·시행령, 초·중등교육법·시행령, 교육공무원법, 아동학대처벌법, 아동복지법 등 조문 | `LAW_OC` |
| `ordinances` | 경기도교육청 교권보호전담관 운영 조례 + 검색어로 찾은 경기·인천 교육활동 보호 자치법규 | `LAW_OC` |
| `admin_rules` | 교육부 고시 (교육활동 침해 행위 및 조치 기준, 학생생활지도 고시) | `LAW_OC` |
| `precedents` | 교육활동 침해·교권보호위원회·정서학대·악성 민원 판례 (판시사항·판결요지) | `LAW_OC` |
| `pages` | 경기교권보호지원센터 안내, 교육부 게시글(첨부 HWPX·PDF까지), 도의회, 프랑스 지침, 기사 | 없음 |
| `boards` | 교육부·경기도교육청 보도자료 게시판을 키워드로 검색해 수집 | 없음 |
| `files` | HWPX·PDF·DOCX 파일 (URL·경로 등록, 또는 `data/raw/inbox/`에 넣기) | 없음 |

```bash
python -m collector.pipeline --list            # 수집기와 키 상태
python -m collector.pipeline --only boards     # 일부만
```

대상은 `config/sources.yaml` 에서 고칩니다. 원문이 들어오면 같은 URL(또는 `replaces:`로 지정한)
팀 요약 시드가 빠지고, 실행이 끝나면 남은 팀 요약 목록을 보여 줍니다. 구형 `.hwp` 는 읽지 못하니 HWPX나 PDF로 저장해 넣어 주세요.

## 빠른 시작

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # 키 입력 (아래 참고)
python -m collector.pipeline   # 지식베이스 만들기 (키가 없으면 시드 자료만)
streamlit run app/Home.py
```

## 키 설정 (`.env`)

| 변수 | 용도 | 없으면 |
|---|---|---|
| `LAW_OC` | 국가법령정보센터 Open API 인증키 ([open.law.go.kr](https://open.law.go.kr) 무료 신청). 조례·교권5법 원문을 조문 단위로 수집 | 팀 문서의 조문 요약(“팀 요약” 표시)으로 동작 |
| `ANTHROPIC_API_KEY` | Claude가 시뮬레이션 결과를 이론·조문 근거로 설명, 사안 로그를 이야기로 풀기, 근거 Q&A 답변 | 규칙 기반 요약과 검색 발췌로 동작 |
| `GOOGLE_TRANSLATE_API_KEY` | Google Cloud Translation API 키. 사이드바 '언어 / Language'에서 English를 고르면 화면 문장을 영어로 번역 | 한국어로만 표시 |
| `ANTHROPIC_MODEL` | 사용할 모델 (기본 `claude-opus-5-5`) | |
| `ASSEMBLY_KEY` | 열린국회정보 Open API 인증키 ([open.assembly.go.kr](https://open.assembly.go.kr/portal/openapi/main.do) 회원가입 → 인증키 발급). 교권 관련 국회 법률안과 제안이유를 근거 자료에 추가 (앱은 하루 한 번 갱신, `python -m collector.pipeline --only bills`) | 법률안 없이 동작 |
| `GG_DATA_KEY` | 경기데이터드림 Open API 인증키 ([data.gg.go.kr](https://data.gg.go.kr) 무료 신청). 지구대·파출소 현황, 초중고 현황. `python -m collector.gg_data --check`로 확인, `python -m collector.gg_data`로 `data/measured/gg/`에 저장 | 해당 데이터 없이 동작 |

`.env`는 `.gitignore`에 있어 커밋되지 않습니다.

### 학교 데이터

| 데이터 | 받는 곳 | 키 |
|---|---|---|
| 전국초중등학교위치표준데이터 (CSV) | [공공데이터포털](https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=전국초중등학교위치표준데이터) | 필요 없음 |
| 학교 기본정보 (선택): 학교코드·전화·홈페이지를 붙이고 위치 데이터와 대조 | [NEIS 교육정보 개방포털](https://open.neis.go.kr) | `NEIS_KEY` (.env 또는 Streamlit Secrets) |

저장소에는 경기도분 2,576곳(초 1,380 · 중 692 · 고 504, 데이터 기준일 2026-10-01, 제공 한국교육시설안전원)이
`data/schools/gyeonggi_schools.csv`로 들어 있습니다. 새 CSV로 바꾸려면 같은 경로에 덮어쓰면 됩니다 (UTF-8, CP949 모두 읽음).
없으면 25개 교육지원청만으로 동작하고, 사안은 교육지원청마다 같은 비중으로 생깁니다.

## 구성

```
config/
  seed_corpus.yaml     팀 조사 자료 요약 (조례 조문, 기사, 정책, 이론) + 출처·신뢰도
  sources.yaml         실제 수집 대상 (법령명, 조례, 웹페이지 URL)
  scenarios.yaml       사안 추적용 시나리오 (1호 사안 등, 「참교육」 시나리오는 팀이 추가)
collector/             수집 파이프라인
  law_api.py           국가법령정보센터 API (법령·자치법규·행정규칙·판례)
  sites.py             교육부·경기도교육청 보도자료 (게시판 검색, 첨부 HWPX)
  documents.py         HWPX·PDF·DOCX 본문 추출
  html_page.py         일반 웹페이지, files.py 파일·inbox
rag/                   문자 n-gram TF-IDF + BM25 하이브리드 검색, 근거 Q&A
sim/
  structures/*.yaml    비교할 조직 구조와 파라미터
  cases.py             사안 생성기 (Perrow 기술 유형, Thompson 상호의존 유형)
  engine.py            SimPy 이산사건 시뮬레이션
  metrics.py           지표 (이론과 1:1 대응)
  explain.py           Claude 결과 설명 / 규칙 기반 요약
agents/                규제 컴플라이언스 에이전트와 행위자 에이전트
geo/                   경기도 25개 교육지원청, 학교 위치 CSV 로더, 감독 구조 트리
app/                   Streamlit 대시보드 (시뮬레이션·사안 추적, 근거 자료, 에이전트 시뮬레이션, 실측 분석)
tests/
```

## 관할 교육지원청과 지도 (시뮬레이션 페이지)

- **지도**: 경기도 초·중·고 학교와 25개 교육지원청 (교육지원청 위치는 시청 부근 대략 위치)
- **감독 구조**: 교육부 → 경기도교육청(교육감, 교권보호단) → 교육지원청 → 지역교권보호위원회·관할 학교
- **관할별 시뮬레이션**: 사안이 학교 수 비중대로 각 교육지원청 관할에서 생기고, 그 교육지원청 위원회로 갑니다.
  위원회는 교육지원청마다 다른 날 열리고 1회 정원(가정, 사이드바에서 조정)을 넘으면 다음 회의로 밀립니다.
- 데이터 출처와 NEIS 대조 결과는 근거 자료 페이지 하단에 있습니다.

## 비교 구조

| 구조 | 내용 | 이론 |
|---|---|---|
| A 분산 구조 | 교사가 상담·법률·행정 창구를 직접 찾아다님, 조정자 없음 | 분화만 있고 통합 부족 (Lawrence & Lorsch), Gulick |
| B0 출범 초기 | 교육감 직속 + 사안팀, 매뉴얼·연계절차 없음 (8.24~10.7) | 공식화 이전 |
| B 교권보호단 | 상근 1 + 비상근 1~2 + 센터 담당이 사안 단위로 묶임, 조례 시행 후 | 위계 + 사안팀 조정 (Burns & Stalker, Thompson) |
| C 인천형 | 상주 인력 중심 통합 | 안정적 전담 인력 조건 |

결론의 실효성 조건 세 가지는 시뮬레이션 페이지에서 직접 켜고 끌 수 있습니다.
① 역할 구분(조례 제17조 연계절차) ② 안정적 전담 인력(상근 수, 비상근 응답 비율) ③ 제도화(조례 제25조 매뉴얼)

## 규제 컴플라이언스 에이전트 (에이전트 시뮬레이션 페이지)

사안 하나를 놓고 행위자 에이전트들이 Claude로 다음 행동을 하나씩 제안하고, 모든 행동은 실행 전에
**컴플라이언스 에이전트**의 심사를 받습니다.

```
행위자 에이전트 ──행동 제안──▶ 컴플라이언스 에이전트 ──RAG──▶ 법령·조례·정책
      ▲                              │
      │        허용 / 조건부 허용 / 차단 + 근거 조문 + 대안 + 후속 절차
      └──────── 차단되면 대안 역할에게 이유와 함께 차례가 넘어감
```

- **공적 주체**(전담관, 교육감, 위원회 등): 권한 안의 행동인지, 절차를 지켰는지 심사. 권한 밖이면 차단하고 권한 있는 주체를 제시 (예: 전담관의 사실조사 → 조례 제15조로 차단, 위원회 심의 요청으로 전환)
- **사인**(학부모, 피해 교원): 행동은 막지 않되 교육활동 침해에 해당하는지 판단해 보호 조치·위원회 절차를 띄움
- 근거 자료에 없는 조항은 지어내지 않고 "근거 불충분"으로 표시
- 조직 구조: 교권보호단 / 기존 분산 구조(후속 절차를 챙길 주체가 없으면 "처리 주체 없는 후속 절차"로 집계) / 드라마식 교권보호국(가상)
- 코드: `agents/` (`compliance.py`, `actors.py`, `roles.py`, `runner.py`)

`ANTHROPIC_API_KEY`가 없으면 **오프라인 예시 모드**로 돕니다. 행위자는 예시 스크립트를, 컴플라이언스는 몇 가지 규칙을 따르므로 흐름 확인용으로만 쓰세요.
실제 판정 품질은 수집된 원문 법령에 달려 있습니다. 교권5법 원문이 없으면 "근거 불충분"이 많이 나옵니다.

## 지표 (대량 비교 시뮬레이션)

첫 응답까지 시간, 종결까지 기간, 교사가 접촉한 기관 수, 반복 진술, 조정 메시지 수, 업무 중복, 담당자 공백, 창구 착오.
시뮬레이터의 각 행동은 지식베이스에서 근거 문서를 검색해 인용합니다. 원문 조례를 수집하면 인용도 원문으로 바뀝니다.

## 데이터 출처

시뮬레이터와 대시보드가 쓰는 데이터 전부입니다. 같은 목록이 `config/data_sources.yaml`에 있습니다.


**실측 통계**

| 제공기관 | 데이터 | 기준일 | 형식 | 키 | 쓰이는 곳 |
|---|---|---|---|---|---|
| 교육부 | [교권보호위원회 개최 현황](https://www.data.go.kr/data/15137983/fileData.do) | 2024-02-29 | HWPX (공공데이터포털 파일) | - | 사안 유형 비율(실측 기반), 심의 건수 추이, 지식베이스 |
| 교육부 | [교육활동 침해 및 교원치유지원센터 지원 현황](https://www.data.go.kr/data/15112904/fileData.do) | 2024-02-29 | HWPX (공공데이터포털 파일) | - | 교육활동보호센터 이용 건수, 2019 심의 건수, 지식베이스 |
| 교육부 | [교육활동 보호 후속 조치 추진현황](https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=98939&lev=0&m=020402) | 2024-05 | PDF (보도자료 별첨) | - | 무고성 아동학대 신고 비율(교육감 의견 제출 연 환산), 심의 결과, 1395 상담, 지식베이스 |
| 경기도교육청 | [행정구역별 학제별 학급·학생·교원](https://www.data.go.kr/data/15077331/fileData.do) | 2025-04-01 | XLSX → data/measured/gyeonggi_offices.csv | - | 교육지원청별 사안 비중(교원 수 비례) |
| 보건복지부 | [아동학대 발생 현황 (시도별)](https://www.data.go.kr/data/15127920/fileData.do) | 2024-12-31 | CSV | - | 참고 자료 (시뮬레이터 값에는 안 씀) |
| 경찰청 | [아동학대 검거 및 조치 현황](https://www.data.go.kr/data/15037062/fileData.do) | 2023-12-31 | CSV | - | 참고 자료 (시뮬레이터 값에는 안 씀) |
| 교육부 학교알리미 공시 (school-violence-map 공개 집계) | [학교폭력 심의 결과·학교장 자체해결 (초·중·고 약 1만 2천 곳, 2023~2026 공시)](https://geeksbaek.github.io/school-violence-map/) | 2026-05-16 수집 | JSON → data/measured/school_violence_sido.csv | - | 실측 분석 ⑦ 학교폭력 심의율과 교보위 심의 회귀 |
| 시·도교육청 (보도자료·지역 언론) | 학교폭력 실태조사 1차 시도별 피해응답률 2022~2026 (시도별 출처는 CSV 출처 칸) | 매년 9월 발표 | 보도 본문 → data/measured/school_violence_survey_sido.csv | - | 실측 분석 ⑦ 피해응답률 회귀 (신뢰도 C) |
| 경찰청 자료 인용 보도 | [시도별 촉법소년 소년부 송치 (7개 시도 일부)](https://www.kyeonggi.com/article/20251006580034) | 2024~2025 보도 | 기사 본문 → data/measured/juvenile_crime_sido.csv | - | 실측 분석 ⑦ 참고 추이 |
| 한국교육개발원 (교육통계서비스 KESS) | [시도별 학생수 (초·중·고)](https://kess.kedi.re.kr) | 2026-04-01 | XLSX → data/measured/schoolinfo/students_by_sido.csv | - | 실측 분석 ④ 학폭 심의율·촉법소년 연도별 학생 수 분모 |
| 한국교육학술정보원 (학교알리미) | [공시정보 Open API (학년별·학급별 학생수 등)](https://www.schoolinfo.go.kr/ng/go/pnnggo_a01_m0.do) | 수시 | Open API (config/schoolinfo.yaml) | `SCHOOLINFO_KEY` | 실측 분석 ⑦ 연도별 학생 수 (python -m collector.schoolinfo) |

**위치·기관**

| 제공기관 | 데이터 | 기준일 | 형식 | 키 | 쓰이는 곳 |
|---|---|---|---|---|---|
| 한국교육시설안전원 | [전국초중등학교위치표준데이터 (경기 2,576곳)](https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=전국초중등학교위치표준데이터) | 2026-10-01 | CSV → data/schools/gyeonggi_schools.csv | - | 시뮬레이션 지도, 학교 → 관할 교육지원청 (교원 수 표가 없을 때 사안 비중) |
| 교육부 (NEIS) | [학교기본정보](https://open.neis.go.kr) | 수시 | Open API | `NEIS_KEY` | 근거 자료 화면 학교 정보 대조 (선택) |
| 경기도 (경기데이터드림) | [경기도 지구대(파출소) 현황](https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=DQ2I0RA86JC3Z2M9Q8RZ17985111&infSeq=3) | 수시 (2025-12-31 기준 자료) | Open API (Ptrldvsnsubpolcstus) | `GG_DATA_KEY` | 교육지원청별 경찰 관서 수 (python -m collector.gg_data, 참고) |
| 경기도 (경기데이터드림) | [경기도 초중고등학교 현황](https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=1CO945ICIYJN0ZYSPR0F21083003&infSeq=3) | 수시 | Open API (GgSchoolM) | `GG_DATA_KEY` | python -m collector.gg_data 로 저장, 학교 위치 대조용 |

**지식베이스**

| 제공기관 | 데이터 | 기준일 | 형식 | 키 | 쓰이는 곳 |
|---|---|---|---|---|---|
| 법제처 (국가법령정보센터) | [법령·자치법규·행정규칙·판례 (교원지위법, 경기도교육청 교권보호전담관 운영 조례, 교육부 고시 등)](https://open.law.go.kr) | 수시 | Open API (DRF) | `LAW_OC` | 근거 자료·에이전트 시뮬레이션 조문 인용 (config/sources.yaml laws·ordinances·admin_rules·precedents) |
| 국회 (열린국회정보) | [국회의원 발의법률안 + 법률안 제안이유 및 주요내용](https://open.assembly.go.kr/portal/data/service/selectAPIServicePage.do/OK7XM1000938DS17215) | 수시 (하루 1회 갱신) | Open API (nzmimeepazxkubdpn, BPMBILLSUMMARY) | `ASSEMBLY_KEY` | 교원지위법·초중등교육법·아동학대처벌법 개정안 제안이유를 근거 자료로 검색 |
| 교육부 | [보도자료 게시판 (교권·교육활동 보호 키워드, 첨부 HWPX·PDF 포함)](https://www.moe.go.kr/boardCnts/listRenew.do?boardID=294&m=020402) | 2023-07 이후 게시글 | 웹 + 첨부파일 | - | 근거 자료 (config/sources.yaml boards.moe_press) |
| 경기도교육청 | [보도자료 게시판 (교권보호단·교권보호전담관 등 키워드)](https://www.goe.go.kr/goe/na/ntt/selectNttList.do?mi=10102&bbsId=1922) | 2025-01 이후 게시글 | 웹 | - | 근거 자료 (config/sources.yaml boards.goe_press) |
| 경기교권보호지원센터 | [지역교권보호위원회·피해교원 보호조치·교권보호119 등 안내 8쪽](https://more.goe.go.kr/eapc/) | 수집 시점 | 웹 | - | 근거 자료, 시뮬레이션 절차 설명 |
| 경기도의회 · 프랑스 교육부 | [경기도의회 보도자료, 프랑스 교육부 공보(EMS 비교 사례)](https://www.education.gouv.fr/bo/2024/Hebdo14/MENE2409242C) | 수집 시점 | 웹 | - | 근거 자료, 비교 구조 |
| 언론 (아시아경제·한국교육신문·경인일보 등 8건) | 교권보호단 운영 보도 (`config/sources.yaml`) | 2025~2026 기사 | 웹 (분석용 로컬 캐시만, 저장소 스냅샷에는 안 넣음) | - | 사안 유입량 등 일부 가정값의 근거, 근거 자료(신뢰도 C) |
| 팀 정리 | 조직이론(Lawrence·Thompson·Perrow·Burns·Gulick·Van de Ven) 요약 (`config/seed_corpus.yaml`) | - | YAML | - | 결과 설명의 이론 근거 (신뢰도 B) |

**보조 서비스**

| 제공기관 | 데이터 | 기준일 | 형식 | 키 | 쓰이는 곳 |
|---|---|---|---|---|---|
| Anthropic | [Claude API](https://console.anthropic.com) | - | API | `ANTHROPIC_API_KEY` | 결과 설명, 사안 로그 서술, 근거 Q&A 답변 (없으면 규칙 기반 요약) |
| Google Cloud | [Cloud Translation API](https://cloud.google.com/translate) | - | API | `GOOGLE_TRANSLATE_API_KEY` | 화면 영어 번역 (선택) |

아직 없는 데이터(정보공개청구 필요): 교권보호단 유형별 접수 건수, 처리 단계별 소요일, 전담관 상근·비상근 인원과 응답률, 지역교권보호위원회 개최 간격.

## 가정값 출처

실측으로 맞춘 값은 사안 유입량(하루 약 3건: 8.24 실무 투입 후 10.8까지 140건 이상), 전담관 300명 중 대부분 비상근,
센터 예산 삭감, 2018~2020년 위원회 연 1회 내외 개최 정도입니다. 나머지(처리시간, 상근 인원 20명, 비상근 응답 비율 등)는
`sim/structures/*.yaml`과 `sim/engine.py` 상단에 가정으로 표시돼 있습니다.

## 테스트

```bash
pytest
```
