from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from dotenv import load_dotenv
import os
from neo4j import GraphDatabase, AsyncGraphDatabase
import subprocess
import time
import logging

# 환경 변수 로드
load_dotenv()

uri = os.getenv("NEO4J_URI")
user= os.getenv("NEO4J_USER")
password=os.getenv("NEO4J_PASSWORD")

# 로그 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =========================================================
# FastMCP 서버 초기화
# =========================================================
mcp = FastMCP("Neo4j 기반 UI Agent", instructions="""You are an intelligent agent designed to automate UI interaction of a mobile app.
    Use the Neo4j graph database to find UI elements and their relationships.
    Perform taps via adb and use OCR to read text when needed.
    Decide and explain your actions step by step.""")

# =========================================================
# FastMCP Tool 정의: find_contained_elements
# Neo4j에서 특정 화면이 포함하는 UIElement와 트리거되는 액션 정보를 조회
# =========================================================
@mcp.tool()
def find_contained_elements(screen: str):
    """Retrieve UIElements which Screen contains"""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    query = """
    MATCH (s:Screen {name: $screen_name})-[:CONTAINS]->(u:UIElement)-[:TRIGGERS]->(a:Tap|Hold)
    RETURN u.name AS ui_name, u.x AS x, u.y AS y, a.name AS action_name
    """
    _log_to_file(f"Tool 'find_contained_elements' called with screen: {screen}")
    try:
        with driver.session() as session:
            results = session.run(query, screen_name=screen)
            ui_list = []
            for record in results:
                ui_name = record["ui_name"]
                x = record["x"]
                y = record["y"]
                action_name = record["action_name"]
                
                _log_to_file(f"Fetched: name={ui_name}, x={x}, y={y}, action={action_name}")
                
                ui_list.append({
                    "ui_name": ui_name,
                    "x": x,
                    "y": y,
                    "action_name": action_name
                })

            _log_to_file(f"Tool 'find_contained_elements' returning: {ui_list}")
            return ui_list
    finally:
        driver.close()

# =========================================================
# 로그 기록 함수
# =========================================================
def _log_to_file(message: str, filename: str = 'adb_commands.txt'):
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception as e:
        print(f"Error writing to log file {filename}: {e}")

# =========================================================
# FastMCP Tool 정의: click_ui
# adb를 사용하여 지정 UI 좌표를 클릭
# =========================================================
@mcp.tool()
def click_ui(info):
    """Click the chosen UI element using adb"""
    
    _log_to_file(f"Tool 'click_ui' called with info: {info}") 

    name = info.get('ui_name', 'Unknown')
    x = info.get('x')
    y = info.get('y')

    if x is None or y is None:
        error_message=f"Skipping {name} due to missing coordinates."
        _log_to_file(f"[ERROR] {error_message}")
        return error_message

    cmd = f"adb shell input tap {x} {y}"

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        success_message = f"Tapping {name} at ({x}, {y})."
        _log_to_file(success_message)
        return success_message
    except subprocess.CalledProcessError as e:
        error_details = e.stderr.strip()
        error_message = f"Failed to tap {name} at ({x}, {y}). ADB Error: {error_details}"
        print(f"[Error] {error_message}")
        _log_to_file(f"[ERROR] {error_message}")
        return error_message

# =========================================================
# FastMCP Tool 정의: screen_description
# Neo4j에서 화면 설명/추가 지침을 비동기로 조회
# =========================================================
@mcp.tool()
async def screen_description(screen: str) -> str: # 반환 타입을 str로 명시
    """
    Retrieves the specific description for a given screen from the Neo4j graph database.

    This tool is used to fetch additional instructions or contextual information
    that is specific to a particular screen. The retrieved description can guide
    the agent's initial actions or provide important context upon entering that screen.

    Args:
        screen (str): The name of the screen for which to retrieve the description.

    Returns:
        str: The description of the screen as a plain string.
             Returns "No specific description found for this screen." if no description is present
             or "An error occurred while fetching the screen description." if an error occurs during the query.
    """
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    query = """
    MATCH (s:Screen {name: $screen_name})
    WHERE s.description IS NOT NULL
    RETURN s.description AS description
    """
    try:
        async with driver.session() as session:
            result = await session.run(query, screen_name=screen)
            record = await result.single()

            if record and record.get("description") is not None:
                return record.get("description")
            else:
                return "No specific description found for this screen."
    except Exception as e:
        print(f"Error querying screen description from Neo4j: {e}")
        return "An error occurred while fetching the screen description."
    finally:
        await driver.close()

