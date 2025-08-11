import json
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from dotenv import load_dotenv
import openai
import os
from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
import pandas as pd
import csv
from collections import defaultdict
from neo4j import GraphDatabase, AsyncGraphDatabase
import subprocess
import time
import pytesseract
from PIL import Image
import cv2

import logging

uri = os.getenv("NEO4J_URI")
user= os.getenv("NEO4J_USER")
password=os.getenv("NEO4J_PASSWORD")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# FastMCP 서버 초기화
mcp = FastMCP("Neo4j 기반 UI Agent", instructions="""You are an intelligent agent designed to automate UI interaction of a mobile app.
    Use the Neo4j graph database to find UI elements and their relationships.
    Perform taps via adb and use OCR to read text when needed.
    Decide and explain your actions step by step.""")

@mcp.tool()
def find_contained_elements(screen: str):
    """Retrieve UIElements which Screen contains"""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    query = """
    MATCH (s:Screen {name: $screen_name})-[:CONTAINS]->(u:UIElement)-[:TRIGGERS]->(a:Action)
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


def _log_to_file(message: str, filename: str = 'adb_commands.txt'):
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception as e:
        print(f"Error writing to log file {filename}: {e}")

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

@mcp.tool()
def find_and_follow_action(action: str):
    """Follow the action and find next place to start with"""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    query = """
    MATCH (a:Action {name: $action_name})-[:LEADS_TO]->(s:Screen)
    RETURN s.name AS screen_name
    """
    logging.info(f"Tool 'find_and_follow_action' called with action: {action}")

    try:
        with driver.session() as session:
            result = session.run(query, action_name = action)
            if result:
                return result["screen_name"]
            else:
                return f"No screen found for action '{action}'"
    finally:
        driver.close()

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

@mcp.tool()
def check_screen_type(screen: str):
    """Check the type of current screen, so you can decide if any additional action is needed."""
    logging.info(f"Tool 'check_screen_type' called with screen: {screen}")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    query = """
    MATCH (s:Screen {name: "IPInputKeyboard"})
    WHERE s.check_type IS NOT NULL
    RETURN
        s.name AS screen_name,
        s.check_type AS type,
        s.check_x AS x,
        s.check_y AS y,
        s.check_w AS w,
        s.check_h AS h
    """
    try:
        with driver.session() as session:
            result = session.run(query, screen_name = screen)
            return result.single()
    finally:
        driver.close()

tesseract_path = os.getenv("TESSERACT_CMD_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

@mcp.tool()
def perform_ocr(region: dict) -> str:
    x = region.get("x")
    y = region.get("y")
    w = region.get("w")
    h = region.get("h")
    
    subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
    subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
    
    image = cv2.imread("screen.png")
    cropped = image[y:y+h, x:x+w]

    pil_img = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
    text = pytesseract.image_to_string(pil_img)
    return text.strip()

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

# action_mcp.py

@mcp.prompt()
def prompt_before(screen_name: str, user_goal: str) -> list[base.Message]:
    system_content = f"""You are a step-by-step guide generator. Tell me what can you do if you are now in {screen_name} screen
You are an intelligent UI automation agent interacting with a mobile app.
You use a Neo4j graph database to query current screens and UI elements. 
You can perform taps via adb, and read text on screen using OCR when needed. 

Given the current screen name, your task is to decide the next step(s) to achieve the user's goal. 

You have access to the following tools:
- find_contained_elements(screen): Returns UI elements and their actions on the given screen.
- click_ui(info): Tap on a UI element given its name and coordinates.
- find_and_follow_action(action): Find the next screen after performing an action.
- check_screen_type(screen): Check if the screen requires OCR and get bounding box if so.
- screen_description(screen): Retrieves the specific description or initial instructions for a given screen from the Neo4j graph database.
- perform_ocr(region): Perform OCR on a specified region.

Instructions:
- If IP address input is required, the IP address string provided in the user goal should be mapped to the corresponding numeric and dot (.) keys and clicked in order.
- Never convert segments like `0.74` to `074`, and never drop the dots.
- First, **ALWAYS START by calling `screen_description` with the current screen name** to get any additional instructions or context for the current screen.
- Then, use `find_contained_elements` to get available UI elements and their actions on the current screen.
- Finally, based on the user's goal, choose the most appropriate UI element and use `click_ui` to tap it.
- Describe each step clearly and decide next steps until the goal is reached.
    """
    return [
        base.AssistantMessage(system_content),
        base.UserMessage(user_goal),
    ]



@mcp.prompt()
def default_prompt(screen_name: str, user_goal: str) -> list[base.Message]:
    system_content = f"""You are a step-by-step UI automation agent interacting with a mobile app.
Your objective is to achieve the user's goal by performing a sequence of UI interactions.
You will execute actions one at a time and then observe the outcome or reassess the situation.

Given the current screen name ('{screen_name}') and the user's overarching goal ('{user_goal}'), your task is to decide the **single most appropriate next atomic step** towards the goal.

You have access to the following tools:
- find_contained_elements(screen): Returns UI elements and their actions on the given screen. Use this after a significant UI change (like a click) to get updated elements.
- click_ui(info): Tap on a UI element given its name and coordinates.
- find_and_follow_action(action): Find the next screen after performing an action.
- check_screen_type(screen): Check if the screen requires OCR and get bounding box if so.
- screen_description(screen): Retrieves the specific description or initial instructions for a given screen from the Neo4j graph database.
- perform_ocr(region): Perform OCR on a specified region.

Instructions:
1. **Always start by calling `screen_description` with the current screen name** to get any additional instructions or context.
2. Then, use `find_contained_elements` to get available UI elements and their actions on the current screen.
3. Based on the user's goal and the available UI elements, **identify and perform only one specific next action.**
4. If the next action is a tap, use `click_ui` to perform it.
5. **Crucially, after performing an action (e.g., a tap), consider if the user's goal is fully achieved.**
    - If the goal is fully achieved (e.g., all digits of an IP are entered, and 'confirm' is clicked, or a final state is reached), state "Goal accomplished." and **do not call any further tools.**
    - If **further actions are required** to achieve the goal, clearly state your reasoning and **the next single logical step** you plan to take. Do not attempt to complete the entire goal in one go; break it down into atomic steps.
6. **For IP address input**: You must click each digit/dot one by one. After each `click_ui` for a digit/dot, **re-evaluate the current screen state** by implicitly assuming you need to find the next element or by stating you are ready for the next iteration. Do not output all clicks in a single turn.
7. If you need to make a decision or explain why you are taking a certain action, provide your reasoning clearly before calling a tool.
"""
    return [
        base.AssistantMessage(system_content),
        base.UserMessage(f"Current Screen: {screen_name}\nUser Goal: {user_goal}"),
    ]

import threading
import datetime

def mcp_health_check():
    _log_to_file(f"[HealthCheck] MCP Server is alive at {datetime.datetime.now()}")
    threading.Timer(10.0, mcp_health_check).start()

if __name__ == "__main__":
    try:
        _log_to_file("Action MCP Server started")
        mcp_health_check()
        mcp.run()
    except Exception as e:
        _log_to_file(f"MCP Server Shut down. Reason: {e}")