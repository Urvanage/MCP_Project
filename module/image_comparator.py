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

            for (ref_y, ref_x), (tap_x, tap_y) in tap_map.items():
                if abs(y - ref_y) <= 5:
                    subprocess.run(f"adb shell input tap {tap_x} {tap_y}", shell=True)
                    subprocess.run("adb shell input tap 845 55", shell=True)  # 닫기?
                    return self.check_menu(menu_name, tap_map)  # 재귀 호출
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
        return image

    def _are_images_similar(self, img1: np.ndarray, img2: np.ndarray, threshold=10) -> bool:
        """두 넘파이 배열 이미지의 유사성을 비교합니다. (평균 픽셀 차이)"""
        if img1.shape != img2.shape:
            return False
        
        diff = np.abs(img1.astype(np.int16) - img2.astype(np.int16))
        mean_diff = np.mean(diff)
        
        return mean_diff < threshold

    def save_screen(self):
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = Image.open("screen.png")
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
            return "Home"
        screen_map = {
            "Program": ((160, 30, 235, 50), "program_check.png"),
            "Run":     ((255, 30, 305, 50), "run_check.png"),
            "Settings":   ((335, 30, 375, 50), "settings_check.png"),
            "Move":    ((1220, 30, 1265, 50), "move_check.png"),
            "System":  ((1290, 30, 1355, 50), "system_check.png"),
        }

        for screen_name, (coords, ref_filename) in screen_map.items():
            
            current_tab_img = full_screen.crop(coords)
            current_tab_arr = np.array(current_tab_img)
            
            ref_filepath = os.path.join(self.reference_path, ref_filename)
            if not os.path.exists(ref_filepath):
                continue
            
            ref_img = Image.open(ref_filepath)
            ref_arr = np.array(ref_img)

            if self._are_images_similar(current_tab_arr, ref_arr):
                return screen_name

        return "Home"

#img = ImageComparator().check_system_menu()

#img = ImageComparator().check_current_screen()