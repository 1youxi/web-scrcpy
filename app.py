from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send
from scrcpy import Scrcpy
import argparse
import queue

scpy_ctx = None
client_sid = None
message_queue = queue.Queue()
video_bit_rate = "1024000"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=None)

@app.route('/')
def index():
    return render_template('index.html')

def video_send_task():
    global client_sid
    while client_sid != None:
        try:
            message = message_queue.get(timeout=0.01)
            socketio.emit('video_data', message, to=client_sid)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error sending data: {e}")
        finally:
            socketio.sleep(0.001)
    print(f"video_send_task stopped")

def send_video_data(data):
    message_queue.put(data)

@socketio.on('connect')
def handle_connect():
    global scpy_ctx, client_sid
    print('Client connected')

    if scpy_ctx is not None:
        print(f'reject connection, client {scpy_ctx} is already connected')
        return False
    else:
        client_sid = request.sid
        scpy_ctx = Scrcpy()
        scpy_ctx.scrcpy_start(send_video_data, video_bit_rate)
        socketio.start_background_task(video_send_task)
        print(f'connectioned, client  {scpy_ctx}')

@socketio.on('disconnect')
def handle_disconnect():
    global scpy_ctx, client_sid
    client_sid = None
    print('Client disconnected', {scpy_ctx})
    scpy_ctx.scrcpy_stop()
    scpy_ctx = None
    print('scrcpy stopped, client {scpy_ctx}')

@socketio.on('control_data')
def handle_control_data(data):
    global scpy_ctx
    scpy_ctx.scrcpy_send_control(data)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web server for scrcpy')
    parser.add_argument('--video_bit_rate', default="1024000", help='scrcpy video bit rate')
    args = parser.parse_args()
    video_bit_rate = args.video_bit_rate
    socketio.run(app, host='0.0.0.0', port=5001)