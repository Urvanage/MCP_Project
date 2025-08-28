from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pathlib import Path
from dotenv import load_dotenv
import os

"""
LLMCypherGenerator 모듈
- Canonical Mapper에서 알아낸 UI element를 바탕으로
  현재 화면 또는 UI element에서 클릭 경로를 찾기 위한
  Neo4j Cypher 쿼리를 생성합니다.

- update_last_clicked_ui: UI Element를 시작점으로 사용
- update_last_clicked_screen: Screen을 시작점으로 사용
- generate: 최종 쿼리 생성
"""

# .env 파일에서 환경변수 불러오기
load_dotenv()
api_key= os.getenv("OPENAI_API_KEY")

# GPT-5 LLM 초기화
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


class LLMCypherGenerator:
    """
    LLMCypherGenerator 클래스
    - graph_path: 그래프 구조 텍스트 파일 경로
    - model: LLM 객체
    - initial_last_clicked_ui: 시작점으로 사용할 UIElement
    - initial_screen: 시작점으로 사용할 Screen
    """

    def __init__(self, graph_path, model=None, initial_last_clicked_ui=None, initial_screen=None):
        self.graph_path = graph_path
        self.llm = llm
        self.prompt_template = ChatPromptTemplate.from_template(self._build_prompt_template())
        self.output_parser = StrOutputParser()
        self.last_clicked_ui = initial_last_clicked_ui
        self.current_screen = initial_screen
        self.isScreen = False

    # LLM 프롬프트 템플릿 정의
    def _build_prompt_template(self):
        return """You are an expert in Neo4j Cypher query generation.
        
Graph Schema:
{graph_structure}

Goal:
The user wants to find the (x, y) coordinates of a UIElement node named "{target_ui}", starting from {start_point_description}.

Task:
You are an expert in writing Neo4j Cypher queries for UI navigation graphs. Based on the following conditions, you will:

1. Think step-by-step and explain how to determine the correct Cypher query to get the coordinates of UIElements involved in the path.
2. Then output the final Cypher query in a code block.

Rules:

- First, write a section titled "추론:" in Korean that clearly explains your reasoning process about how the query will be formed, what assumptions are made, and how directionality and relationships are handled.
- Then, write a section titled "결과:" that contains the final Cypher query.
- The Cypher query should:
  - Find the shortest path from the given screen or UIElement to the target UIElement
  - Traverse via only the following relationships (directional, forward only): `[:CONTAINS]`, `[:TRIGGERS]`, `[:LEADS_TO]`
  - After `UNWIND`, you must use `WITH n` before using `WHERE` (Neo4j requires this)
  - Only return UIElement nodes that have both `x` and `y` coordinates (using `n.x IS NOT NULL AND n.y IS NOT NULL`)
  - Return results in path order using `apoc.coll.indexOf(nodes(path), n)`
  - Return: `n.name AS name, n.x AS x, n.y AS y`

Only return this output format:

추론:
(너의 추론 과정)

결과:
```cypher
-- 최종 Cypher 쿼리 --
    """

    def _load_text(self, path: str) -> str:
        return Path(path).read_text(encoding='utf-8')

    # 마지막 클릭한 UI Element를 시작점으로 설정
    def update_last_clicked_ui(self, ui_element: dict | None):
        self.last_clicked_ui = ui_element['name']
        self.isScreen = False

    # Screen을 시작점으로 설정
    def update_last_clicked_screen(self, screen_name):        
        self.current_screen = screen_name
        self.isScreen = True
        self.last_clicked_ui = None

    def generate(self, target_ui: str, previous_failed_queries=None) -> str:
        graph_structure = self._load_text(self.graph_path)

        # 시작점 설정 및 노드 이름 결정
        current_screen = "Home"
        if self.current_screen != None:
            current_screen = self.current_screen
        start_point_description = ""
        start_node_name = ""
        used_UIElement = self.last_clicked_ui is not None and not self.isScreen

        if self.last_clicked_ui is not None and self.isScreen == False:
            start_point_description = f"the previously clicked UI element\"{self.last_clicked_ui}\" (consider it as a UIElement node in the graph)"
            start_node_name = self.last_clicked_ui
            used_UIElement = True
        else:
            start_point_description = f"the screen \"{current_screen}\""
            start_node_name = current_screen
            used_UIElement = False

        print(f"generate() - current_screen: {self.current_screen}, isScreen: {self.isScreen}, last_clicked_ui: {self.last_clicked_ui}")

        # LLM 프롬프트 context 구성하기
        context = {
            "graph_structure": graph_structure.strip(),
            "target_ui": target_ui.strip(),
            "start_point_description": start_point_description,
        }

        # 이전 실패 쿼리가 존재하면 context에 추가
        if previous_failed_queries:
            context["graph_structure"] += (
                f"\n\nPrevious failed queries:\n" +
                "\n".join(previous_failed_queries)
            )
        else:
            # 기본 쿼리 생성 (LLM 사용하지 않음)
            start_node_label = "UIElement" if used_UIElement else "Screen"

            initialCypher = f"""
MATCH (start {{name: "{start_node_name}"}})
MATCH (target:UIElement {{name: "{target_ui}"}})
MATCH path = shortestPath((start)-[:CONTAINS|TRIGGERS|LEADS_TO*]->(target))
UNWIND nodes(path) AS n
WITH n, path
WHERE n: UIElement AND n.x IS NOT NULL AND n.y IS NOT NULL
RETURN n.name AS name, n.x AS x, n.y AS y
ORDER BY apoc.coll.indexOf(nodes(path), n)
"""
            return initialCypher

        # LLM 호출
        chain = self.prompt_template | self.llm
        response = chain.invoke(context)

        # LLM 응답에서 필요한 내용 추출
        if isinstance(response, dict) and "messages" in response:
            messages = response["messages"]
            if isinstance(messages, list):
                text_content = "".join(
                    part.get("text", "")
                    for msg in messages
                    for part in msg.get("content", [])
                )
            else:
                text_content = str(messages)
        else:
            text_content = str(response)

        return text_content.strip()