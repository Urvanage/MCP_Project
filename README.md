# Conty AI Agent

Conty AI Agent는 Conty 애플리케이션의 테스트와 자동화를 지원하는 AI 기반 에이전트입니다. 자연어 명령을 이해해 테스트 시나리오를 자동 생성하고, 단계별 실행과 시각적 검증까지 제공합니다.

---

## 주요 기능
- **UI 자동화**
  `ADB(Android Debug Bridge)`를 통해 앱 화면을 탭하고 조작
- **시각적 검증**
  테스트 단계 실행 후 스크린샷 분석으로 예상 상태 도달 여부 확인
- **매뉴얼 기반 지식**
  매뉴얼(`resource/manual.txt`)을 벡터스토어로 변환하여 정확한 테스트 생성 지원
- **그래프 기반 UI 모델링**
  `Neo4j`를 활용해 화면(Screen), UI 요소(UIElement), 사용자 행동(Tap/Hold) 관계를 그래프 형태로 관리

---

## 설치 방법

### 1. 요구사항
- Python 3.9+
- [ADB](https://developer.android.com/studio/command-line/adb)  
- [Neo4j](https://neo4j.com/)
- [NoxPlayer](https://kr.bignox.com/)

### 2. 환경 설정
```bash
# 저장소 클론
git clone -b test-auto/final --single-branch https://gitlab.com/neuromeka-group/nrmkc/release-automation
cd AGENT

# uv 설치
pip install uv

# 가상환경 생성 및 의존성 설치
uv venv
uv pip install -r requirements.txt

# 가상환경 활성화 - Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

### 3. 환경 변수
프로젝트 루트에 .env 파일을 생성하고 아래 내용을 추가하세요:
```bash
OPENAI_API_KEY="YOUR_OPENAI_KEY"
NEO4J_URI="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="YOUR_PASSWORD"
``` 

---

## 실행 방법

### 1. Neo4j 데이터베이스
1. Neo4j Desktop 2 설치 후, **Create Instance** 버튼으로 인스턴스를 생성합니다. (이름과 비밀번호 지정)
2. 생성된 인스턴스에서 **Load database from file**을 선택하고 resource/neo4j.dump를 불러옵니다.
3. 로드가 완료되면 인스턴스를 시작하여 **RUNNING** 상태로 전환합니다.

데이터베이스의 노드/관계를 추가하거나 삭제하고 싶다면:
```bash
python app.py
```
실행 후 http://127.0.0.1:5000 웹 UI에서 관리할 수 있습니다.

### 2. NoxPlayer, ADB
1. NoxPlayer 실행 후 Conty 앱을 실행합니다.
2. ADB로 NoxPlayer에 연결합니다:
```bash
adb connect 127.0.0.1:62001
```

### 3. AI 에이전트 실행
위 준비가 끝나면, AI 에이전트를 실행합니다:
```bash
python step_mcp_client.py
```
자연어로 테스트를 입력할 수 있습니다:
```bash
(예시)
초기화면, WIFI IP 192.168.0.89 연결 확인
이동화면, 홈 위치로 이동시키기
```
추가로 설정(화면), 시스템(화면), 프로그램(화면), 실행(화면) 같은 화면도 명령에 사용할 수 있습니다.
에이전트는 단계별 실행을 진행하고 결과를 보고합니다.

---

## 기술 스택
- Python (테스트 자동화)
- Neo4j (그래프 DB 모델링)
- FAISS (매뉴얼 기반 검색)
- ADB (Android 앱 제어)
- OpenAI API (자연어 처리 + 시각적 검증)

---

## 참고
- 본 프로젝트는 Windows Powershell + uv 환경에서 테스트되었습니다.