from module.log_monitor import *
from module.canonical_mapper import *
from module.cypher_generator import *
from module.neo4j_handler import *
from module.tap_executor import *
from action_mcp_client import run_action_agent
from verify_mcp_client import run_verify_agent

load_dotenv()

# LLM 응답에서 JSON 블록을 안전하게 추출
def extract_json_from_response(raw_text: str) -> dict:
    pattern = r"```json\n(.*?)\n```"
    match = re.search(pattern, raw_text, re.DOTALL)
    if match:
        try:
            json_str= match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            raise ValueError("Invalid JSON format detected.")
    else:
        print("No JSON code block found in response.")
        raise ValueError("Response did not contain a JSON code block.")

class StepExecutor:
    def __init__(self, monitor: InMemoryLogMonitor, user_input = None,start_point=None):
        # 로그 모니터, canonical mapper, Neo4j handler, TapExecutor 초기화
        self.monitor = monitor
        self.mapper = LLMCanonicalMapper(
            alias_path="resource/ui_alias.json",
            graph_path="resource/graph_structure.txt"
        )
        self.start_point = None or start_point # 현재 시작 위치(UI 또는 화면)
        self.user_input = None or user_input # 사용자 입력
        self.isScreen = False # start_point가 화면인지 여부
        self.neo4j = Neo4jHandler( # Neo4j 연결 초기화
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD"),
            cypher=""
        )
        self.tap_executor = TapExecutor() # ADB 탭/홀드 실행기
        self.step_passed = True # step 성공 여부 초기화
    
    # 로그 모니터 시작 시간 설정
    def setMonitorTime(self):
        self.monitor.setTime()

    # 현재 step 성공 여부 초기화
    def resetState(self):
        self.step_passed=True

    # 테스트 시작 화면 설정
    def setStartScreen(self, start_point):
        self.start_point = {
            "name": start_point,
            "x": None,
            "y": None
        }

        if not hasattr(self, "generator") or self.generator is None:
            self.generator = LLMCypherGenerator(
                graph_path="resource/graph_structure.txt",
                initial_screen=start_point
            )
        else:
            self.generator.update_last_clicked_screen(start_point)

    # 테스트 시작 화면으로 이동
    def return_to_testScreen(self, testScreen):
        finished_place = self.start_point.get("name")

        # 현재 위치의 Label 확인
        checkUIElementQuery = f"""
        MATCH (n {{name: "{finished_place}"}})
        RETURN head(labels(n)) AS label
        """

        self.neo4j.cypher = checkUIElementQuery
        query_result1, error = self.neo4j.execute_cypher()
        query_result1 = query_result1[0][0]

        # UIElement인 경우, testScreen과 포함 관계 확인
        if query_result1 == "UIElement":
            checkContainQuery = f"""
            MATCH (s:Screen {{name: "{testScreen}"}}), (e:UIElement {{name: "{finished_place}"}})
            MATCH path = (s)-[:CONTAINS|TRIGGERS*..]->(e)
            RETURN COUNT(path) > 0 AS isContained
            """
            self.neo4j.cypher = checkContainQuery
            query_result2, error = self.neo4j.execute_cypher()
            
            if query_result2 == True:
                self.tap_executor.tap_middle()
                return
        
        # UIElement -> Screen 최단경로 계산
        stepFin_Cypher = f"""
            MATCH (start:{query_result1} {{name: "{finished_place}"}})
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

        # TapExecutor를 통해 화면 이동
        tap_result = self.tap_executor.tap(query_result3)
        if tap_result == False:
                self.tap_executor.tap_middle()
                return

        # start_point 갱신
        self.start_point = tap_result
        screen_name = self._update_start_point_from_ui(tap_result)
        self.tap_executor.tap_middle()
        
    # 현재 화면과 테스트 시작 화면이 다른 경우, 테스트 시작 화면으로 이동
    def generate_step0(self, fromScreen, toScreen):
        toCheck = ""

        if toScreen == "Home":
            # 앱 종료 후 재실행
            print("Shutting down the app")
            cmd = "adb shell am force-stop com.neuromeka.conty3"
            subprocess.run(cmd, shell=True)
            time.sleep(1)
            print("Initiate Program")
            cmd = "adb shell monkey -p com.neuromeka.conty3 -c android.intent.category.LAUNCHER 1"
            subprocess.run(cmd, shell=True)
            print("==== Step 0: Move to Initial Screen ====")
            print("==== Completed ====\n\n")
            time.sleep(8)
            self.start_point = {
                    "name": "Home",
                    "x": None,
                    "y": None
            }
            self.isScreen = True
            return
        elif toScreen == "Settings":
            toCheck = "setup"
        else:
            toCheck = toScreen.lower()

        # Neo4j shortestPath 쿼리 생성
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
        if not hasattr(self, "neo4j") or self.neo4j is None:
            self.neo4j = Neo4jHandler(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="neo4jneo4j",
                cypher=step0_Cypher
            )
        else:
            self.neo4j.cypher = step0_Cypher

        # Cypher 실행
        query_result, error = self.neo4j.execute_cypher()
        if query_result:
            self.tap_executor = TapExecutor()
            tap_result = self.tap_executor.tap(query_result)
            log = self.monitor.search("StartFragment :")
            if log and toCheck in log:
                print(f"==== Step 0: Move to {toScreen} Screen ====")
                print("==== Completed ====")

                self.start_point = {
                    "name": toScreen,
                    "x": None,
                    "y": None
                }
                if not hasattr(self, "generator") or self.generator is None:
                    self.generator = LLMCypherGenerator(
                        graph_path="resource/graph_structure.txt",
                        initial_screen=toScreen
                    )
                else:
                    self.generator.update_last_clicked_screen(toScreen)

    # 현재 시작점 반환       
    def get_startPoint(self):
        startPoint = self.start_point
        if startPoint == None:
            return "Home"
        else:
            return startPoint.get("name")

    # 마지막으로 실행한 step의 결과 반환
    def get_finalResult(self):
        finalResult = self.total_result
        self.total_result = {}
        return finalResult

    # Neo4j 연결 종료
    def __del__(self):
        if hasattr(self, "neo4j") and self.neo4j:
            try:
                self.neo4j.close()
            except Exception as e:
                print(f"[WARN] Failed to close neo4j in destructor: {e}")

    # Observation 수행
    async def _observate_result(self, step, expected_result):
        print("\n==== Observation ====")
        print(f"Expected Result: {expected_result}")
        self.monitor.save_log()
        time.sleep(1)

        # Verify MCP 에이전트 실행
        res, reason = await run_verify_agent(step, expected_result)
        if res=="Error":
            print("[ERROR] Observation Error Occurred")
            return
        
        print(f"Observation Result: {res}\nReason: {reason}")
        if res.lower()=="fail":
            self.step_passed = False # 현재 step 성공 여부
        
        self.total_result = {"step": step, "result": res}

        self.monitor.setTime()

    # Cypher 실행 후 실패 시 LLM으로 재생성
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

    # UI 클릭 후 start_point 업데이트
    def _update_start_point_from_ui(self, ui_name):
        check = self.neo4j.check_trigger(ui_name)
        if check == None:
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

    # 단일 Step 실행
    async def run_step(self, step: str, expected_result: str):
        if self.step_passed == False:
            return 
        
        self.step = step

        canonical_place = self.start_point.get("name")
        if self.isScreen == False:
            canonical_place= self.neo4j.get_current_screen(canonical_place)

        # canonical name, action_type, action_data, expected_result 확인
        result = self.mapper.resolve(step, self.user_input,canonical_place, expected_result)
        resolved_instr= result
        print(resolved_instr)
        
        print(f"==== Current STEP ====\n{step}")
        canonical_name = resolved_instr.get("canonical_name")
        action_type = resolved_instr.get("action_type")
        action_data = resolved_instr.get("action_data")
        expected_result = resolved_instr.get("expected_result")

        print(f"Canonical Name: {canonical_name}, Action Type: {action_type}, Action Data: {action_data}, Expected Result: {expected_result}")

        if not hasattr(self, "generator") or self.generator is None:
            self.generator = LLMCypherGenerator(
                graph_path="resource/graph_structure.txt",
                initial_last_clicked_ui=self.start_point
            )

        # Cypher 생성 및 실행
        cypher_query = self.generator.generate(canonical_name)
                    
        if not hasattr(self, "neo4j") or self.neo4j is None:
            self.neo4j = Neo4jHandler(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="neo4jneo4j",
                cypher=cypher_query
            )
        else:
            self.neo4j.cypher = self.neo4j._extract_cypher_query(cypher_query)
        
        query_result = self._run_cypher_with_retry(canonical_name=canonical_name)
        
        if query_result == False:
            self.neo4j.close()
            return
        
        # TapExecutor 실행
        avoid = None or self.start_point
        self.tap_executor = TapExecutor(avoid=avoid)

        if action_type == "hold":
            tap_result = self.tap_executor.hold(query_result)
        else:
            tap_result = self.tap_executor.tap(query_result)
        
        if tap_result is False:
            return
        
        # start_point 및 화면 갱신
        self.start_point = tap_result
        screen_name = self._update_start_point_from_ui(tap_result)

        # 추가 action 필요 시 MCP 호출
        if action_type not in ["tap", "hold"]:
            print("[INFO] Additional action required, calling action_mcp client...")
            ui_name = await run_action_agent(screen_name, step)
            self.start_point = {
                "name": ui_name,
                "x": None,
                "y": None
            }
            screen_name = self._update_start_point_from_ui(self.start_point)

        # Observation 수행
        await self._observate_result(step, expected_result)     