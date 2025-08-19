from threading import Thread
import subprocess
import socket
import time

ADB_PATH = "adb"
SCRCPY_SERVER_PATH = "scrcpy-server"
DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"
# 避免与 Android 模拟器使用的本机 5554/5555 端口对冲，使用 scrcpy 默认端口 27183
LOCAL_PORT = 27183

class Scrcpy:
    def __init__(self):
        self.video_socket = None
        self.audio_socket = None
        self.control_socket = None

        self.android_thread = None
        self.video_thread = None
        self.audio_thread = None
        self.control_thread = None
        self.android_process = None

    def push_server_to_device(self):
        print("Pushing scrcpy-server.jar to device...")
        result = subprocess.run([ADB_PATH, "push", SCRCPY_SERVER_PATH, DEVICE_SERVER_PATH], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error pushing server: {result.stderr}")
            return False
        return True

    def setup_adb_forward(self):
        print(f"Setting up ADB forward: tcp:{LOCAL_PORT} -> localabstract:scrcpy")
        # 先尝试移除已有的同端口转发，避免残留导致失败（忽略错误）
        try:
            subprocess.run([ADB_PATH, "forward", "--remove", f"tcp:{LOCAL_PORT}"], capture_output=True)
        except Exception:
            pass
        subprocess.run([ADB_PATH, "forward", f"tcp:{LOCAL_PORT}", "localabstract:scrcpy"], check=True)

    def start_server(self):
        print("Starting scrcpy server in background...")
        cmd = [
            ADB_PATH, "shell",
            f"CLASSPATH={DEVICE_SERVER_PATH} app_process / com.genymobile.scrcpy.Server 3.1 tunnel_forward=true log_level=VERBOSE video_bit_rate=" + self.video_bit_rate
        ]
        self.android_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while not self.stop:
            stderr_line = self.android_process.stderr.readline().decode().strip()
            if not stderr_line:
                break
            if stderr_line:
                print(f"Server error: {stderr_line}")
        self.android_process.wait()
        print("Server stopped")

    def receive_video_data(self):
        print("Receiving video data (H.264)...")
        try:
            self.video_socket.settimeout(0.5)
            try:
                self.video_socket.recv(1)
            except (TimeoutError, socket.timeout):
                pass
            while not self.stop:
                try:
                    data = self.video_socket.recv(20480)
                except (TimeoutError, socket.timeout):
                    continue
                except (OSError, ConnectionAbortedError, ConnectionResetError):
                    break
                if not data:
                    break
                self.video_callback(data)
        except Exception:
            pass
        print("Video data reception stopped")

    def receive_audio_data(self):
        print("Receiving audio data...")
        try:
            self.audio_socket.settimeout(0.5)
            try:
                self.audio_socket.recv(1)
            except (TimeoutError, socket.timeout):
                pass
            while not self.stop:
                try:
                    data = self.audio_socket.recv(1024)
                except (TimeoutError, socket.timeout):
                    continue
                except (OSError, ConnectionAbortedError, ConnectionResetError):
                    break
                if not data:
                    break
        except Exception:
            pass
        print("Audio data reception stopped")

    def handle_control_conn(self):
        print("Control connection established (idle)...")
        try:
            self.control_socket.settimeout(0.5)
            try:
                self.control_socket.recv(1)
            except (TimeoutError, socket.timeout):
                pass
            while not self.stop:
                try:
                    data = self.control_socket.recv(1024)
                except (TimeoutError, socket.timeout):
                    continue
                except (OSError, ConnectionAbortedError, ConnectionResetError):
                    break
                if not data:
                    break
                print("Control Mesg:", data)
        except Exception:
            pass
        print("Control connection stopped")

    def scrcpy_start(self, video_callback, video_bit_rate):
        self.video_bit_rate = video_bit_rate
        self.video_callback = video_callback
        self.stop = False

        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
        if "device" not in result.stdout:
            print("No device found. Please connect your Android device via USB.")
            return
        print(result.stdout)

        if not self.push_server_to_device():
            print("Failed to push server files to device.")
            return

        self.setup_adb_forward()
        self.android_thread = Thread(target=self.start_server, daemon=True)
        self.android_thread.start()
        time.sleep(1)

        # video connection
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.video_socket.connect(('localhost', LOCAL_PORT))
        print("Video connection established")

        # audio connection
        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.audio_socket.connect(('localhost', LOCAL_PORT))
        print("Audio connection established")

        # contorl connection
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_socket.connect(('localhost', LOCAL_PORT))
        print("Control connection established")

        self.video_thread = Thread(target=self.receive_video_data, daemon=True)
        self.audio_thread = Thread(target=self.receive_audio_data, daemon=True)
        self.control_thread = Thread(target=self.handle_control_conn, daemon=True)
        self.video_thread.start()
        self.audio_thread.start()
        self.control_thread.start()
        print("Background tasks started")

    def scrcpy_stop(self):
        print("Stopping Scrcpy")
        self.stop = True
        # 逐个安全关闭，避免重复关闭导致的 WinError 10038
        try:
            if self.video_socket:
                try:
                    self.video_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
        finally:
            try:
                if self.video_socket:
                    self.video_socket.close()
            except Exception:
                pass

        try:
            if self.audio_socket:
                try:
                    self.audio_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
        finally:
            try:
                if self.audio_socket:
                    self.audio_socket.close()
            except Exception:
                pass

        try:
            if self.control_socket:
                try:
                    self.control_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
        finally:
            try:
                if self.control_socket:
                    self.control_socket.close()
            except Exception:
                pass

        try:
            if self.video_thread:
                self.video_thread.join()
        except Exception:
            pass
        try:
            if self.audio_thread:
                self.audio_thread.join()
        except Exception:
            pass
        try:
            if self.control_thread:
                self.control_thread.join()
        except Exception:
            pass

        try:
            if self.android_process:
                self.android_process.terminate()
        except Exception:
            pass
        try:
            if self.android_thread:
                self.android_thread.join()
        except Exception:
            pass

        # 清理 adb 端口转发，避免残留
        try:
            subprocess.run([ADB_PATH, "forward", "--remove", f"tcp:{LOCAL_PORT}"])
        except Exception:
            pass
        print("Scrcpy stopped")

    def scrcpy_send_control(self, data):
        self.control_socket.send(data)