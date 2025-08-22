import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta

class InMemoryLogMonitor:
    def __init__(self, buffer_max_minutes=10):
        self.process = None
        self.thread = None
        self._running = False
        self.log_buffer = deque()
        self.start_time = None
        self.buffer_max_minutes = buffer_max_minutes
        self.current_year = datetime.now().year
        print("LogMonitor initialized (in-memory buffer mode).")

    def setTime(self):
        self.start_time = datetime.now()
        print(f"LogMonitor: start time set to {self.start_time}")

    def start_monitoring(self):
        # adb logcat -c 생략 가능
        import subprocess
        self.process = subprocess.Popen(
            ["adb", "logcat", "-v", "time", "*:I"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8"
        )
        self._running = True
        import threading
        self.thread = threading.Thread(target=self._buffer_logs, daemon=True)
        self.thread.start()
        print("LogMonitor: Started log buffering in memory.")

    def _buffer_logs(self):
        try:
            for line in iter(self.process.stdout.readline, ''):
                if not self._running:
                    break
                cleaned_line = line.strip()
                if cleaned_line:
                    # logcat 시간 추출: 예시 => "07-10 14:32:01.410"
                    timestamp_match = re.match(r"^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})", cleaned_line)
                    if timestamp_match:
                        log_time_str = timestamp_match.group(1)
                        try:
                            # 현재 연도 보정
                            timestamp = datetime.strptime(f"{self.current_year}-{log_time_str}", "%Y-%m-%d %H:%M:%S.%f")
                        except ValueError:
                            timestamp = datetime.now()  # 파싱 실패 시 fallback
                    else:
                        timestamp = datetime.now()  # 시간 형식 없을 경우 fallback

                    self.log_buffer.append((timestamp, cleaned_line))
                    self._clean_old_logs()
        except Exception as e:
            print(f"LogMonitor ERROR: {e}")
        finally:
            self._running = False
            print("LogMonitor: Buffering stopped.")


    def _clean_old_logs(self):
        now = datetime.now()
        threshold = now - timedelta(minutes=self.buffer_max_minutes)
        while self.log_buffer:
            timestamp, _ = self.log_buffer[0]
            if(self.start_time and timestamp < self.start_time) or timestamp < threshold:
                self.log_buffer.popleft()
            else:
                break

    def stop_monitoring(self):
        if self.process:
            self._running = False
            self.process.terminate()
            self.thread.join(timeout=5)
            print("LogMonitor: Monitoring stopped and cleaned up.")

    def get_logs(self) -> list[str]:
        self._clean_old_logs()
        return [line for _, line in self.log_buffer]

    def search(self, keyword: str) -> str | None:
        self._clean_old_logs()
        for _, line in reversed(self.log_buffer):
            if keyword.lower() in line.lower():
                return line
        return None
    
    def save_log(self):
        logs = []
        logs.append(self.search("[Msg]"))
        logs.append(self.search("Toast.Show"))
        logs.append(self.search("StartFragment :"))
        logs = [str(log) for log in logs if log is not None]
        # print(f"==== [LOGMONITOR] ====\n{logs}")

        curr_dir = Path(__file__).parent
        resource_folder = curr_dir.parent / 'resource'
        file_path = resource_folder / 'log_info.txt'
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.truncate(0)
                for log_entry in logs:
                    f.write(log_entry + "\n")
            #print(f"로그가 성공적으로 저장되었습니다.")
        except IOError as e:
            print(f"파일 작성 중 오류가 발생했습니다: {e}")