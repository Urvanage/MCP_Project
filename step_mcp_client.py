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

from module.step_executor import StepExecutor

import csv
from collections import OrderedDict

def testCases_from_csv(file_path):
    test_cases = OrderedDict()

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)

        for row in reader:
            if len(row) < 4:
                continue

            test_screen = row[0].strip()
            category = row[1].strip()
            sub_category = row[2].strip()
            raw_input = row[3].strip()

            parts = [category] if category == sub_category else [category, sub_category]
            parts.append(raw_input)

            user_input = ' '.join(parts)

            key = (test_screen, user_input)
            if key not in test_cases:
                test_cases[key] = None  # 순서 유지

    return list(test_cases.keys())

DEV_MODE = True

embeddings = OpenAIEmbeddings()
faiss_vectorstore=None

load_dotenv()

os.getenv("OPENAI_API_KEY")
model = ChatOpenAI(model="gpt-4o")

server_params = StdioServerParameters(
    command="python",
    args=["./step_mcp.py"],
)

async def initialize_faiss():
    global faiss_vectorstore
    global embeddings

    faiss_index_path = "conty_faiss_index"

    if os.path.exists(faiss_index_path):
        faiss_vectorstore = FAISS.load_local(
            faiss_index_path,
            embeddings,
            allow_dangerous_deserialization=True
        )

async def save_faiss():
    global faiss_vectorstore
    if faiss_vectorstore:
        faiss_index_path = "conty_faiss_index"
        faiss_vectorstore.save_local(faiss_index_path)
        print(f"FAISS Vectorstore를 저장했습니다.")

async def feedback_loop(user_input, steps: list[dict], agent) -> list[dict]:
    print("\n Generated Steps:")
    for i, step in enumerate(steps, 1):
        print(f"{i}. ({step['action']}) {step['description']}")

    feedback = input("\n 이 Step으로 테스트 수행하겠습니까? (Enter = OK / 피드백 입력): ").strip()

    if not feedback:
        return steps
    
    prompt = f"""
You are refining the following test steps based on the feedback below.

Steps:
{json.dumps(steps, indent=2)}

Feedback:
{feedback}

Renegerate a concise and improved list of steps in JSON format.
Only include necessary steps. Improve clarity and efficiency.
    """

    edited_response = await agent.ainvoke({"messages": [{"role": "user","content": prompt}]})
    
    content = edited_response["messages"][-1].content.strip()
    match = re.search(r"```json\s*(\[\s*{.*?}\s*])\s*```", content, re.DOTALL)

    if match:
        edited_steps=json.loads(match.group(1))
        print("\n==== LLM이 수정한 Step ====")
        for i, step in enumerate(edited_steps, 1):
            print(f"{i}. ({step['action']}) {step['description']}")

        confirm_save = input("\n수정된 Step 만족 여부 (Enter = 저장 및 진행 / N = 저장하지 않고 원본 Step으로 진행): ").strip().lower()

        if confirm_save != 'n':
            global faiss_vectorstore

            if faiss_vectorstore:
                doc_content = f"User Query: {user_input}" \
                              f"Refined Steps: {json.dumps(edited_steps, indent=2, ensure_ascii=False)}"
                
                doc = Document(page_content=doc_content, metadata={
                    "query": user_input,
                    "timestamp": datetime.datetime.now().isoformat(),
                })

                faiss_vectorstore.add_documents([doc])
        
        return edited_steps
    else:
        print("수정된 JSON 블록 감지되지 않음. 원문 출력:")
        print(content)
        return steps

def change_screen_name(test_screen: str) -> str:
    if test_screen == "초기화면":
        return "Home"
    elif test_screen == "이동":
        return "Move"
    elif "설정" in test_screen:
        return "Settings"
    elif "시스템" in test_screen:
        return "System"
    elif test_screen == "프로그램":
        return "Program"
    elif test_screen == "실행":
        return "Run"

def remove_trailing_commas(json_str: str) -> str:
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    return json_str

import ast

