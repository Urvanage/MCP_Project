from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from dotenv import load_dotenv
import os
import subprocess
import base64
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
from pathlib import Path
from langchain_core.messages import HumanMessage
from fastmcp import Context

# 환경 변수 로드 
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# LLM 모델 초기화 (GPT-5)
model = ChatOpenAI(
    model="gpt-5",
    use_responses_api=True,
    output_version="responses/v1",
    extra_body={
        "text": {"verbosity": "low"},
        "reasoning": {"effort": "minimal"},
    },
    api_key=api_key 
)

# =========================================================
# FastMCP 서버 초기화
# - VerifyMCP: UI 상태 및 로그 기반 검증용
# =========================================================
mcp = FastMCP("VerifyMCP", instructions="Observe the current state and determine if the previous task was completed successfully.")

# =========================================================
# ADB 스크린샷 캡처 함수
# - filename: 로컬 저장 파일명
# - adb shell screencap -> adb pull
# =========================================================
def capture_adb_screen_image(filename: str = "screen.png") -> Path:
    try:
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True, check=True)
        subprocess.run(f"adb pull /sdcard/screen.png {filename}", shell=True, check=True)
        return Path(filename)
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

# =========================================================
# 이미지 파일을 Base64 문자열로 인코딩
# =========================================================
def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# =========================================================
# LLM을 이용한 화면 상태 질의
# - question: 화면 이미지에 대해 LLM에게 물어볼 질문
# - 화면 분석 규칙 포함 (라디오 버튼, 연결 아이콘 등)
# =========================================================
def query_screen_with_llm(image_path: Path, question: str) -> str:
    if not image_path or not image_path.exists():
        raise RuntimeError("Image file does not exist.")

    # 화면 분석 규칙 설명
    descriptive_prompt = (
        "You are a precise UI analyst. You must follow this rule to determine the state of radio buttons:\n"
        "First, describe everything you see in the current screen in detail. "
        "It is a fact that one option is always selected. Based on this rule, first describe the state of each radio button, and then answer the original question:\n"
        "When checking the IP connection, determine it as connected if the connection icon is green, not the Wi-Fi icon.\n\n"
    )
    
    # 최종 질문 구성
    final_question = descriptive_prompt + question

    base64_image = encode_image_to_base64(image_path)
    image_url = f"data:image/png;base64,{base64_image}"

    # LLM용 HumanMessage 구성
    msg = HumanMessage(content=[
        {"type": "text", "text": final_question},
        {"type": "image_url", "image_url": {"url": image_url}},
    ])

    # LLM 호출
    llm = model
    res = llm.invoke([msg])

    # 응답 처리: text 형태로 반환
    if isinstance(res.content, list):
        for item in res.content:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '').strip()
    elif isinstance(res.content, str):
        return res.content.strip()

    return "No valid text content found in the response."

# =========================================================
# 로그 읽기
# - resource/log_info.txt에서 읽어옴
# =========================================================
def get_log():
    file_path = os.path.join('resource', 'log_info.txt')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return f"오류: 파일을 찾을 수 없습니다."
    except IOError as e:
        return f"파일을 읽는 중 오류가 발생했습니다: {e}"

# =========================================================
# FastMCP Tool: adb_screen_vlm
# - 화면 캡처 후 LLM을 통해 질문 응답
# - question: "현재 화면에서 xxx가 보이나요?" 등
# - 반환: {"success": bool, "answer": str}
# =========================================================
@mcp.tool()
async def adb_screen_vlm(ctx: Context, question: str) -> dict:
    """
    FastMCP Tool: ADB 화면 캡처 후 LLM(VLM) 질의
    Args:
        question (str): 화면 이미지에 대해 LLM에게 물어볼 질문
    Returns:
        dict: {"success": bool, "answer": str}
    """
    screen_file = capture_adb_screen_image()
    if not screen_file:
        return {"success": False, "answer": "Failed to capture screen."}

    try:
        answer = query_screen_with_llm(screen_file, question)
        return {"success": True, "answer": answer}
    except Exception as e:
        return {"success": False, "answer": str(e)}
    
