import datetime
from langchain_core.documents import Document
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.prompts import load_mcp_prompt
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import json
import re
from langchain_community.vectorstores import FAISS

from dotenv import load_dotenv
import os

import asyncio

import csv
from collections import OrderedDict

load_dotenv()
api_key= os.getenv("OPENAI_API_KEY")

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

server_params = StdioServerParameters(
    command="python",
    args=["./verify_mcp.py"],
)

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

                #print("\n" + "="*50)
                #print("[DEBUG] Agent's raw response before parsing:")
                #print(text_content)
                #print("="*50 + "\n")

                # JSON 블록 추출
                match = re.search(r"\{.*\}", text_content, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                        res = parsed.get("result")
                        reason = parsed.get("reason")
                        tool = parsed.get("tools")
                        # print(tool)
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

async def run_analysis_agent(step: str, expected_result: str, action_type: str, canonical_name: str):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await load_mcp_tools(session)
            agent = create_react_agent(llm, tools)

            analysis_prompt = await load_mcp_prompt(
                session, "analysis_prompt",
                arguments={
                    "step": step,
                    "expected_result": expected_result,
                    "action_type": action_type,
                    "canonical_name": canonical_name
                }
            )

            try:
                analysis_response = await asyncio.wait_for(agent.ainvoke({"messages": analysis_prompt}), timeout=60)
                analysis_content = analysis_response["messages"][-1].content

                if isinstance(analysis_content, list):
                    text_content="".join(
                        part.get("text", "") for part in analysis_content
                    )
                else:
                    text_content = str(analysis_content)

                match = re.search(r"\{.*\}", text_content, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                        reason = parsed.get("failure_reason")
                        recomm = parsed.get("recommendation")
                        return reason, recomm
                    except json.JSONDecodeError:
                        print(f"[DEBUG] Invalid JSON content: {match.group(0)}")
                else:
                    print("[WARN] No JSON block found in LLM's analysis response")
            except asyncio.TimeoutError:
                print("[ERROR] Agent timed out after 60 seconds.")
            except Exception as e:
                print(f"[ERROR] MCP agent failed: {e}")

            return "Error", "Error"

#a,b = asyncio.run(run_verify_agent("Select '홈 위치' from the list as the target position.", "'홈 위치' is set as the target position."))
#print(a,"\n",b)