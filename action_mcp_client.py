from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.prompts import load_mcp_prompt
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
import json
import re

from langchain_core.runnables import Runnable
from langchain_core.runnables.config import RunnableConfig

from dotenv import load_dotenv
import os

import asyncio

from uuid import uuid4
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from typing import Any

load_dotenv()
openAPI = os.getenv("OPENAI_API_KEY")

"""
llm = ChatOpenAI(
    model="gpt-5",
    use_responses_api=True,
    output_version="responses/v1",
    extra_body={
        "text":{"verbosity":"low"},
        "reasoning": {"effort": "low"},
    },
    api_key = openAPI
)
model = TextLLM(llm)
"""

model = ChatOpenAI(model="gpt-4o")

server_params = StdioServerParameters(
    command="python",
    args=["./action_mcp.py"],
    stdout=None,
    stderr=None
)

import asyncio

async def run_action_agent(screen_name: str, user_goal: str):
    print("[Client] Starting run_action_agent...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            agent = create_react_agent(model, tools)

            need_more_info = False
            user_question = None

            action_data_check_prompt = await load_mcp_prompt(
                session, "action_data_checker",
                arguments={
                    "screen_name": screen_name,
                    "user_goal": user_goal
                }
            )

            try:
                check_response = await asyncio.wait_for(agent.ainvoke({"messages": action_data_check_prompt}), timeout=60)
                check_content = check_response["messages"][-1].content.strip()
                #check_ai_msg = check_response["messages"][-1]
                #check_content = _text_or_raw(check_ai_msg.content)  # 문자열로 변환
                #match = re.search(r"\{.*?\}", check_content)
                match = re.search(r"\{.*?\}", check_content)
                
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                        need_more_info = parsed.get("needs_more_info", False)
                        user_question = parsed.get("question")
                        print(f"[Client] Parsed data check: needs_more_info={need_more_info}, question={user_question}")
                    except json.JSONDecodeError:
                        print("[ERROR] LLM did not return valid JSON. Assuming no extra info is needed.")
                        print(f"[DEBUG] Invalid JSON content: {match.group(0)}")
                        # 파싱 실패 시 안전한 기본값으로 설정
                        need_more_info = False
                        user_question = None
                else:
                    # JSON 블록을 찾지 못한 경우
                    print("[WARN] No JSON block found in LLM's data check response.")
                    need_more_info = False
                    user_question = None

                if need_more_info and user_question:
                    user_input = input(f"[Question] {user_question}\n[Answer] ").strip()
                    if user_input:
                        user_goal = f"{user_goal} (User Input: {user_input})"
                        print(f"[Client] User input received. Updated goal: {user_goal}")

            except asyncio.TimeoutError:
                print("[ERROR] Agent data check timed out after 60 seconds.")
                return None
            except Exception as e:
                print(f"[ERROR] MCP agent data check failed: {e}")
                return None

            # === 주 목표 달성을 위한 반복 실행 루프 시작 ===
            goal_achieved = False
            max_iterations = 20 # 무한 루프 방지를 위한 최대 반복 횟수 설정 (필요에 따라 조정)
            current_ui_name_tapped = None # 마지막으로 탭한 UI 이름 저장

            for i in range(max_iterations):
                if goal_achieved:
                    print("[Client] User goal achieved. Exiting agent loop.")
                    break

                print(f"\n[Client] Iteration {i+1}/{max_iterations}: Invoking agent for main goal...")
                prompts = await load_mcp_prompt(
                    session, "default_prompt",
                    arguments={
                        "screen_name": screen_name,
                        "user_goal": user_goal
                    }
                )

                try:
                    # 에이전트 호출에 타임아웃 적용
                    response = await asyncio.wait_for(agent.ainvoke({"messages": prompts},config={"recursion_limit": 100}), timeout=120) # 주 목표 에이전트 타임아웃 120초
                    print(f"[Client] Agent main goal invoked (Iteration {i+1}). Processing response.")

                    llm_ans = response["messages"][-1].content.strip()
                    #llm_ans = response["messages"][-1]
                    print("==== AGENT RESPONSE (Iteration {}) ====".format(i+1))
                    print(llm_ans)
                    print("====================================")

                    # LLM의 마지막 응답을 분석하여 목표 달성 여부 판단
                    # 에이전트가 "Goal accomplished."와 같은 최종 메시지를 반환하도록 프롬프트에서 지시할 것임.
                    if "Goal accomplished." in llm_ans or "No further actions" in llm_ans: # 예시 조건, 에이전트의 실제 응답에 맞춰 수정
                         goal_achieved = True
                         print("[Client] Agent indicated goal accomplished.")

                    # click_ui ToolMessage 처리 및 다음 반복을 위해 함수 종료하지 않음
                    found_click_ui = False
                    for message in reversed(response['messages']):
                        if hasattr(message, 'name') and message.name == 'click_ui':
                            last_tool_message_content = message.content
                            #last_tool_message_content = message
                            start_index = last_tool_message_content.find("Tapping ") + len("Tapping ")
                            end_index = last_tool_message_content.find(" at (")
                            if start_index != -1 and end_index != -1:
                                current_ui_name_tapped = last_tool_message_content[start_index:end_index].strip()
                                print(f"[Client] Found click_ui ToolMessage. Tapped UI: {current_ui_name_tapped}")
                                found_click_ui = True
                                break
                            else:
                                print("[Client] Could not parse ui_name from the last ToolMessage content.")
                                break
                    
                    if not found_click_ui and not goal_achieved:
                        print("[Client] No 'click_ui' ToolMessage found in this response and goal not achieved. Agent might be reasoning or stuck.")
                        # 이 경우, 에이전트가 다음 행동을 결정하지 못했거나 추가 정보가 필요할 수 있음.
                        # 필요하다면 여기에 추가적인 프롬프트 조정 또는 오류 처리 로직을 넣을 수 있음.
                        # 예: LLM이 "need more info"와 유사한 응답을 줬는지 확인
                        pass # 다음 반복으로 넘어감

                except asyncio.TimeoutError:
                    print(f"[ERROR] Agent main goal timed out after 120 seconds in iteration {i+1}.")
                    break # 타임아웃 발생 시 루프 종료
                except Exception as e:
                    print(f"[ERROR] MCP agent invoke failed in iteration {i+1}: {e}")
                    break # 예외 발생 시 루프 종료

            if not goal_achieved:
                print(f"[Client] Max iterations ({max_iterations}) reached without achieving goal.")
            
            print("[Client] run_action_agent finished.")
            return current_ui_name_tapped # 마지막으로 탭한 UI 요소를 반환
        

# asyncio.run(run_action_agent("IPInputKeyboard", "Enter '192.168.0.89' in the IP input field."))