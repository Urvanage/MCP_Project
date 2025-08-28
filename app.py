from flask import Flask, render_template, request, jsonify
from module.neo4j_handler import *
import json
import os

# Flask 앱 생성
app = Flask(__name__)

# Neo4jHandler 초기화
n4 = Neo4jHandler(
    uri=os.getenv("NEO4J_URI"),
    user=os.getenv("NEO4J_USER"),
    password=os.getenv("NEO4J_PASSWORD"),
    cypher=""
)

json_file = "resource/ui_alias.json"
data = {}

# 노드 존재 여부 확인
def check_if_exist(node, name):
    checking_cypher = f"""
    MATCH (n:{node} {{name: "{name}"}})
    RETURN n
    """
    n4.setCypher(checking_cypher)
    result, error = n4.execute_cypher()
    return result is not None and len(result) > 0

# Neo4j 노드 생성 / 업데이트
def update_neo4j(node, name, properties=None):
    props = [f'name: "{name}"']
    if properties:
        for key, value in properties.items():
            if isinstance(value, str):
                props.append(f'{key}: "{value}"')
            else:
                props.append(f'{key}: {value}')
    props_string = ", ".join(props)
    updating_cypher = f"""CREATE (n:{node} {{{props_string}}})"""
    n4.setCypher(updating_cypher)
    result, error = n4.execute_cypher()
    return not error

# Neo4j에서 Tap, Hold, Screen, UIElement 목록 가져오기
def get_list():
    cyphers = {
        "tap": "MATCH (n:Tap) RETURN n.name",
        "hold": "MATCH (n:Hold) RETURN n.name",
        "screen": "MATCH (n:Screen) RETURN n.name",
        "uielement": "MATCH (n:UIElement) RETURN n.name"
    }
    lists = {}
    for key, cypher in cyphers.items():
        n4.setCypher(cypher)
        result, error = n4.execute_cypher()
        if error:
            lists[key] = []
        else:
            lists[key] = [item[0] for item in result]
    return lists["tap"], lists["hold"], lists["screen"], lists["uielement"]

# UI alias 삭제
def delete_ui_alias(name, type):
    global data
    if os.path.exists(json_file):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        return

    if name in data and data[name].get("type") == type:
        del data[name]
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    return False

# Neo4j 노드 삭제
def delete_node(node_name, node_type):
    if check_if_exist(node_type, node_name) == False:
        return False, f"[실패] {node_type}('{node_name}') 노드는 존재하지 않습니다."

    deleting_cypher = f"""
    MATCH (n:{node_type} {{name: "{node_name}"}})
    DETACH DELETE n
    """

    n4.setCypher(deleting_cypher)
    result, error = n4.execute_cypher()

    if error:
        return False, f"[에러 발생] {error}"

    message = f"노드 '{node_name}' 및 연결된 모든 관계가 성공적으로 삭제되었습니다."
    return True, message

# Neo4j 관계 삭제
def delete_relationship(reltype, n1name, n1type, n2name, n2type):
    deleting_relationship_cypher = f"""
    MATCH (a:{n1type} {{name: "{n1name}"}})-[r:{reltype}]->(b:{n2type} {{name: "{n2name}"}})
    DELETE r
    RETURN COUNT(r)
    """

    n4.setCypher(deleting_relationship_cypher)
    result, error = n4.execute_cypher()

    if error:
        return False, f"[에러 발생] {error}"

    if result and isinstance(result, list) and len(result) > 0:
        deleted_count = result[0][0] if result[0] else 0
        if deleted_count > 0:
            return True, f"[성공] 관계 '{n1name}' -[:{reltype}]-> '{n2name}'가 삭제되었습니다."
        else:
            return False, f"[실패] '{n1name}' -[:{reltype}]-> '{n2name}' 관계가 존재하지 않습니다."
    else:
        return False, "[실패] 관계가 존재하지 않거나 예상치 못한 결과 형식입니다."

# 노드 속성 조회
def get_node_properties(node_name, node_type):
    property_cypher = f"""
    MATCH (n:{node_type} {{name:"{node_name}"}})
    RETURN properties(n)
    """
    n4.setCypher(property_cypher)
    res, err = n4.execute_cypher()
    if err or not res:
        return None
    return res[0][0]

# 노드 속성 업데이트
# - new_props: 업데이트할 속성
# - remove_props: 제거할 속성
def update_node_properties(node_name, node_type, new_props, remove_props):
    set_clauses = []
    remove_clauses = []
    
    if new_props:
        for k, v in new_props.items():
            if isinstance(v, (int, float, bool)):
                set_clauses.append(f"n.{k} = {v}")
            else:
                set_clauses.append(f"n.{k} = {json.dumps(v, ensure_ascii=False)}")
    
    if remove_props:
        for prop_key in remove_props:
            remove_clauses.append(f"n.{prop_key}")
            
    cypher_parts = [f'MATCH (n:{node_type} {{name: "{node_name}"}})']
    
    if set_clauses:
        cypher_parts.append(f'SET {", ".join(set_clauses)}')

    if remove_clauses:
        cypher_parts.append(f'REMOVE {", ".join(remove_clauses)}')
    
    if not set_clauses and not remove_clauses:
        return False, "변경할 속성이 없습니다."

    update_property_cypher = "\n".join(cypher_parts)
    n4.setCypher(update_property_cypher)
    res, err = n4.execute_cypher()
    
    if err:
        return False, f"노드 속성 업데이트 중 오류: {err}"
    else:
        return True, f"노드 '{node_name}'의 속성이 성공적으로 업데이트되었습니다."

# =========================================================
# Flask 라우트 정의
# =========================================================