async def run():
    await initialize_faiss()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await load_mcp_tools(session)
            agent = create_react_agent(model, tools)

            ############################################
            # 이거를 반영해서 전체적으로 생성하도록 하면 될듯
            # testList = testCases_from_csv("resource/my_tests.csv")
            # x,y = testList[0]
            #
            # test_screen = ""
            # user_input = ""
            #
            # for i in 0..len(testList):
            #    test_screen, user_input = testList[i]
            ###########################################
            
            user_input = input("질문을 입력하세요: ")
            prompts = await load_mcp_prompt(
                session, "default_prompt", arguments={"message": user_input}
            )
            response = await agent.ainvoke({"messages": prompts})

            #### steps 배열 내부에 각각마다 action / expected_result 가 존재
            print("====RESPONSE====")
            content = response["messages"][-1].content.strip()

            # JSON 블록 탐색: 완화된 정규식으로 배열 전체 추출
            #match = re.search(r"```json\s*(\[.*?\])\s*```", content, re.DOTALL)

            test_screen = change_screen_name("이동") # 이동
            start_point = "Home" # Move

            stepExecutor = StepExecutor(user_input=user_input)
            stepExecutor.setStartScreen(start_point)

            match = re.search(r"```json\s*(\[.*?\])\s*```", content, re.DOTALL)

            json_str = None
            if match:
                json_str = match.group(1)
            else:
                match = re.search(r"(\[\s*{.*?}\s*])", content. re.DOTALL)
                if match:
                    json_str = match.group(1)


            if json_str:
                try:
                    cleaned_json = remove_trailing_commas(json_str)

                    steps = json.loads(cleaned_json)

                    if DEV_MODE:
                        steps = await feedback_loop(user_input, steps, agent)
                    


                    stepExecutor.setMonitorTime()

                    if start_point != test_screen:
                        stepExecutor.generate_step0(start_point, test_screen)

                    action_type=""
                    for i, step in enumerate(steps, 1):
                        action = step.get("action", "").strip()
                        desc = step.get("description", step.get("url", "")).strip()
                        step_text = f"{i}. ({action}) {desc}"
                        action_type = await stepExecutor.run_step(step_text)

                    if action_type != "observation":
                        last_step = steps[-1]
                        expected = last_step.get("expected_result", "").strip()
                        obs_step_text = f"{len(steps)+1}. (Observe) {expected}"
                        print(obs_step_text)
                        await stepExecutor.run_step(obs_step_text)

                    stepExecutor.return_to_testScreen(test_screen)

                except (json.JSONDecodeError, SyntaxError, ValueError) as e:
                    print("JSON 파싱 실패:", e)
                    print("==== 추출된 JSON 문자열 ====")
                    print(json_str)
                    print("==== 전체 응답 원문 ====")
                    print(content)

                    print("\nJSON 파싱 실패, 수동 파싱 시도...")
                    manual_steps = []
                    object_matches = re.finditer(r"\{\s*\"action\":\s*\"(.*?)\",\s*\"description\":\s*\"(.*?)\"(?:,\s*\"expected_result\":\s*\"(.*?)\")?\s*\},?", json_str, re.DOTALL)

                    for match in object_matches:
                        action = match.group(1).strip()
                        description = match.group(2).strip()
                        expected_result = match.group(3).strip() if match.group(3) else ""

                        manual_steps.append({
                            "action": action,
                            "description": description,
                            "expected_result": expected_result
                        })

                    if manual_steps:
                        print(f"수동 파싱 성공! {len(manual_steps)}개의 스텝 추출.")

                        action_type = ""
                        for i, step in enumerate(manual_steps, 1):
                            action = step.get("action", "").strip()
                            desc = step.get("description", "").strip()
                            step_text = f"{i}. ({action}) {desc}"
                            action_type = await stepExecutor.run_step(step_text)

                        if action_type != "observation":
                            last_step = steps[-1]
                            expected = last_step.get("expected_result", "").strip()
                            obs_step_text = f"{len(steps)+1}. (Observe) {expected}"
                            print(obs_step_text)
                            await stepExecutor.run_step(obs_step_text)

                        stepExecutor.return_to_testScreen(test_screen)
                    else:
                        print("수동 파싱에도 실패했습니다. JSON 형식 분석이 필요합니다.")
            else:
                print("JSON 코드 블록 또는 배열 형식이 존재하지 않음")
                print("==== 전체 응답 원문 ====")
                print(content)
            
    await save_faiss()

asyncio.run(run())




