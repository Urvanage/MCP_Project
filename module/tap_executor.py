import subprocess
import time

"""
생성된 sequence를 토대로 adb 커맨드를 실행한다.

tap 함수를 통해서 호출한다.
avoid 값은 dictionary 로 가장 시작점으로 설정된 UI Element를 의미한다.
"""

class TapExecutor:
    def __init__(self, avoid=None):
        self.avoid = avoid

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