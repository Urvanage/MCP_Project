from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from dotenv import load_dotenv
import openai
import os
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# 환경 변수 로드
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# FAISS 벡터스토어 초기화
embedding = OpenAIEmbeddings()
vectorstore = FAISS.load_local(
    "conty_faiss_index",
    embedding,
    allow_dangerous_deserialization=True
)

# FastMCP 서버 초기화
mcp = FastMCP("Conty Assistant", instructions="Generate step-by-step guide from manual")

# =========================================================
# FastMCP Tool: query_manual
# - 테스트 설명(test_desc)을 기반으로 관련 매뉴얼 내용 검색
# - FAISS 벡터스토어에서 k=3개 문서 추출
# - 결과를 문자열로 반환
# =========================================================
@mcp.tool()
def query_manual(test_desc: str) -> str:
    """Retrieve relevant manual contents based on the test description."""
    docs = vectorstore.similarity_search(test_desc, k=3)
    if not docs:
        return "No relevant documents found."
    return "\n\n".join(doc.page_content for doc in docs)

# =========================================================
# FastMCP Prompt: default_prompt
# - 사용자 메시지(message)를 기반으로 단계별 가이드 생성
# - JSON 형식으로 반환하도록 지침 포함
# - 각 단계(step)는 다음 키 포함:
#   - action: 사용자 수행 동작
#   - description: 상세 설명
#   - expected_result: 기대 결과
# =========================================================
@mcp.prompt()
def default_prompt(message: str) -> list[base.Message]:
    return [
        base.AssistantMessage(
            """
You are a step-by-step guide generator for testing the Conty app.
Based on the provided manual context and user query, generate a concise and actionable step-by-step guide in JSON format.
Conty is always assumed to be already running.

Each step in your JSON array must contain the following keys. Adhere strictly to this format:
- "action": a short verb describing the user's interaction (e.g., "Input", "Click")
- "description": a clear and concise explanation of what the user should do
- "expected_result": what should be observed or expected after performing the action, if applicable
            """
        ),
        base.UserMessage(message),
    ]

# =========================================================
# 메인 실행
# - FastMCP 서버 실행
# =========================================================
if __name__ == "__main__":
    mcp.run()