# =========================================================
# FastMCP Prompt 정의: action_data_checker
# 주어진 액션에 대해 사용자 입력이 더 필요한지 판단
# =========================================================
@mcp.prompt()
def action_data_checker(screen_name: str, user_goal: str):
    return [
        base.AssistantMessage(
            "YOu are an assistatn that determines whether the given UI action requires additional information from the user to proceed."
            "If additional data is needed, respond with a JSON like"
            '{"needs_more_info": true, "question": "What IP address should I use?"}.'
            "Otherwise, respond with {'needs_more_info': false}."
        ),
        base.UserMessage(
            f"Screen: {screen_name}\nGoal: {user_goal}\n"
        )
    ]

# =========================================================
# FastMCP Prompt 정의: default_prompt
# 단일 단계 UI 액션을 결정
# =========================================================
@mcp.prompt()
def default_prompt(screen_name: str, user_goal: str) -> list[base.Message]:
    system_content = f"""You are a step-by-step UI automation agent interacting with a mobile app.
Your objective is to achieve the user's goal by performing a sequence of UI interactions.
You will execute actions one at a time and then observe the outcome or reassess the situation.

Given the current screen name ('{screen_name}') and the user's overarching goal ('{user_goal}'), your task is to decide the **single most appropriate next atomic step** towards the goal.

You have access to the following tools:
- find_contained_elements(screen): Returns UI elements and their actions on the given screen. Use this after a significant UI change (like a click) to get updated elements.
- click_ui(info): Tap on a UI element given its name and coordinates.
- screen_description(screen): Retrieves the specific description or initial instructions for a given screen from the Neo4j graph database.

Dont forget the press the dot when you press the IP key.

Instructions:
1. **Always start by calling `screen_description` with the current screen name** to get any additional instructions or context.
2. Then, use `find_contained_elements` to get available UI elements and their actions on the current screen.
3. If the next action is a tap, use `click_ui` to perform it.
4. **Crucially, after performing an action (e.g., a tap), consider if the user's goal is fully achieved.**
    - If the goal is fully achieved (e.g., all digits of an IP are entered, and 'confirm' is clicked, or a final state is reached), state "Goal accomplished." and **do not call any further tools.**
    - If **further actions are required** to achieve the goal, clearly state your reasoning and **the next single logical step** you plan to take. Do not attempt to complete the entire goal in one go; break it down into atomic steps.
5. **For IP address input**: You must click each digit/dot one by one. After each `click_ui` for a digit/dot, **re-evaluate the current screen state** by implicitly assuming you need to find the next element or by stating you are ready for the next iteration. Do not output all clicks in a single turn.
6. If you need to make a decision or explain why you are taking a certain action, provide your reasoning clearly before calling a tool.
"""
    return [
        base.AssistantMessage(system_content),
        base.UserMessage(f"Current Screen: {screen_name}\nUser Goal: {user_goal}"),
    ]

# =========================================================
# MCP 서버 건강 체크
# 10초마다 서버 작동 로그 기록
# =========================================================
import threading
import datetime

def mcp_health_check():
    _log_to_file(f"[HealthCheck] MCP Server is alive at {datetime.datetime.now()}")
    threading.Timer(10.0, mcp_health_check).start()

# =========================================================
# 메인: MCP 서버 실행
# =========================================================
if __name__ == "__main__":
    try:
        _log_to_file("Action MCP Server started")
        mcp_health_check() # 서버 상태 주기적 확인
        mcp.run() # FastMCP 서버 실행
    except Exception as e:
        _log_to_file(f"MCP Server Shut down. Reason: {e}")