# =========================================================
# FastMCP Tool: analyze_log
# - step, expected_result, 로그를 기반으로 성공 여부 판단
# - LLM을 이용하여 JSON 형식 결과 반환
# =========================================================
@mcp.tool()
def analyze_log(step: str, expected_result: str) -> dict:
    logs = get_log()

    prompt = f"""
    다음은 사용자가 수행한 작업 단계(step), 기대되는 결과(expected result), 
    그리고 실제 수집된 로그(logs)입니다.

    [Step 설명]
    {step}

    [기대되는 결과]
    {expected_result}

    [Log 목록]
    {logs}

    위 정보를 바탕으로, 해당 작업이 성공했는지, 실패했는지, 아니면 불확실한지 판단하세요.

    출력은 반드시 JSON 형식으로 해주세요. 
    아래와 같은 두 개의 키를 포함해야 합니다:
    - "result": "success" | "fail" | "uncertain"
    - "reason": 간단한 이유 설명
    """

    response = model.invoke([HumanMessage(content=prompt)])

    # response.content 처리
    raw_output = response.content
    if isinstance(raw_output, list):
        raw_output = "".join(item.get("text", "") for item in raw_output if isinstance(item, dict))
    raw_output = raw_output.strip()

    # JSON 부분만 추출
    import re, json
    match = re.search(r"\{.*\}", raw_output, re.DOTALL)
    if match:
        raw_output = match.group(0)

    try:
        parsed = json.loads(raw_output)
        parsed["result"] = parsed.get("result", "").lower()
        return parsed
    except Exception:
        return {
            "result": "uncertain",
            "reason": f"Failed to parse model output as JSON. Raw output: {raw_output}"
        }
    
# =========================================================
# FastMCP Prompt: verify_prompt
# - 주어진 step/expected_result를 분석하여 성공 여부 결정
# - analyze_log + adb_screen_vlm 툴 사용
# =========================================================
@mcp.prompt()
def verify_prompt(step: str, expected_result: str) -> list[base.Message]:
    system_content = f"""   
당신은 소프트웨어 테스트 검증을 수행하는 신중하고 철저한 AI 에이전트입니다.

[역할]
- step은 이미 실행된 상태입니다.
- expected_result는 step이 성공했을 때 기대되는 결과입니다.
- 당신의 임무는 주어진 정보와 툴을 활용하여 expected_result가 충족되어는지 검증하는 것입니다.
- 검증은 보수적으로 접근해야 하며, 성공이 100% 확실하지 않은 모든 경우에는 교차 검증을 통해 재확인 해야 합니다.

[사용 가능한 툴]
1. analyze_log(step, expected_result)
- 로그 정보를 기반으로 'success' | 'fail' | 'uncertain'을 판단합니다.
- 안드로이드 시스템 내부 동작을 확인하는 데 유용합니다.

2. adb_screen_vlm(question)
- 현재 화면의 스크린샷을 분석하여 expected_result가 시각적으로 나타나는지 확인합니다.
- 실제 사용자 관점의 UI 상태를 확인하는 데 결정적입니다.

[행동 지침]
1. 로그 분석
- 먼저 analyze_log 툴을 호출하여 결과를 확인합니다.

2. 조건부 교차 검증
- analyze_log의 결과가 'success'가 아닐 경우, 당신은 반드시 adb_screen_vlm 툴을 추가로 호출하여 시각적 교차 검증을 수행해야 합니다.

3. 최종 결론 종합
- 두 가지 툴의 결과를 종합하여 최종 결론을 내립니다.
- adb_screen_vlm의 결과가 'success'라면, 최종 결과를 'success'라고 판단할 수 있습니다.
- 두 툴 모두에서 성공을 확인할 수 없는 경우에만 최종 결과를 'fail'로 확정합니다.    

[추가 정보]
- Wi-Fi 팝업은 '로봇 연결하기' 화면입니다. Wi-Fi Popup 화면이 열렸는지 확인하는 경우에만 이 정보를 추가로 고려해주세요.

[최종 출력]
- 반드시 아래 JSON 형식으로 답변해야 합니다.
- "result" 값은 success | fail | uncertain 중 하나여야 합니다.
- "reason"은 어떤 근거로 최종 결론을 내렸는지 사람이 이해할 수 있도록 설명해야 합니다.
- "tools"에는 너가 호출한 tool 정보와 어떤 응답을 받았는지에 대한 정보를 순서대로 알려줘야 합니다.

{{
    "result": "success" | "fail" | "uncertain",
    "reason": "간단한 이유 설명",
    "tools": "호출한 툴 순서대로 작성"
}}
    """
    return [
        base.AssistantMessage(system_content),
        base.UserMessage(f"Current Step: {step}\nExpected Result: {expected_result}\n"),
    ]

# =========================================================
# 메인 실행
# - FastMCP 서버 실행
# =========================================================
if __name__ == "__main__":
    mcp.run()
