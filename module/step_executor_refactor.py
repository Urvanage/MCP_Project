import asyncio
from module.log_monitor import *
from module.canonical_mapper import *
from module.cypher_generator import *
from module.neo4j_handler import *
from module.tap_executor import *
from module.step_analyzer import *
from action_mcp_client import run_action_agent
import subprocess
import time
import json
import re

def extract_json_from_response(raw_text: str) -> dict:
    pattern = r"```json\n(.*?)\n```"
    match = re.search(pattern, raw_text, re.DOTALL)
    if match:
        try:
            json_str = match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            raise ValueError("Invalid JSON format detected.")
    else:
        print("No JSON code block found in response.")
        raise ValueError("Response did not contain a JSON code block.")

class StepExecutor:
    def __init__(self, user_input=None, start_point=None):
        self.monitor = InMemoryLogMonitor()
        self.monitor.start_monitoring()
        self.monitor.setTime()
        self.mapper = LLMCanonicalMapper(
            alias_path="resource/ui_alias.json",
            graph_path="resource/graph_structure.txt"
        )
        self.neo4j = Neo4jHandler(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="neo4jneo4j",
            cypher=""
        )
        self.tap_executor = TapExecutor()
        self.step_analyzer = StepAnalyzer()
        self.generator = LLMCypherGenerator(graph_path="resource/graph_structure.txt")

        # 테스트 상태 및 로그 관리 변수
        self.final_status = "success"
        self.execution_log = []
        self.current_step_info = {}

        # 초기화
        self.start_point = None
        self.user_input = user_input
        self.isScreen = False
        if start_point:
            self.setStartScreen(start_point)

    def setMonitorTime(self):
        self.monitor.setTime()

    def setStartScreen(self, start_point):
        self.start_point = {
            "name": start_point,
            "x": None,
            "y": None
        }
        self.generator.update_last_clicked_screen(start_point)

    def get_startPoint(self):
        startPoint = self.start_point
        if startPoint is None:
            return "Home"
        else:
            return startPoint.get("name")

    def reset_state(self):
        """새로운 테스트 케이스를 위해 상태를 초기화합니다."""
        self.final_status = "success"
        self.execution_log = []
        self.current_step_info = {}
        # 필요한 경우 다른 변수들도 초기화
        self.monitor.setTime()

    def get_final_result(self):
        """최종 테스트 상태와 로그를 반환합니다."""
        return {
            "status": self.final_status,
            "log": "\n".join(self.execution_log)
        }

    def _update_start_point_from_ui(self, ui_name):
        check = self.neo4j.check_trigger(ui_name)
        if check is None:
            self.generator.update_last_clicked_ui(self.start_point)
            return
        
        screen_name = check.get("screen_name")
        if screen_name:
            self.start_point = {
                "name": screen_name,
                "x": None,
                "y": None
            }
            self.generator.update_last_clicked_screen(screen_name)
        else:
            self.generator.update_last_clicked_ui(self.start_point)
        
        return screen_name

    def _run_cypher_with_retry(self, canonical_name):
        max_retries = 5
        previous_failed_queries = []
         
        for attempt in range(max_retries):
            records, error = self.neo4j.execute_cypher()
            if error:
                print("Cypher Query Failed with error\n")
                previous_failed_queries.append(f"Query:\n{self.neo4j.cypher}\nError:\n{error}\n")
                print(f"[INFO] Attempt {attempt}: Requesting LLM to fix the query...")
                fixed_query = self.generator.generate(
                    canonical_name,
                    previous_failed_queries=previous_failed_queries
                )
                print("[INFO] Fixed Cypher Query:\n{fixed_query}")
                self.neo4j.cypher = self.neo4j._extract_cypher_query(fixed_query)
            else:
                print("Cypher Query Succeeded.")
                print("Query Results: ", records)
                return records
        
        print("[FAIL] Maximum retries reached without success.")
        return False

    def return_to_testScreen(self, testScreen):
        print("RETURN TO TESTSCREEN")
        finished_place = self.get_startPoint()
        
        checkUIElementQuery = f"""
        MATCH (n {{name: "{finished_place}"}})
        RETURN head(labels(n)) AS label
        """
        self.neo4j.cypher = checkUIElementQuery
        query_result1, error = self.neo4j.execute_cypher()
        
        if error or not query_result1:
            print(f"[ERROR] Neo4j query failed or no result for {finished_place}: {error}")
            self.execution_log.append(f"[FAIL] Could not determine type of {finished_place}. Aborting return to test screen.")
            self.final_status = "failed"
            return

        label = query_result1[0][0]

        if label == "Screen" and finished_place == testScreen:
            print(f"[INFO] Already at the target screen: {testScreen}")
            return
        
        if label == "UIElement":
            checkContainQuery = f"""
            MATCH (s:Screen {{name: "{testScreen}"}}), (e:UIElement {{name: "{finished_place}"}})
            RETURN exists((s)-[:CONTAINS|TRIGGERS*..]->(e)) AS isContained
            """
            self.neo4j.cypher = checkContainQuery
            query_result2, error = self.neo4j.execute_cypher()
            
            if not error and query_result2 and query_result2[0]["isContained"]:
                print(f"[INFO] {finished_place} is already contained in {testScreen}. No navigation needed.")
                return

        stepFin_Cypher = f"""
        MATCH (start:{label} {{name: "{finished_place}"}})
        MATCH (target:Screen {{name: "{testScreen}"}})
        MATCH path = shortestPath((start)-[:CONTAINS|TRIGGERS|LEADS_TO*]->(target))
        UNWIND nodes(path) AS n
        WITH n, path
        WHERE n: UIElement AND n.x IS NOT NULL AND n.y IS NOT NULL
        RETURN n.name AS name, n.x AS x, n.y AS y
        ORDER BY apoc.coll.indexOf(nodes(path), n)
        """
        self.neo4j.cypher = stepFin_Cypher
        query_result3, error = self.neo4j.execute_cypher()

        if error or not query_result3:
            print(f"[ERROR] Failed to find path to {testScreen} from {finished_place}: {error}")
            self.execution_log.append(f"[FAIL] Failed to return to test screen: {finished_place} to {testScreen}")
            self.final_status = "failed"
            return
        
        tap_result = self.tap_executor.tap(query_result3)
        if tap_result is False:
            self.execution_log.append(f"[FAIL] Tap failed while returning to test screen.")
            self.final_status = "failed"
            return

        self.start_point = tap_result
        self._update_start_point_from_ui(tap_result)
        self.execution_log.append(f"[INFO] Returned to screen: {self.get_startPoint()}")

    def generate_step0(self, fromScreen, toScreen):
        print("==== Step 0: Move to Initial Screen ====")
        self.execution_log.append(f"[INFO] Moving from {fromScreen} to {toScreen}")
        
        if toScreen == "Home":
            print("Shutting down the app")
            cmd = "adb shell am force-stop com.neuromeka.conty3"
            subprocess.run(cmd, shell=True)
            time.sleep(1)
            print("Initiate Program")
            cmd = "adb shell monkey -p com.neuromeka.conty3 -c android.intent.category.LAUNCHER 1"
            subprocess.run(cmd, shell=True)
            print("==== Step 0: Move to Initial Screen ====")
            print("==== Completed ====\n\n")
            time.sleep(6)
            self.start_point = {
                    "name": toScreen,
                    "x": None,
                    "y": None
            }
            self.isScreen = True
            return

        toCheck = "setup" if toScreen == "Settings" else toScreen.lower()

        step0_Cypher = f"""
        MATCH (start:Screen {{name: "{fromScreen}"}})
        MATCH (target:Screen {{name: "{toScreen}"}})
        MATCH path = shortestPath((start)-[:CONTAINS|TRIGGERS|LEADS_TO*]->(target))
        UNWIND nodes(path) AS n
        WITH n, path
        WHERE n: UIElement AND n.x IS NOT NULL AND n.y IS NOT NULL
        RETURN n.name AS name, n.x AS x, n.y AS y
        ORDER BY apoc.coll.indexOf(nodes(path), n)
        """
        self.neo4j.cypher = step0_Cypher
        query_result, error = self.neo4j.execute_cypher()

        if error or not query_result:
            self.execution_log.append(f"[FAIL] Step 0 failed: Could not find a path from {fromScreen} to {toScreen}. Error: {error}")
            self.final_status = "failed"
            return

        tap_result = self.tap_executor.tap(query_result)
        log = self.monitor.search("StartFragment :")

        if toCheck in log:
            print(f"==== Step 0: Move to {toScreen} Screen ====")
            print("==== Completed ====")
            self.execution_log.append(f"[INFO] Successfully moved to {toScreen} screen.")
            self.setStartScreen(toScreen)
            self.isScreen = True
        else:
            self.execution_log.append(f"[FAIL] Step 0 failed: Expected to reach {toScreen}, but got logs: {log}")
            self.final_status = "failed"

    def _observate_result(self, description):
        print(f"\n==== Observation: {description} ====")
        self.execution_log.append(f"[INFO] Observing for: {description}")
        time.sleep(10)
        
        # log와 ocr을 모두 고려하도록 로직 수정
        logs = []
        logs.append(self.monitor.search("[Msg]"))
        logs.append(self.monitor.search("Toast.Show"))
        logs = [str(log) for log in logs if log is not None]
        
        analysis_result = self.step_analyzer.analyze_observation_mode(description, logs)
        print(f"Observation Analysis Result: {analysis_result}")
        
        # 분석 결과를 기반으로 상태 업데이트
        if analysis_result == "success":
            self.execution_log.append(f"[PASS] Observation successful.")
        elif analysis_result == "failed":
            self.execution_log.append(f"[FAIL] Observation failed.")
            self.final_status = "failed"
        else:
            self.execution_log.append(f"[WARN] Observation result is uncertain.")
            self.final_status = "uncertain"

    async def run_step(self, step_text: str):
        self.current_step_info = {} # 현재 스텝 정보 초기화
        self.execution_log.append(f"\n[INFO] Executing step: {step_text}")
        print(f"From [run_step] | Starting Point : {self.get_startPoint()}")
        
        # 이미 실패 상태면 더 이상 스텝 실행하지 않음
        if self.final_status in ["failed", "uncertain"]:
            self.execution_log.append("[INFO] Skipping step due to previous failure.")
            return

        try:
            # 1. Canonical Mapping
            canonical_place = self.get_startPoint()
            if self.isScreen == False:
                canonical_place = self.neo4j.get_current_screen(canonical_place)
            
            result = self.mapper.resolve(step_text, self.user_input, canonical_place)
            resolved_instr = extract_json_from_response(result)

            canonical_name = resolved_instr.get("canonical_name")
            action_type = resolved_instr.get("action_type")
            action_data = resolved_instr.get("action_data")

            self.execution_log.append(f"[INFO] Mapped to: {canonical_name}, Action: {action_type}, Data: {action_data}")
            print(f"Canonical Name: {canonical_name}, Action Type: {action_type}, Action Data: {action_data}")
            
            # 2. Observation 스텝 처리
            if action_type == "observation":
                self._observate_result(action_data)
                return action_type
            
            # 3. Cypher Query 생성 및 실행
            cypher_query = self.generator.generate(canonical_name)
            self.neo4j.cypher = self.neo4j._extract_cypher_query(cypher_query)
            query_result = self._run_cypher_with_retry(canonical_name=canonical_name)

            if query_result is False:
                self.final_status = "failed"
                self.execution_log.append(f"[FAIL] Cypher query failed for {canonical_name}. Max retries reached.")
                return action_type
            
            # 4. Tap/Action 실행
            avoid = self.start_point
            self.tap_executor.avoid = avoid
            tap_result = self.tap_executor.tap(query_result)
            
            if tap_result is False:
                self.final_status = "failed"
                self.execution_log.append(f"[FAIL] Tap failed for {canonical_name}.")
                return action_type

            # 5. 상태 업데이트
            self.start_point = tap_result
            self._update_start_point_from_ui(tap_result)
            self.execution_log.append(f"[INFO] Action successful. Current location: {self.get_startPoint()}")

            if action_type != "tap":
                print("[INFO] Additional action required, calling action_mcp client...")
                ui_name = await run_action_agent(self.get_startPoint(), step_text)
                self.start_point = { "name": ui_name, "x": None, "y": None }
                self._update_start_point_from_ui(self.start_point)
                self.execution_log.append(f"[INFO] Additional action completed. Current location: {self.get_startPoint()}")
            
            return action_type

        except Exception as e:
            self.final_status = "failed"
            error_msg = f"[CRITICAL FAIL] An unexpected error occurred during step execution: {e}"
            self.execution_log.append(error_msg)
            print(error_msg)
            return "failed"
            
    def __del__(self):
        if hasattr(self, "neo4j") and self.neo4j:
            try:
                self.neo4j.close()
            except Exception as e:
                print(f"[WARN] Failed to close neo4j in destructor: {e}")