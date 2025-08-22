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

@mcp.tool()
def query_manual(test_desc: str) -> str:
    """Retrieve relevant manual contents based on the test description."""
    docs = vectorstore.similarity_search(test_desc, k=3)
    if not docs:
        return "No relevant documents found."
    return "\n\n".join(doc.page_content for doc in docs)

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

if __name__ == "__main__":
    mcp.run()