import pyaudio
import wave
import time
import queue
import RPi.GPIO as GPIO
from datetime import datetime
import os
import threading
import sys
import select
import termios
import tty

# Reducing ALSA verbosity (0 = silent, 3 = full debug)
os.environ["ALSA_LOG_LEVEL"] = "0"

# Audio settings
CHUNK = 512 
FORMAT = pyaudio.paInt16
CHANNELS = 1  
RATE = 16000  # Common sampling rate for voice
BUFFER_SECONDS = 30

BUTTON_PIN = 2  

# Circular buffer to store last 30 seconds
audio_buffer = queue.Queue(maxsize=int(RATE / CHUNK * BUFFER_SECONDS))

is_recording = False
keyboard_enabled = False # for testing
stop_program = False

def setup_gpio():
    """Initialize GPIO for button input"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Internal pull-up
        GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=button_callback, bouncetime=300)
        print("GPIO button initialized on pin", BUTTON_PIN)
    except Exception as e:
        print(f"GPIO initialization failed: {e}")
        print("Running with keyboard controls only")
        global keyboard_enabled
        keyboard_enabled = True

def button_callback(channel):
    global is_recording
    print("Button pressed! Starting recording...")
    is_recording = True

def is_key_pressed():
    """Non-blocking check for keyboard input"""
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

def keyboard_listener():
    """Thread function to listen for keyboard commands"""
    global is_recording, stop_program
    
    # Save terminal settings
    # this allows the program to listen for keyboard commands without waiting for the enter key or
    # echoing the input to the terminal
    # saving the old settings to restore them later
    old_settings = termios.tcgetattr(sys.stdin) 
    try:
        # Set terminal to raw mode
        tty.setraw(sys.stdin.fileno())
        print("\nKeyboard controls enabled:")
        print("  Press 'r' to start recording")
        print("  Press 'q' to quit the program")
        print("Waiting for commands...")
        
        while not stop_program:
            if is_key_pressed():
                key = sys.stdin.read(1)
                
                if key == 'r':
                    print("\nKeyboard command: Start recording")
                    is_recording = True
                elif key == 'q':
                    print("\nKeyboard command: Quit program")
                    stop_program = True
                    break
            time.sleep(0.1)  # Small delay to reduce CPU usage
    finally:
        # Restore terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

def find_best_microphone(p):
    """Find the best available microphone
    
    Returns a tuple of (device_index, max_channels, sample_rate)
    """
    print("Searching for available microphones...")
    
    # looking for devices with "mic" or similar in the name
    best_mics = []
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        dev_name = dev_info['name'].lower()
        channels = int(dev_info['maxInputChannels'])
        
        print(f"Device {i}: {dev_info['name']}")
        print(f"  Max Input Channels: {channels}")
        print(f"  Default Sample Rate: {dev_info['defaultSampleRate']}")
        
        # Only consider devices that actually have input channels
        if channels > 0:
            priority = 0
            # Give priority to devices that seem like dedicated microphones
            if 'mic' in dev_name or 'microphone' in dev_name:
                priority += 3
            if 'array' in dev_name:  # Microphone arrays are better quality
                priority += 2
            if 'usb' in dev_name:  # USB mics are usually external and better quality
                priority += 1
            if 'respeaker' in dev_name:  # Extra points for known good mics
                priority += 3
                
            best_mics.append({
                'index': i,
                'name': dev_info['name'],
                'channels': channels,
                'sample_rate': int(dev_info['defaultSampleRate']),
                'priority': priority
            })
    
    # If we found microphones, select the best one based on priority
    if best_mics:
        # Sort by priority (highest first) then by number of channels
        best_mics.sort(key=lambda x: (x['priority'], x['channels']), reverse=True)
        selected = best_mics[0]
        print(f"Selected microphone: {selected['name']} (device index: {selected['index']})")
        return selected['index'], min(selected['channels'], CHANNELS), selected['sample_rate']
    
    # If no dedicated mic found, try to find the default input device
    try:
        default_info = p.get_default_input_device_info()
        print(f"Using default input device: {default_info['name']}")
        return default_info['index'], min(int(default_info['maxInputChannels']), CHANNELS), int(default_info['defaultSampleRate'])
    except:
        # Last resort: use the system default device (index None)
        print("No specific microphone found. Using system default.")
        return None, CHANNELS, RATE

def audio_recording():
    """Main audio recording function"""
    global is_recording, stop_program
    
    p = pyaudio.PyAudio()
    
    # Find the best available microphone
    device_index, channels, sample_rate = find_best_microphone(p)
    
    print(f"Using device index: {device_index}, channels: {channels}, sample rate: {sample_rate}")
    
    try:
        stream = p.open(format=FORMAT,
                      channels=channels,
                      rate=sample_rate,
                      input=True,
                      input_device_index=device_index,
                      frames_per_buffer=CHUNK)
        print("Recording started successfully...")
    except Exception as e:
        print(f"Stream error: {e}")
        # Try again with default settings as a fallback
        try:
            print("Trying with fallback default settings...")
            stream = p.open(format=FORMAT,
                          channels=1,
                          rate=16000,
                          input=True,
                          frames_per_buffer=CHUNK)
            print("Recording started with fallback settings...")
            channels = 1
            sample_rate = 16000
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
            p.terminate()
            return

    print("Device is listening... (Press button or 'r' key to save, 'q' to quit)")
    try:
        while not stop_program:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if audio_buffer.full():
                audio_buffer.get()  # Remove oldest chunk
            audio_buffer.put(data)
            if is_recording:
                save_recording(p, stream, channels, sample_rate)
                is_recording = False
    except Exception as e:
        print(f"Recording loop error: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

def save_recording(p, stream, channels, sample_rate):
    """Save the buffered audio plus additional 10 seconds"""
    frames = []
    while not audio_buffer.empty():
        frames.append(audio_buffer.get())
    
    print("Recording additional 10 seconds...")
    start_time = time.time()
    while time.time() - start_time < 10:
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    # Creating 'audios' directory if it doesn't exist
    audios_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audios")
    if not os.path.exists(audios_dir):
        os.makedirs(audios_dir)
        print(f"Created directory: {audios_dir}")
    
    filename = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    filepath = os.path.join(audios_dir, filename)
    
    wf = wave.open(filepath, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(sample_rate)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"Recording saved as {filepath}")

def main():
    try:
        #GPIO if enabled
        setup_gpio()
        
        # Starting the keyboard listener thread if enabled
        if keyboard_enabled:
            keyboard_thread = threading.Thread(target=keyboard_listener)
            keyboard_thread.daemon = True  # Thread will exit when main program exits
            keyboard_thread.start()
        
        audio_recording()
    except KeyboardInterrupt:
        print("\nStopping program...")
    except Exception as e:
        print(f"Main error: {e}")
    finally:
        global stop_program
        stop_program = True
        try:
            GPIO.cleanup()
        except:
            pass
        print("Program terminated.")

if __name__ == "__main__":
    main()