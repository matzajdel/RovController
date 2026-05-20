import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Initialize GStreamer
Gst.init(None)

# The Ports for the 4 cameras
PORTS = [2140, 2141, 2142, 2143]

# The Receiver Pipeline:
# 1. udpsrc: Listens on the assigned port for incoming data.
# 2. application/x-rtp... : Defines the incoming format (H.264 over RTP).
# 3. rtph264depay: Extracts the compressed H.264 video from the network packets.
# 4. avdec_h264: Decodes the compressed video into raw frames.
# 5. videoconvert: Ensures the color format matches your screen.
# 6. autovideosink: Displays the video in a window.
pipelines = []

for port in PORTS:
    pipeline_string = (
        f"udpsrc port={port} ! "
        "application/x-rtp,media=video,payload=96,encoding-name=H264 ! "
        "rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false"
    )
    
    pipeline = Gst.parse_launch(pipeline_string)
    
    # Start playing
    pipeline.set_state(Gst.State.PLAYING)
    pipelines.append(pipeline)

print(f"Listening for incoming video on UDP ports {', '.join(map(str, PORTS))}...")
print("Press Ctrl+C to stop.")

loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("\nStopping...")

# Clean up
for pipeline in pipelines:
    pipeline.set_state(Gst.State.NULL)
