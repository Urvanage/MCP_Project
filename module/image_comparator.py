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

img = ImageComparator().check_system_menu()