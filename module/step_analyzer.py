# file path="step_analyzer.py" (or step_analyzer copy.py)
from dotenv import load_dotenv
import os
import json # JSON 파싱을 위해 추가
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
import re

# module 경로는 실제 프로젝트 구조에 맞게 조정하세요.
# repomix-output.xml 에는 module 디렉토리가 없지만, 기존 코드 흐름상
# log_analyzer와 ocr_evaluator가 module 폴더 안에 있다고 가정합니다.
# 만약 동일 디렉토리에 있다면 'from .log_analyzer import *' 등으로 변경하거나
# 그냥 'from log_analyzer import *'로 변경해야 합니다.
from module.log_analyzer import  * #
from module.ocr_evaluator import * #

from typing import List, Optional, Tuple

load_dotenv() #
os.getenv("OPENAI_API_KEY") #



class StepAnalyzer: #
    def __init__(self, llm=None): #
        self.llm = llm or ChatOpenAI(model="gpt-4o") #
        self.log_analyzer = LogAnalyzer(self.llm) #
        self.ocr_evaluator = OCREvaluator() #

    def analyze_observation_mode(self, step_description: str, step_expected_result: str = None, logs: Optional[List[str]]= None) -> Tuple[str, str]:
        """
        관측 스텝을 분석하여 로그 또는 OCR 중 적절한 방식을 선택하고 실행합니다.
        
        - 임의의 화면으로 이동했는지 확인하는 경우에는 로그 방식을 선택하세요.
        - 대부분의 경우에는 로그 방식을, OCR 이 특정된 방식에는 OCR을 선택하세요.
        - 연결이 되었는지 확인하는 경우에는 로그 방식을 선택하세요. 
        
        Args:
            step_description (str): 현재 스텝의 설명 (e.g., "Verify the presence of 'Simulation Mode' text on the screen.")
            step_expected_result (str): 스텝의 기대 결과 (optional)

        Returns:
            tuple[str, str]: (분석 결과: 'success'/'fail'/'uncertain', 상세 메시지)
        """
        # LLM에게 어떤 분석 방식이 적절한지 묻습니다.
        logs = logs or []

        if not logs:
            logs = []
        
        analysis_decision_json_str = self._select_analysis_mode(step_description, step_expected_result)
        analysis_decision_json_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", analysis_decision_json_str.strip(), flags=re.IGNORECASE)

        try:
            decision_data = json.loads(analysis_decision_json_str)
            method = decision_data.get("method")
            search_text = decision_data.get("search_text", "")
        except json.JSONDecodeError:
            print(f"[ERROR] LLM returned invalid JSON: {analysis_decision_json_str}")
            return "uncertain", "LLM returned unparseable decision."
        
        print(f"[INFO] Analysis mode decided: {method.upper()}")

        if method == "ocr":
            if not search_text:
                print("[WARNING] OCR method selected but no search_text provided by LLM. Attempting to infer or skipping.")
                # LLM이 search_text를 주지 않았을 경우, description에서 직접 추출 시도
                text_match = re.search(r"['\"]([^'\"]+)['\"]\s*text", step_description)
                if text_match:
                    search_text = text_match.group(1)
                elif "simulation mode" in step_description.lower():
                    search_text = "Simulation Mode"
                
                if not search_text and step_expected_result: # expected_result에서도 찾아볼 수 있습니다.
                    text_match = re.search(r"['\"]([^'\"]+)['\"]\s*(?:is\s*)?(?:displayed|present|shown)", step_expected_result, re.IGNORECASE)
                    if text_match:
                        search_text = text_match.group(1)
                    elif "simulation mode" in step_expected_result.lower():
                        search_text = "Simulation Mode"


            if search_text:
                print(f"[INFO] Performing OCR for: '{search_text}'")
                full_ocr_text, found = self.ocr_evaluator.perform_ocr_and_search(search_string=search_text) #
                if found:
                    return "success", f"OCR: Found '{search_text}' on screen."
                else:
                    return "fail", f"OCR: Could not find '{search_text}' on screen. Full OCR text:\n{full_ocr_text}"
            else:
                return "uncertain", "OCR method selected but no specific text to search for."
        
        elif method == "log":
            print("[INFO] Performing log-based analysis...")
            related_logs = logs
            result = self.log_analyzer.analyze(step_description, related_logs)
            print(result)
            return result, "Log result" # 로그 분석은 StepExecutor에서 logs를 전달받아야 함.

        else:
            return "uncertain", f"Unknown analysis method: {method}"

    def _select_analysis_mode(self, step_description: str, step_expected_result: str = None) -> str: #
        # LLM 프롬프트에 step_expected_result 정보도 포함하여 더 정확한 판단을 유도합니다.
        prompt = f""" #
당신은 테스트 자동화 시스템의 결과 관측 방식을 판단하는 도우미입니다. #

다음 사용자의 작업 단계(step) 설명을 읽고, 아래 중 어떤 관측 방식이 더 적절한지 판단하세요. #
또한, OCR 방식이라면 화면에서 찾아야 할 구체적인 문자열이 무엇인지도 함께 알려주세요. #

[Step 설명] #
{step_description} #

[기대 결과]
{step_expected_result if step_expected_result else "없음"}

가능한 관측 방식:
- Log: 애플리케이션 로그 기반 판단이 가능한 경우 (예: Toast 메시지, logcat 출력, 콘솔 메시지 등)
- OCR: 화면 상 특정 텍스트나 UI 요소의 시각적 존재 여부로 판단하는 경우 (예: "로그인 성공" 텍스트, "Simulation Mode" 라벨 등)

출력은 다음 형식의 JSON으로 답변하세요:
{{
    "method": "log" 또는 "ocr" 중 하나,
    "search_text": "OCR인 경우 화면에서 찾아야 할 문자열. 문맥상 명확하게 특정 텍스트를 찾을 수 없다면 빈 문자열"
}}
"""
        response = self.llm.invoke([HumanMessage(content=prompt)]) #
        return response.content.strip()
    
