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
from abc import ABC, abstractmethod

# Reducing ALSA verbosity (0 = silent, 3 = full debug)
os.environ["ALSA_LOG_LEVEL"] = "0"

class InputController(ABC):
    """Abstract base class for input controllers"""
    def __init__(self, recorder=None):
        self.recorder = recorder
        self.stop_program = False

    @abstractmethod
    def setup(self):
        """Initialize the input controller"""
        pass

    @abstractmethod
    def start(self):
        """Start listening for input"""
        pass

    @abstractmethod
    def cleanup(self):
        """Clean up resources"""
        pass

    def set_recorder(self, recorder):
        """Set the recorder instance"""
        self.recorder = recorder

    def trigger_recording(self):
        """Trigger recording on the recorder"""
        if self.recorder:
            self.recorder.is_recording = True

    def stop(self):
        """Stop the input controller"""
        self.stop_program = True
        if self.recorder:
            self.recorder.stop_program = True

class AudioRecorder:
    def __init__(self, buffer_seconds=30, chunk_size=512, channels=1, sample_rate=16000):
        self.CHUNK = chunk_size
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = channels
        self.RATE = sample_rate
        self.BUFFER_SECONDS = buffer_seconds
        
        self.audio_buffer = queue.Queue(maxsize=int(self.RATE / self.CHUNK * self.BUFFER_SECONDS))
        self.is_recording = False
        self.stop_program = False
        self.p = None
        self.stream = None
        
    def find_best_microphone(self):
        """Find the best available microphone"""
        print("Searching for available microphones...")
        
        best_mics = []
        for i in range(self.p.get_device_count()):
            dev_info = self.p.get_device_info_by_index(i)
            dev_name = dev_info['name'].lower()
            channels = int(dev_info['maxInputChannels'])
            
            print(f"Device {i}: {dev_info['name']}")
            print(f"  Max Input Channels: {channels}")
            print(f"  Default Sample Rate: {dev_info['defaultSampleRate']}")
            
            if channels > 0:
                priority = 0
                if 'mic' in dev_name or 'microphone' in dev_name:
                    priority += 3
                if 'array' in dev_name:
                    priority += 2
                if 'usb' in dev_name:
                    priority += 1
                if 'respeaker' in dev_name:
                    priority += 3
                    
                best_mics.append({
                    'index': i,
                    'name': dev_info['name'],
                    'channels': channels,
                    'sample_rate': int(dev_info['defaultSampleRate']),
                    'priority': priority
                })
        
        if best_mics:
            best_mics.sort(key=lambda x: (x['priority'], x['channels']), reverse=True)
            selected = best_mics[0]
            print(f"Selected microphone: {selected['name']} (device index: {selected['index']})")
            return selected['index'], min(selected['channels'], self.CHANNELS), selected['sample_rate']
        
        try:
            default_info = self.p.get_default_input_device_info()
            print(f"Using default input device: {default_info['name']}")
            return default_info['index'], min(int(default_info['maxInputChannels']), self.CHANNELS), int(default_info['defaultSampleRate'])
        except:
            print("No specific microphone found. Using system default.")
            return None, self.CHANNELS, self.RATE

    def start_recording(self):
        """Start the audio recording process"""
        self.p = pyaudio.PyAudio()
        device_index, channels, sample_rate = self.find_best_microphone()
        
        try:
            self.stream = self.p.open(format=self.FORMAT,
                                    channels=channels,
                                    rate=sample_rate,
                                    input=True,
                                    input_device_index=device_index,
                                    frames_per_buffer=self.CHUNK)
            print("Recording started successfully...")
            return channels, sample_rate
        except Exception as e:
            print(f"Stream error: {e}")
            try:
                print("Trying with fallback default settings...")
                self.stream = self.p.open(format=self.FORMAT,
                                        channels=1,
                                        rate=16000,
                                        input=True,
                                        frames_per_buffer=self.CHUNK)
                print("Recording started with fallback settings...")
                return 1, 16000
            except Exception as e2:
                print(f"Fallback also failed: {e2}")
                self.cleanup()
                return None, None

    def record_loop(self):
        """Main recording loop"""
        channels, sample_rate = self.start_recording()
        if channels is None:
            return

        print("Device is listening... (Press button or 'r' key to save, 'q' to quit)")
        try:
            while not self.stop_program:
                data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                if self.audio_buffer.full():
                    self.audio_buffer.get()
                self.audio_buffer.put(data)
                if self.is_recording:
                    self.save_recording(channels, sample_rate)
                    self.is_recording = False
        except Exception as e:
            print(f"Recording loop error: {e}")
        finally:
            self.cleanup()

    def save_recording(self, channels, sample_rate):
        """Save the buffered audio plus additional 10 seconds"""
        frames = []
        while not self.audio_buffer.empty():
            frames.append(self.audio_buffer.get())
        
        print("Recording additional 10 seconds...")
        start_time = time.time()
        while time.time() - start_time < 10:
            data = self.stream.read(self.CHUNK, exception_on_overflow=False)
            frames.append(data)

        audios_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audios")
        if not os.path.exists(audios_dir):
            os.makedirs(audios_dir)
            print(f"Created directory: {audios_dir}")
        
        filename = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        filepath = os.path.join(audios_dir, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(channels)
        wf.setsampwidth(self.p.get_sample_size(self.FORMAT))
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))
        wf.close()
        print(f"Recording saved as {filepath}")

    def cleanup(self):
        """Clean up resources"""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()

