from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers import JsonOutputParser
from pathlib import Path
import json
import os

""" 
step 정보가 들어오면, 매뉴얼을 기반으로 step에 대해서
클릭해야할 UI element 하나의 정보를 반환한다.

resolve 를 통해 호출한다.
"""

load_dotenv()
api_key= os.getenv("OPENAI_API_KEY")

llm = ChatOpenAI(
    model="gpt-5",
    use_responses_api=True,
    output_version="responses/v1",
    extra_body={
        "text":{"verbosity":"low"},
        "reasoning":{"effort":"low"},
    },
    api_key=api_key
)

class LLMCanonicalMapper:
    def __init__(self, alias_path, graph_path, model=None):
        self.alias_path = alias_path
        self.graph_path = graph_path
        self.llm = llm
        self.prompt_template = ChatPromptTemplate.from_template(self._build_prompt_template())
        self.output_parser = JsonOutputParser()

    def _build_prompt_template(self):
        return """You are given a user instruction step and a set of canonical UI elements with their aliases and types.

Alias Mappings:
{alias_mapping}

Graph Schema:
{graph_structure}

Original User Input:
{user_input}

Current User Step:
{step_text}

Current Screen:
{current_screen}

Question:
Which canonical UIElement or Screen name does this step refer to?
Addiionally, identify the required action type, any associated data, and the expected result after performing the action.

For action_type:
- Use only one of the following or generate a new one if necessary: "tap", "hold", "pinch", or another appropriate user action type.
- Do NOT use "observation" anymore.
- "hold" means pressing and holding the UI element until a condition occurs.
- "tap" means a single tap or click on the UI element.
- "pinch" means pinch gesture interaction
- For all other complicated action type, use that instead of simple action type

For expected_result:
- Describe what the user should see or expect after completing this step (e.g., "Popup window opens").

Return your answer in JSON format, like this:
{{
  "canonical_name": "Wi-Fi Option",
  "action_type": "tap",
  "action_data": null,
  "expected_result": {expected_result}
}}
"""

    def _load_text(self, path: str) -> str:
        return Path(path).read_text(encoding='utf-8')

    def resolve(self, step_text: str, user_input: str, current_screen: str, expected_result: str) -> str:
        alias_data = json.loads(Path(self.alias_path).read_text(encoding='utf-8'))
        graph_structure = self._load_text(self.graph_path)

        # 새로운 alias 포맷 문자열 생성
        alias_string = ""
        for canonical, entry in alias_data.items():
            type_str = entry.get("type", "Unknown")
            aliases = entry.get("aliases", [])
            alias_string += f'- {canonical} ({type_str}): {", ".join(aliases)}\n'

        # LLM 실행
        chain = self.prompt_template | self.llm | self.output_parser
        return chain.invoke({
            "alias_mapping": alias_string.strip(),
            "graph_structure": graph_structure.strip(),
            "step_text": step_text.strip(),
            "user_input": user_input.strip(),
            "current_screen": current_screen.strip(),
            "expected_result": expected_result.strip()
        })

# For testing purpose
"""
can = LLMCanonicalMapper(
    alias_path="resource/ui_alias.json",
    graph_path="resource/graph_structure.txt",
    model=llm
)

res = can.resolve("(Hold) Press and hold the '입력 위치로 이동' (Move to Target Position) button.","지정 위치 이동에서 홈 위치 선택 후 누르는동안 타겟 위치로 이동 버튼을 누르는 동안 설정된 위치로 이동하는지 확인", "Home", "Robot will be in Home Position.")
print(f"반환된 타입: {type(res)}")
print(f"Canonical Name: {res['canonical_name']}")
"""