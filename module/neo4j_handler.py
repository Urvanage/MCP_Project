from neo4j import GraphDatabase
import re
import os
from dotenv import load_dotenv

"""
Neo4j DB를 통해서 생성된 cypher 쿼리를 실행할 수 있다.

execute_cypher 를 통해서 호출한다.
check_trigger 를 통해서 마지막으로 클릭한 UI Element의 trigger를 확인한다.
"""
load_dotenv()

# TODO 
# 이를 사용해서 차후에 DB 업데이트나 추가를 간단히 할 수 있는 함수 만들기
# 예를 들어 사용자가 Screen 와 UI Element 를 추가하고 action 추가하면
# 이를 기반으로 반복문을 통해서 쿼리를 쉽게 업데이트 할 수 있도록 하기

class Neo4jHandler:
    def __init__(self, uri, user, password, cypher):
        self.driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"),os.getenv("NEO4J_PASSWORD")))
        self.cypher = self._extract_cypher_query(cypher)

    def _extract_cypher_query(self, raw_text):
        pattern = r"```cypher\n(.*?)\n```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        else:
            return raw_text.strip()
        
    def setCypher(self, cypher):
        self.cypher = cypher

    def execute_cypher(self):
        try:
            with self.driver.session() as session:
                result = session.run(self.cypher)
                return result.values(), None
        except Exception as e:
            return None, str(e)
        
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
        
    def check_trigger(self, result):
        if 'name' not in result:
            print("'name' key not found in the result.")
            return None
        ui_name = result['name']

        trigger_query = """
        MATCH (u:UIElement {name: $ui_name})-[:TRIGGERS]->(a:Action)-[:LEADS_TO]-(s:Screen)
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

    def close(self):
        self.driver.close()


#n4 = Neo4jHandler("","","","")
#res = n4.get_current_screen("VirtualBtn")
#print(res)