class ButtonController(InputController):
    def __init__(self, pin=2, recorder=None):
        super().__init__(recorder)
        self.BUTTON_PIN = pin

    def setup(self):
        """Initialize GPIO for button input"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.BUTTON_PIN, GPIO.FALLING, callback=self.button_callback, bouncetime=300)
            print("GPIO button initialized on pin", self.BUTTON_PIN)
        except Exception as e:
            print(f"GPIO initialization failed: {e}")
           

    def button_callback(self, channel):
        print("Button pressed! Starting recording...")
        self.trigger_recording()

    def start(self):
        """Button controller doesn't need a separate thread"""
        pass

    def cleanup(self):
        try:
            GPIO.cleanup()
        except:
            pass

class KeyboardController(InputController):
    def __init__(self, recorder=None, keyboard_enabled=False):
        super().__init__(recorder)
        self.old_settings = None
        self.keyboard_enabled = keyboard_enabled

    def setup(self):
        """Keyboard controller setup is handled in start()"""
        pass

    def is_key_pressed(self):
        """Non-blocking check for keyboard input"""
        #select is a function that waits for input from the keyboard
        #sys.stdin is the input from the keyboard
        #[] is the list of inputs to wait for
        #[] is the list of inputs to ignore
        #0 is the timeout
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

    def start(self):
        """Start the keyboard listener thread"""
        #termios is a module that allows you to change the attributes of the terminal
        #tcgetattr is a function that gets the attributes of the terminal
        #sys.stdin is the input from the keyboard
        #termios.tcgetattr(sys.stdin) is the attributes of the terminal
        #termios.tcsetattr is a function that sets the attributes of the terminal
        #termios.TCSADRAIN is a flag that means that the terminal attributes should be restored when the program exits
        self.old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            print("\nKeyboard controls enabled:")
            print("  Press 'r' to start recording")
            print("  Press 'q' to quit the program")
            print("Waiting for commands...")
            
            while not self.stop_program:
                if self.is_key_pressed():
                    key = sys.stdin.read(1)
                    
                    if key == 'r':
                        print("\nKeyboard command: Start recording")
                        self.trigger_recording()
                    elif key == 'q':
                        print("\nKeyboard command: Quit program")
                        self.stop()
                        break
                time.sleep(0.1)
        finally:
            self.cleanup()

    def cleanup(self):
        if self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

def main():
    try:
        # Create and initialize components
        recorder = AudioRecorder()
        button_controller = ButtonController(recorder=recorder)
        keyboard_controller = KeyboardController(recorder=recorder, keyboard_enabled=True)
        
        # Setup input controllers
        button_controller.setup()
        keyboard_controller.setup()
        
        # Start keyboard listener thread if needed
        if keyboard_controller.keyboard_enabled:
            keyboard_thread = threading.Thread(target=keyboard_controller.start)
            keyboard_thread.daemon = True
            keyboard_thread.start()
        
        # Start recording
        recorder.record_loop()
        
    except KeyboardInterrupt:
        print("\nStopping program...")
    except Exception as e:
        print(f"Main error: {e}")
    finally:
        button_controller.cleanup()
        keyboard_controller.cleanup()
        print("Program terminated.")

if __name__ == "__main__":
    main()