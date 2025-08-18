import asyncio
from module.log_monitor import *
from module.canonical_mapper import *
from module.cypher_generator import *
from module.log_analyzer import *
from module.neo4j_handler import *
from module.tap_executor import *
from module.step_analyzer import *
from module.ocr_evaluator import *
from action_mcp_client import run_action_agent

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
    def __init__(self, user_input = None,start_point=None):
        self.monitor = InMemoryLogMonitor()
        self.monitor.start_monitoring()
        self.monitor.setTime()
        self.mapper = LLMCanonicalMapper(
            alias_path="resource/ui_alias.json",
            graph_path="resource/graph_structure.txt"
        )
        self.start_point = None or start_point
        self.user_input = None or user_input
        self.isScreen = False
        self.neo4j = Neo4jHandler(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="neo4jneo4j",
            cypher=""
        )
        self.tap_executor = TapExecutor()
        self.step_analyzer = StepAnalyzer()

    def setMonitorTime(self):
        self.monitor.setTime()

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

    def return_to_testScreen(self, testScreen):
        #print("RETURN TO TESTSCREEN")
        finished_place = self.start_point.get("name")
        checkUIElementQuery = f"""
        MATCH (n {{name: "{finished_place}"}})
        RETURN head(labels(n)) AS label
        """

        self.neo4j.cypher = checkUIElementQuery
        query_result1, error = self.neo4j.execute_cypher()
        query_result1 = query_result1[0][0]

        #print(finished_place," ", query_result1)

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

        tap_result = self.tap_executor.tap(query_result3)
        if tap_result == False:
                self.tap_executor.tap_middle()
                return

        self.start_point = tap_result
        screen_name = self._update_start_point_from_ui(tap_result)
        self.tap_executor.tap_middle()
        
    def generate_step0(self, fromScreen, toScreen):
        toCheck = ""

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
            
            
    def get_startPoint(self):
        startPoint = self.start_point
        if startPoint == None:
            return "Home"
        else:
            return startPoint.get("name")

    def __del__(self):
        if hasattr(self, "neo4j") and self.neo4j:
            try:
                self.neo4j.close()
            except Exception as e:
                print(f"[WARN] Failed to close neo4j in destructor: {e}")

    def _observate_result(self):
        print("\n==== Observation ====")
        time.sleep(10)
        
        #print(self.monitor.get_logs())
        logs = []
        logs.append(self.monitor.search("[Msg]"))
        logs.append(self.monitor.search("Toast.Show"))
        logs.append(self.monitor.search("StartFragment :"))
        logs = [str(log) for log in logs if log is not None]
        #print(logs)
        
        analyzer = self.step_analyzer
        analyzer.analyze_observation_mode(self.step, logs=logs)

        """
        if obs_config["method"] == "log":
            logs = []
            logs.append(self.monitor.search("[Msg]"))
            logs.append(self.monitor.search("Toast.Show"))
            logs = [str(log) for log in logs if log is not None]

            self.analyzer = LogAnalyzer()
            result = self.analyzer.analyze(self.step, logs)
            print(f"Log 분석 결과: {result}")

        elif obs_config["method"] == "ocr":
            search_text = obs_config.get("search_text", "")
            ocr_text, found = OCREvaluator().perform_ocr_and_search(search_text)
            print(f"OCR 분석 결과: {found}")
        """
        """
        logs = []
        logs.append(self.monitor.search("[Msg]"))
        logs.append(self.monitor.search("Toast.Show"))
        logs = [str(log) for log in logs if log is not None]

        self.analyzer = LogAnalyzer()
        result = self.analyzer.analyze(self.step, logs)
        
        print(result)
        """

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

    async def run_step(self, step: str):
        self.step = step
        print(f"From [run_step] | Starting Point : {self.start_point}")
        #print(self.monitor.get_logs())

        canonical_place = self.start_point.get("name")
        if self.isScreen == False:
            canonical_place= self.neo4j.get_current_screen(canonical_place)

        result = self.mapper.resolve(step, self.user_input,canonical_place)
        
        resolved_instr = extract_json_from_response(result)
        
        print(f"==== Current STEP ====\n{step}")

        canonical_name = resolved_instr.get("canonical_name")
        action_type = resolved_instr.get("action_type")
        action_data = resolved_instr.get("action_data")

        print(f"Canonical Name: {canonical_name}, Action Type: {action_type}, Action Data: {action_data}")

        if action_type == "observation":
            self._observate_result()
            return action_type
        else:

            if not hasattr(self, "generator") or self.generator is None:
                self.generator = LLMCypherGenerator(
                    graph_path="resource/graph_structure.txt",
                    initial_last_clicked_ui=self.start_point
                )
            
            cypher_query = self.generator.generate(canonical_name)
            
            print("Initial Cypher Query: \n", cypher_query)
            
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
            
            avoid = None or self.start_point
            self.tap_executor = TapExecutor(avoid=avoid)
            tap_result = self.tap_executor.tap(query_result)
            if tap_result == False:
                return
            
            self.start_point = tap_result
            screen_name = self._update_start_point_from_ui(tap_result)

            if action_type != "tap":
                print("[INFO] Additional action required, calling action_mcp client...")

                ui_name = await run_action_agent(screen_name, step)

                self.start_point = {
                    "name": ui_name,
                    "x": None,
                    "y": None
                }
                screen_name = self._update_start_point_from_ui(self.start_point)

            