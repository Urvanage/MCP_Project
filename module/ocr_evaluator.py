import subprocess
from PIL import Image
import cv2
import pytesseract
import re
import os
from dotenv import load_dotenv

load_dotenv()

tesseract_path = os.getenv("TESSERACT_CMD_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

class OCREvaluator:
    def __init__(self):
        pass

    def check_system_menu_ocr(self):
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = Image.open("screen.png")
        cropped_img = image.crop((10,105,300,875))

        text = pytesseract.image_to_string(cropped_img, lang='kor')
        if "엔드툴" in text:
            subprocess.run("adb shell input tap 165 130")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
        if "네트워크" in text:
            subprocess.run("adb shell input tap 165 195")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
        if "로그" in text:
            subprocess.run("adb shell input tap 165 255")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
        
        
    
    def check_settings_menu_ocr(self):
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = Image.open("screen.png")
        cropped_img = image.crop((10,105,300,875))

        text = pytesseract.image_to_string(cropped_img, lang='kor')
        r1=False
        r2=False
        r3=False
        r4=False
        if "공간" in text:
            subprocess.run("adb shell input tap 165 130")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
        if "좌표계" in text:
            subprocess.run("adb shell input tap 165 195")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
        if "옵션" in text:
            subprocess.run("adb shell input tap 165 255")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
        if "보호기" in text:
            subprocess.run("adb shell input tap 165 315")
            subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
            subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
            image = Image.open("screen.png")
            cropped_img = image.crop((10,105,300,875))

            text = pytesseract.image_to_string(cropped_img, lang='kor')
 
        return r1,r2,r3,r4

    def perform_ocr(self) -> str:
        subprocess.run("adb shell screencap -p /sdcard/screen.png", shell=True)
        subprocess.run(f"adb pull /sdcard/screen.png screen.png", shell=True)
        
        image = cv2.imread("screen.png")

        if image is None:
            print("Error: Could not load image from screen.png. Check file path or adb pull success.")
            return ""

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        pil_img = Image.fromarray(binary) 
        text = pytesseract.image_to_string(pil_img, lang='kor+eng', config='--psm 6') # 'eng'와 '--psm 6' 시도

        return text.strip()

    def perform_ocr_and_search(self, search_string: str = None) -> (str,bool):
        full_text = self.perform_ocr()
        print(f"[OCR] Full text from Image\n{full_text}\n")
        found=False

        if search_string:
            if search_string.lower() in full_text.lower():
                found =True
        
        print(f"[OCR] The {search_string} was found? result follows: {found}")

        return full_text, found
    

ocr = OCREvaluator()
#r1, r2, r3 = ocr.check_system_menu_ocr()
s1,s2,s3,s4 = ocr.check_settings_menu_ocr()
