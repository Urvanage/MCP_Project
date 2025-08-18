import cv2
import numpy as np

import subprocess
from PIL import Image
import os
import matplotlib.pyplot as plt
import time

class ImageComparator:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.reference_path = os.path.join(base_dir, "resource", "image")

    def save_current(self):
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = Image.open("screen.png")
        # screen.png 지우는 코드
        cropped_img = image.crop((10,105,300,875))
        cropped_img.save("current_screen.png")
        return cropped_img

    def check_menu(self, menu_name: str, tap_map: dict):
        current_img = self.save_current()
        ref_path = os.path.join(self.reference_path, menu_name)
        ref_img = Image.open(ref_path)

        current_arr = np.array(current_img).astype(np.int16)
        ref_arr = np.array(ref_img).astype(np.int16)

        if current_arr.shape != ref_arr.shape:
            raise ValueError(f"이미지 크기 불일치: current={current_arr.shape}, reference={ref_arr.shape}")
        
        diff = np.abs(current_arr - ref_arr)
        diff_mask = np.any(diff > 0, axis=2)

        if np.any(diff_mask):
            y, x = np.argwhere(diff_mask)[0]
            print(f"[DIFF] 첫 번째 다른 픽셀 위치: (x={x}, y={y})")

            # 오차 범위 허용 비교 함수
            for (ref_y, ref_x), (tap_x, tap_y) in tap_map.items():
                if abs(y - ref_y) <= 5:
                    print(f"[ACTION] 탭 위치: ({tap_x}, {tap_y})")
                    subprocess.run(f"adb shell input tap {tap_x} {tap_y}", shell=True)
                    subprocess.run("adb shell input tap 845 55", shell=True)  # 닫기?
                    return self.check_menu(menu_name, tap_map)  # 재귀 호출
            print("[INFO] 일치하는 탭 좌표 없음.")
        else:
            print("[DIFF] 모든 픽셀이 동일합니다.")

    def check_system_menu(self):
        tap_map = {
            (16, 70): (165, 130),
            (78, 70): (165, 195),
            (139, 66): (165, 255),
        }
        self.check_menu("system_screen.png", tap_map)

    def check_settings_menu(self):
        tap_map = {
            (16, 79): (165, 130),
            (78, 124): (165, 195),
            (139, 71): (165, 255),
            (202, 62): (165, 315),
        }
        self.check_menu("settings_screen.png", tap_map)
    
    def _capture_and_load_screen(self, filename="current_full_screen.png"):
        """전체 화면을 캡처하고 PIL Image 객체로 불러옵니다."""
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = Image.open("screen.png")
        #image.save("current_screen.png")
        return image

    def _are_images_similar(self, img1: np.ndarray, img2: np.ndarray, threshold=10) -> bool:
        """두 넘파이 배열 이미지의 유사성을 비교합니다. (평균 픽셀 차이)"""
        if img1.shape != img2.shape:
            return False
        
        diff = np.abs(img1.astype(np.int16) - img2.astype(np.int16))
        mean_diff = np.mean(diff)
        
        #print(f"[DEBUG] 이미지 유사도 검사 (평균 픽셀 차이): {mean_diff:.2f}")
        return mean_diff < threshold

    def save_screen(self):
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = Image.open("screen.png")
        # screen.png 지우는 코드
        cropped_img = image.crop((1290,30,1355,50))
        cropped_img.save("current_screen.png")
        return cropped_img
    
    def check_current_screen(self) -> str:
        """
        현재 화면을 캡처하여 어떤 메뉴인지 식별합니다.
        미리 정의된 각 탭 영역을 잘라내어 기준 이미지와 비교합니다.
        """
        print("\n==== 현재 화면 식별 시작 ====")
        full_screen = self._capture_and_load_screen()
        if full_screen is None:
            #print("[ERROR] 스크린샷을 가져올 수 없어 'Home'으로 간주합니다.")
            return "Home"

        # 각 메뉴 탭의 이름, 자를 좌표 (left, top, right, bottom), 기준 이미지 파일명 정의
        screen_map = {
            "Program": ((160, 30, 235, 50), "program_check.png"),
            "Run":     ((255, 30, 305, 50), "run_check.png"),
            "Settings":   ((335, 30, 375, 50), "settings_check.png"),
            "Move":    ((1220, 30, 1265, 50), "move_check.png"),
            "System":  ((1290, 30, 1355, 50), "system_check.png"),
        }

        for screen_name, (coords, ref_filename) in screen_map.items():
            #print(f"---> '{screen_name}' 탭 확인 중...")
            
            # 1. 현재 화면에서 해당 탭 영역 잘라내기
            current_tab_img = full_screen.crop(coords)
            current_tab_arr = np.array(current_tab_img)
            
            # 2. 기준 이미지 불러오기
            ref_filepath = os.path.join(self.reference_path, ref_filename)
            if not os.path.exists(ref_filepath):
                #print(f"[WARNING] 기준 파일을 찾을 수 없습니다: {ref_filepath}")
                continue # 다음 탭으로 넘어감
            
            ref_img = Image.open(ref_filepath)
            ref_arr = np.array(ref_img)

            # 3. 두 이미지 비교
            if self._are_images_similar(current_tab_arr, ref_arr):
                #print(f"====> 결과: 현재 화면은 '{screen_name}' 입니다. <====")
                return screen_name

        # 모든 탭과 일치하지 않는 경우
        #print("====> 결과: 활성화된 탭을 찾지 못했습니다. 'Home'으로 인식합니다. <====")
        return "Home"

#img = ImageComparator().check_system_menu()

#img = ImageComparator().check_current_screen()