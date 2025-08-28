import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta

class InMemoryLogMonitor:
    """
    In-memory Log Monitor
    - adb logcat을 통해 안드로이드 디바이스 로그를 실시간으로 가져와 메모리 버퍼에 저장
    - 최근 N분간의 로그만 유지
    - 키워드 검색 및 특정 로그 저장 기능 제공
    """
    def __init__(self, buffer_max_minutes=10):
        self.process = None
        self.thread = None
        self._running = False
        self.log_buffer = deque()
        self.start_time = None
        self.buffer_max_minutes = buffer_max_minutes
        self.current_year = datetime.now().year
        print("LogMonitor initialized (in-memory buffer mode).")

    # 로그 모니터 시작 시간 설정
    def setTime(self):
        self.start_time = datetime.now()
        print(f"LogMonitor: start time set to {self.start_time}")

    # adb logcat 실행 후 별도 스레드에서 로그를 메모리 버퍼에 저장
    def start_monitoring(self):
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

    # 별도 스레드에서 로그 읽기
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

    # log_buffer에서 오래된 로그 제거
    def _clean_old_logs(self):
        now = datetime.now()
        threshold = now - timedelta(minutes=self.buffer_max_minutes)
        while self.log_buffer:
            timestamp, _ = self.log_buffer[0]
            if(self.start_time and timestamp < self.start_time) or timestamp < threshold:
                self.log_buffer.popleft()
            else:
                break

    # 로그 모니터 종료 및 스레드 정리
    def stop_monitoring(self):
        if self.process:
            self._running = False
            self.process.terminate()
            self.thread.join(timeout=5)
            print("LogMonitor: Monitoring stopped and cleaned up.")

    # 현재 메모리 버퍼에 있는 로그 리스트 반환
    def get_logs(self) -> list[str]:
        self._clean_old_logs()
        return [line for _, line in self.log_buffer]

    # 버퍼에서 특정 키워드 포함하는 가장 최근 로그 한 줄 검색
    def search(self, keyword: str) -> str | None:
        self._clean_old_logs()
        for _, line in reversed(self.log_buffer):
            if keyword.lower() in line.lower():
                return line
        return None
    
    # 특정 키워드 로그 추출한 후 log_info.txt에 저장
    def save_log(self):
        logs = []
        logs.append(self.search("[Msg]"))
        logs.append(self.search("Toast.Show"))
        logs.append(self.search("StartFragment :"))
        logs = [str(log) for log in logs if log is not None]

        curr_dir = Path(__file__).parent
        resource_folder = curr_dir.parent / 'resource'
        file_path = resource_folder / 'log_info.txt'
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.truncate(0)
                for log_entry in logs:
                    f.write(log_entry + "\n")
        except IOError as e:
            print(f"파일 작성 중 오류가 발생했습니다: {e}")