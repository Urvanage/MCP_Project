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

from module.step_executor_refactor import StepExecutor

import csv
from collections import OrderedDict

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

def find_json_block(content: str) -> str | None:
    match = re.search(r"```json\s*(\[.*?\])\s*```", content, re.DOTALL)
    if match:
        return match.group(1)
    
    match = re.search(r"(\[\s*{.*?}\s*])", content, re.DOTALL)
    if match:
        return match.group(1)
    
    return None

def parse_steps_from_json(json_str: str) -> list[dict] | None:
    try:
        cleaned_json = remove_trailing_commas(json_str)
        return json.loads(cleaned_json)
    except (json.JSONDecodeError, SyntaxError, ValueError) as e:
        print("JSON 파싱 실패:", e)
        return None
    
def parse_steps_manually(json_str: str) -> list[dict] | None:
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
        return manual_steps
    return None

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

async def execute_test_case(session, agent, test_screen, user_input):
    # StepExecutor 객체를 새로 생성
    stepExecutor = StepExecutor(user_input=user_input)
    stepExecutor.reset_state() # 상태 초기화
    
    prompts = await load_mcp_prompt(
        session, "default_prompt", arguments={"message": user_input}
    )
    
    response = await agent.ainvoke({"messages": prompts})
    content = response["messages"][-1].content.strip()
    
    steps = None
    json_str = find_json_block(content)

    if json_str:
        steps = parse_steps_from_json(json_str)
    
    if steps is None:
        print("JSON 파싱 실패, 수동 파싱 시도...")
        steps = parse_steps_manually(json_str)
    
    if steps is None:
        print("수동 파싱에도 실패했습니다. JSON 형식 분석이 필요합니다.")
        return {"status": "uncertain", "log": "Failed to parse steps."}
    
    if DEV_MODE:
        steps = await feedback_loop(user_input, steps, agent)

    start_point = "Home"
    screen_name = change_screen_name(test_screen)
    stepExecutor.setStartScreen(start_point)

    if start_point != screen_name:
        stepExecutor.generate_step0(start_point, screen_name)
    
    # 마지막 스텝의 action_type을 추적하기 위한 변수
    last_action_type = ""
    for i, step in enumerate(steps, 1):
        action = step.get("action", "").strip()
        desc = step.get("description", step.get("url", "")).strip()
        step_text = f"{i}. ({action}) {desc}"
        
        # run_step의 반환값(action_type)을 last_action_type에 저장
        last_action_type = await stepExecutor.run_step(step_text)
    
    # 마지막 스텝이 observation이 아닐 경우, 관찰 스텝 추가
    if last_action_type != "observation":
        last_step_index = len(steps) + 1
        last_step = steps[-1]
        expected = last_step.get("expected_result", "").strip()
        obs_step_text = f"{last_step_index}. (Observe) {expected}"
        print(obs_step_text)
        await stepExecutor.run_step(obs_step_text)
    
    stepExecutor.return_to_testScreen(screen_name)
    
    # 최종 결과 반환
    return stepExecutor.get_final_result()

async def run():
    await initialize_faiss()

    testList = testCases_from_csv("resource/my_tests.csv")
    
    output_file_path = "resource/test_results.csv"
    with open(output_file_path, 'w', newline='', encoding='utf-8') as output_file:
        fieldnames = ["test_screen", "user_input", "result", "log"]
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)
                agent = create_react_agent(model, tools)
                
                for test_screen, user_input in testList:
                    print(f"\n==== 테스트 시작: {test_screen} / '{user_input}' ====")
                    
                    # execute_test_case 함수에서 최종 결과를 받아옴
                    result = await execute_test_case(session, agent, test_screen, user_input)
                    
                    writer.writerow({
                        "test_screen": test_screen,
                        "user_input": user_input,
                        "result": result["status"],
                        "log": result["log"]
                    })
                    print(f"==== 테스트 종료: {result['status']} ====")
                    
    await save_faiss()

if __name__ == "__main__":
    asyncio.run(run())