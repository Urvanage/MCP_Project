from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.prompts import load_mcp_prompt
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
import json
import re
from dotenv import load_dotenv
import os
import asyncio

# 환경 변수 로드
load_dotenv()
api_key= os.getenv("OPENAI_API_KEY")

# LLM 초기화 (GPT-5)
llm = ChatOpenAI(
    model="gpt-5",
    use_responses_api=True,
    output_version="responses/v1",
    extra_body={
        "text":{"verbosity":"low"},
        "reasoning":{"effort":"medium"},
    },
    api_key=api_key
)

# MCP 서버 실행 파라미터 정의
server_params = StdioServerParameters(
    command="python",
    args=["./verify_mcp.py"],
)

# =========================================================
# 비동기 함수: run_verify_agent
# - step과 expected_result를 받아 MCP 에이전트를 통해 검증 수행
# - logs, 화면 등 시각적/로그 정보 기반으로 결과 판단
# =========================================================
async def run_verify_agent(step: str, expected_result: str):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await load_mcp_tools(session)
            agent = create_react_agent(llm, tools)
            
            verify_prompt = await load_mcp_prompt(
                session, "verify_prompt",
                arguments={
                    "step": step,
                    "expected_result": expected_result
                }
            )

            try:
                verify_response = await asyncio.wait_for(agent.ainvoke({"messages": verify_prompt}), timeout=60)

                # messages[-1]은 AIMessage, content는 list[dict]
                verify_content = verify_response["messages"][-1].content

                # dict 리스트에서 "text" 값들만 모아서 합치기
                if isinstance(verify_content, list):
                    text_content = "".join(
                        part.get("text", "") for part in verify_content if isinstance(part, dict)
                    )
                else:
                    text_content = str(verify_content)

                # JSON 블록 추출
                match = re.search(r"\{.*\}", text_content, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                        res = parsed.get("result")
                        reason = parsed.get("reason")
                        tool = parsed.get("tools")
                        return res, reason
                    except json.JSONDecodeError:
                        print(f"[DEBUG] Invalid JSON content: {match.group(0)}")
                else:
                    print("[WARN] No JSON block found in LLM's verify response.")
            except asyncio.TimeoutError:
                print("[ERROR] Agent timed out after 60 seconds.")
            except Exception as e:
                print(f"[ERROR] MCP agent failed: {e}")   

            return "Error", "Error"       