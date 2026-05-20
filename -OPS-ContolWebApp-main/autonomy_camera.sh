#!/usr/bin/env python3
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

class LiveStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Send the exact HTTP headers modern browsers demand for live video
        self.send_response(200)
        self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=ffserver')
        self.end_headers()

        # 2. Launch FFmpeg, force 10 FPS, and pipe the output to stdout (memory)
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-f', 'v4l2', '-framerate', '30', '-i', '/dev/video0',
            '-vf', 'fps=10', '-f', 'mpjpeg', '-q:v', '5', '-'
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)

        # 3. Stream the memory pipe directly to the browser
        try:
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception:
            # Ignore errors when the user closes their browser tab
            pass
        finally:
            # Safely kill FFmpeg when the viewer disconnects to save CPU
            process.kill()

print("=====================================================")
print("Zero-Latency 10 FPS Stream is LIVE!")
print("View URL: http://localhost:8081")
print("Press Ctrl+C to stop.")
print("=====================================================")

# Start the server on port 8081
ThreadingHTTPServer(('0.0.0.0', 8081), LiveStreamHandler).serve_forever()
