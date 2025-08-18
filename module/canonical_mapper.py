from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pathlib import Path
import json

""" 
step 정보가 들어오면, 매뉴얼을 기반으로 step에 대해서
클릭해야할 UI element 하나의 정보를 반환한다.

resolve 를 통해 호출한다.
"""

class LLMCanonicalMapper:
    def __init__(self, alias_path, graph_path, model=None):
        self.alias_path = alias_path
        self.graph_path = graph_path
        self.llm = model or ChatOpenAI(model="gpt-4o")
        self.prompt_template = ChatPromptTemplate.from_template(self._build_prompt_template())
        self.output_parser = StrOutputParser()

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
Addiionally, identify the required action type and any associated data.

For action_type:
- If the step involves clicking, tapping, or touching a UI element, use "tap".
- If the step involves simply observing or verifying changes in UI elements without interaction, use "observation".
- For all other types of user interactions (e.g., inputting text using keyboard, generating program), generate an appropriate action_type freely.
- If you are in USEPopup Screen and you are looking for Connect button, the answer is USBConnectBtn

Return your answer in JSON format, like this:
{{
  "canonical_name": "Wi-Fi Option",
  "action_type": "tap",
  "action_data": null
}}
"""

    def _load_text(self, path: str) -> str:
        return Path(path).read_text(encoding='utf-8')

    def resolve(self, step_text: str, user_input: str, current_screen: str) -> str:
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
            "current_screen": current_screen.strip()
        }).strip()