# 메인 페이지
@app.route('/')
def index():
    return render_template('index.html')

# 노드 생성
@app.route('/create_node', methods=['POST'])
def create_node_web():
    global data
    if os.path.exists(json_file):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    node_type = request.form['node_type']
    node_name = request.form['node_name']
    
    if node_type == "Action": # Action 타입 선택 시 하위 타입 사용
        node_type = request.form['action_subtype']

    # 이미 존재하면 생성 불가
    if check_if_exist(node_type, node_name):
        return jsonify({"success": False, "message": f"'{node_name}' ({node_type}) 노드가 이미 존재합니다."})

    properties = {}
    if node_type == "UIElement":
        properties['x'] = int(request.form['x_coord'])
        properties['y'] = int(request.form['y_coord'])
    
    custom_props = request.form.get('custom_properties', '{}')
    custom_props = json.loads(custom_props)
    properties.update(custom_props)

    if update_neo4j(node_type, node_name, properties):
        aliases = request.form.get('aliases', '').split(',')
        data[node_name] = {"type": node_type, "aliases": [alias.strip() for alias in aliases if alias.strip()]}
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return jsonify({"success": True, "message": f"'{node_name}' ({node_type}) 노드가 성공적으로 생성되었습니다."})
    else:
        return jsonify({"success": False, "message": "Neo4j 노드 생성 중 오류가 발생했습니다."})

# 관계 생성
@app.route('/create_relation', methods=['POST'])
def create_relation_web():
    source_type = request.form['source_type']
    source_name = request.form['source_name']
    target_type = request.form['target_type']
    target_name = request.form['target_name']
    
    if not check_if_exist(source_type, source_name):
        return jsonify({"success": False, "message": f"오류: 시작 노드 '{source_name}' ({source_type})가 존재하지 않습니다."})

    # Tap/Hold 관계 노드 없으면 생성
    if target_type in ["Tap", "Hold"]:
        if not check_if_exist(target_type, target_name):
            update_neo4j(target_type, target_name)
    elif not check_if_exist(target_type, target_name):
        return jsonify({"success": False, "message": f"오류: 대상 노드 '{target_name}' ({target_type})가 존재하지 않습니다."})

    # 관계 타입 자동 결정
    relation_type = None
    if source_type == "Screen" and target_type == "UIElement":
        relation_type = "CONTAINS"
    elif source_type == "UIElement" and (target_type == "UIElement" or target_type in ["Tap", "Hold"]):
        relation_type = "TRIGGERS"
    elif source_type in ["Tap", "Hold"] and target_type == "Screen":
        relation_type = "LEADS_TO"
    else:
        return jsonify({"success": False, "message": f"오류: '{source_type}'와(과) '{target_type}' 사이에는 유효한 관계 타입이 없습니다."})

    creating_relation_cypher = f"""
    MATCH (s:{source_type} {{name: "{source_name}"}}), (t:{target_type} {{name: "{target_name}"}})
    CREATE (s)-[:{relation_type}]->(t)
    """
    n4.setCypher(creating_relation_cypher)
    result, error = n4.execute_cypher()

    if error:
        return jsonify({"success": False, "message": f"Neo4j 관계 생성 중 오류: {error}"})
    else:
        return jsonify({"success": True, "message": f"'{source_name}' -[:{relation_type}]-> '{target_name}' 관계가 정상적으로 생성됨"})

# 노드 삭제
@app.route('/delete_node', methods=['POST'])
def delete_node_web():
    node_type = request.form['node_type']
    node_name = request.form['node_name']
    
    success, message = delete_node(node_name, node_type)
    
    if success:
        delete_ui_alias(node_name, node_type)
    
    return jsonify({"success": success, "message": message})

# 관계 삭제
@app.route('/delete_relationship', methods=['POST'])
def delete_relationship_web():
    reltype = request.form['reltype']
    n1name = request.form['source_name']
    n1type = request.form['source_type']
    n2name = request.form['target_name']
    n2type = request.form['target_type']

    success, message = delete_relationship(reltype, n1name, n1type, n2name, n2type)

    return jsonify({"success": success, "message": message})

# 노드 목록 조회
@app.route('/get_nodes', methods=['GET'])
def get_nodes_api():
    tap_list, hold_list, screen_list, uielement_list = get_list()
    return jsonify({
        "tap": tap_list,
        "hold": hold_list,
        "screen": screen_list,
        "uielement": uielement_list
    })

# 노드 속성 조회
@app.route('/get_node_properties', methods=['POST'])
def get_node_properties_web():
    node_type = request.form['node_type']
    node_name = request.form['node_name']

    if not check_if_exist(node_type, node_name):
        return jsonify({"success": False, "message": f"'{node_name}' 노드가 존재하지 않습니다."})
    
    properties = get_node_properties(node_name, node_type)
    if properties is not None:
        return jsonify({"success": True, "properties": properties})
    else:
        return jsonify({"success": False, "message": "노드 속성을 가져오는 중 오류가 발생했습니다."})

# 노드 속성 업데이트
@app.route('/update_node_properties', methods=['POST'])
def update_node_properties_web():
    node_type = request.form['node_type']
    node_name = request.form['node_name']
    new_props_json = request.form['new_props']
    remove_props_json = request.form['remove_props']
    
    new_props = json.loads(new_props_json)
    remove_props = json.loads(remove_props_json)

    success, message = update_node_properties(node_name, node_type, new_props, remove_props)
    
    return jsonify({"success": success, "message": message})

# Flask 앱 실행
if __name__ == '__main__':
    if os.path.exists(json_file):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    app.run(debug=True)