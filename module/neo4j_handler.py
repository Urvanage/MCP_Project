from neo4j import GraphDatabase
import re
import os
from dotenv import load_dotenv

"""
Neo4jHandler 클래스
- Neo4j 데이터베이스에 접속하여 Cypher 쿼리 실행
- UI Element와 Screen 간 관계를 조회하고 마지막 클릭 UI Element의 trigger 확인 가능

주요 메서드:
- execute_cypher(): 설정된 Cypher 쿼리 실행
- check_trigger(): 마지막으로 클릭한 UI Element의 trigger 정보 확인
- get_current_screen(): 특정 노드에서 가장 가까운 화면 조회
"""

# .env 파일에서 환경 변수 로드
load_dotenv()

class Neo4jHandler:
    
    def __init__(self, uri, user, password, cypher):
        """
        초기화
        - Neo4j 드라이버 생성
        - raw Cypher 쿼리 처리
        """
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"), 
            auth=(os.getenv("NEO4J_USER"),os.getenv("NEO4J_PASSWORD")))
        self.cypher = self._extract_cypher_query(cypher)

    # 필요하다면 입력 텍스트에서 cypher 코드 블록 추출
    def _extract_cypher_query(self, raw_text):
        pattern = r"```cypher\n(.*?)\n```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        else:
            return raw_text.strip()
        
    # 새로운 cypher 쿼리 설정
    def setCypher(self, cypher):
        self.cypher = cypher

    # 현재 설정된 cypher 쿼리 실행
    def execute_cypher(self):
        try:
            with self.driver.session() as session:
                result = session.run(self.cypher)
                return result.values(), None
        except Exception as e:
            return None, str(e)
    
    # 특정 노드에서 가장 가까운 화면 조회
    def get_current_screen(self, name):
        if name in ["Home", "Settings", "Run", "Move", "System", "Program"]:
            return name
            
        query = """
        MATCH (start {name: $name}) 
        MATCH (target:Screen)
        WHERE target.name IN ["Home", "Settings", "Run", "Move", "System", "Program"]
        MATCH path = shortestPath((start)-[:CONTAINS|TRIGGERS|LEADS_TO*..10]-(target))
        RETURN target.name AS screen_name, length(path) AS distance
        ORDER BY distance ASC
        LIMIT 1
        """
        with self.driver.session() as session:
            res = session.run(query, name=name)
            record = res.single()
            if record:
                return record["screen_name"]
    
    # 마지막 클릭한 UIElement의 trigger 확인
    def check_trigger(self, result):
        if 'name' not in result:
            print("'name' key not found in the result.")
            return None
        ui_name = result['name']

        trigger_query = """
        MATCH (u:UIElement {name: $ui_name})-[:TRIGGERS]->(a:Tap|Hold)-[:LEADS_TO]-(s:Screen)
        RETURN a.name AS action_name, s.name AS screen_name
        LIMIT 1
        """
        parameters = {"ui_name": ui_name}

        with self.driver.session() as session:
            res = session.run(trigger_query, parameters)
            record = res.single()

            if record:
                return {
                    "action_name": record["action_name"],
                    "screen_name": record["screen_name"]
                }
            return None

    # Neo4j 드라이버 종료
    def close(self):
        self.driver.close()