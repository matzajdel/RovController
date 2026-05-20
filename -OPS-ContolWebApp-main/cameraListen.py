import sys
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gst, GLib

def main():
    # Initialize GStreamer
    Gst.init(sys.argv)

    # Define the receiving pipeline
    # We specify the exact caps (capabilities) that match your rtph264pay sender
    pipeline_string = (
        'udpsrc port=8081 '
        'caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96" ! '
        'rtph264depay ! '
        'decodebin ! '
        'videoconvert ! '
        'autovideosink'
    )

    print(f"Starting receiver pipeline:\n{pipeline_string}\n")
    
    # Create the pipeline using parse_launch (the simplest method)
    pipeline = Gst.parse_launch(pipeline_string)

    # Start playing
    pipeline.set_state(Gst.State.PLAYING)

    # Create a GLib Main Loop to keep the script running and listen for events
    loop = GLib.MainLoop()
    
    try:
        print("Listening for video stream... Press Ctrl+C to stop.")
        loop.run()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        # Clean up properly
        pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    main()
