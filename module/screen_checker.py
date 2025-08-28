from langchain_openai import ChatOpenAI
import subprocess
import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
import base64
import time

"""
ScreenChecker 클래스
- 안드로이드 디바이스 화면을 캡처하고, 현재 화면이 어떤 화면인지 LLM을 이용해 판단
- 초기 화면으로 이동, 화면 캡처, 이미지 인코딩, 화면 확인 기능 포함
"""

# .env 파일에서 API key 불러오기
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

class ScreenChecker:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.reference_path = os.path.join(base_dir, "resource", "image")
    
    # 현재 디바이스 화면 캡처 후 PC로 저장
    def save_current_screen(self, filename: str = "screen.png"):
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png {filename}", shell=True)
        return Path(filename)
    
    # 이미지 파일을 base64 문자열로 변환
    def encode_image_to_base64(self,path:Path) -> str:
        with open(path,"rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
        
    # 앱 종료 후 다시 실행해 초기(Home) 화면으로 이동
    def move_to_home(self):
        cmd = "adb shell am force-stop com.neuromeka.conty3"
        subprocess.run(cmd, shell=True)
        time.sleep(1)
        print("Initiate Program")
        cmd = "adb shell monkey -p com.neuromeka.conty3 -c android.intent.category.LAUNCHER 1"
        subprocess.run(cmd, shell=True)
        print("==== Step 0: Move to Initial Screen ====")
        print("==== Completed ====\n\n")
        time.sleep(8)

    # 현재 화면 캡처 후 LLM을 통해 화면 이름을 판별
    def check_current_screen(self) -> str:
        screen_file = self.save_current_screen()

        llm = ChatOpenAI(
            model="gpt-5",
            use_responses_api=True,
            output_version="responses/v1",
            extra_body={
                "text": {"verbosity":"low"},
                "reasoning": {"effort":"minimal"},
            },
            api_key=api_key
        )
        base64_image = self.encode_image_to_base64("screen.png")
        image_url = f"data:image/png;base64,{base64_image}"

        question = f"""당신은 현재 화면을 구분하는 전문가입니다.
        현재 화면을 보고, 다음 화면들 중 어떤 화면인지 판단해주세요:
        "Program", "Run", "Settings", "System", "Move", "Home"

        - 활성화된 화면은 상단 탭에서 파란색 글자로 표시됩니다.
        - Home 화면은 중앙에 3개의 큰 카드 UI가 있습니다.
        - 위 6개 화면으로 구분할 수 없는 경우 "fail"을 반환해주세요.
        """

        msg = HumanMessage(content=[
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": image_url}}
        ])

        res = llm.invoke([msg])

        if isinstance(res.content, list):
            for item in res.content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    return item.get('text', '').strip()

        elif isinstance(res.content, str):
            return res.content.strip()

        return "No valid text content found in the response."