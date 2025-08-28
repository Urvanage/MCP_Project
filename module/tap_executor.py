import subprocess
import time

"""
TapExecutor 클래스
- 생성된 UI sequence를 기반으로 ADB 명령어를 실행하여 안드로이드 디바이스를 제어
- tap()과 hold() 함수를 통해 호출
- avoid 값은 dictionary 형태로, sequence의 시작점에서 클릭을 피할 UI Element를 지정
"""

class TapExecutor:
    def __init__(self, avoid=None):
        self.avoid = avoid # 클릭할 필요가 없는 UI Element 정보

    # tap_sequence를 표준 형식 (list of dict)으로 변환
    def _normalize(self, tap_sequence):
        normalized = []
        
        def deep_flatten(seq):
            for item in seq:
                if isinstance(item, (list, tuple)):
                    if len(item) > 0 and isinstance(item[0], (list, tuple, dict)):
                        deep_flatten(item)
                    elif len(item) == 3 and isinstance(item[0], str) and isinstance(item[1], int) and isinstance(item[2], int):
                        normalized.append({'name': item[0], 'x': item[1], 'y': item[2]})
                    else:
                        print(f"[normalize] Unknown item format (list/tuple): {item}")
                elif isinstance(item, dict):
                    if 'x' in item and 'y' in item:
                        normalized.append(item)
                    else:
                        print(f"[normalize] Dictionary missing coordinates: {item}")
                else:
                    print(f"[normalize] Unknown item type: {item}")

        if isinstance(tap_sequence, (list, tuple)):
            deep_flatten(tap_sequence)
        elif isinstance(tap_sequence, dict): # Handle a single dict case if it ever comes up
            if 'x' in tap_sequence and 'y' in tap_sequence:
                normalized.append(tap_sequence)
            else:
                print(f"[normalize] Dictionary missing coordinates: {tap_sequence}")
        else:
            print(f"[normalize] Unexpected input type for tap_sequence: {tap_sequence}")

        return normalized
    
    # 화면 중앙 상단 영역을 탭
    def tap_middle(self):
        cmd = "adb shell input tap 810 50"
        subprocess.run(cmd, shell=True)

    # 주어진 tap_sequence를 순서대로 탭한 후, 마지막으로 탭한 UI Element를 반환
    def tap(self, tap_sequence, avoid=None):
        tap_sequence = self._normalize(tap_sequence)
        last_tapped_item = None
        skip = False
        avoid = self.avoid

        if len(tap_sequence) == 0:
            return False

        if avoid is not None:
            first_item_name = tap_sequence[0].get('name')
            if first_item_name == avoid.get('name'):
                skip = True


        for item in tap_sequence:
            if skip is True:
                skip = False
                continue
            name = item.get('name', 'Unknown')
            x = item.get('x')
            y = item.get('y')

            if x is None or y is None:
                print(f"Skipping {name} due to missing coordinates.")
                continue

            print(f"Tapping {name} at ({x}, {y})...")
            cmd = f"adb shell input tap {x} {y}"
            subprocess.run(cmd, shell=True)
            time.sleep(0.5)
            last_tapped_item = item #마지막으로 탭한 UI
        
        return last_tapped_item
    
    # tap과 동일하나 tap_sequence의 마지막 항목을 길게 누르는 동작
    def hold(self, tap_sequence, avoid=None):
        tap_sequence = self._normalize(tap_sequence)
        last_tapped_item = None
        skip = False
        avoid = self.avoid

        if len(tap_sequence) == 0:
            return False
        
        if avoid is not None:
            first_item_name = tap_sequence[0].get('name')
            if first_item_name == avoid.get('name'):
                skip = True

        for idx, item in enumerate(tap_sequence):
            if skip:
                skip = False
                continue

            name = item.get('name', 'Unknown')
            x = item.get('x')
            y = item.get('y')

            if x is None or y is None:
                print(f"Skipping {name} due to missing coordinates.")
                continue

            if idx == len(tap_sequence)-1:
                print(f"Holding {name} at ({x}, {y}) for 10 seconds...")
                cmd = f"adb shell input swipe {x} {y} {x} {y} 10000"
            else:
                print(f"Tapping {name} at ({x}, {y})...")
                cmd = f"adb shell input tap {x} {y}"

            subprocess.run(cmd, shell=True)
            time.sleep(0.5)
            last_tapped_item = item

        return last_tapped_item