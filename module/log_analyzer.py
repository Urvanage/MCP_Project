from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage

load_dotenv()
os.getenv("OPENAI_API_KEY")


"""
LogAnalyzer 는 adb logcat 명령을 통해 LogMonitor 가 받아온
로그를 분석한다.

현재는 단순 Toast 메시지나 [Msg] 메시지를 통해 성공 실패를 분석하지만
차후에는 좀 더 상세하게 분석하는 경우를 추가할 수 있다.

analyze 호출을 통해 분석한다.

"""

class LogAnalyzer:
    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(model="gpt-4o")

    def analyze(self, step, logs: list[str]) -> str:
        prompt = f"""
    다음은 사용자가 수행한 작업 단계(step)와 그 이후 수집된 로그(logs)입니다.

    [Step 설명]
    {step}

    [Log 목록]
    {chr(10).join(logs)}

    이 로그들 중 step과 관련된 내용이 있다면 그것을 바탕으로 해당 작업이 '성공(success)'했는지 '실패(fail)'했는지 판단해주세요.
    만약 관련된 로그가 없거나 판단이 어렵다면 'uncertain'을 반환하세요.

    출력은 아래 중 하나만 정확히 선택해서 간단한 이유와 함께 출력하세요:
    - Success
    - Fail
    - Uncertain
    """
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip().lower()