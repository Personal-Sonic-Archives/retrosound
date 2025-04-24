# Overview
This are scripts designed to be run on a raspberry pi 3 and should also work on later models. The goal for this project is to build a wearable device with software that can allow it to continunously buffer audio and save recordings when triggered. Currently it feautures a 30-second pre-recording buffer and saves 10 seconds of audio after the trigger.


## Hardware Requirements
- Raspberry Pi (any model with GPIO pins)
- Microphone 
- Push button (to trigger recording)
- 2 wires to connect the button to the GPIO pins

## Software Requirements
- Python 3.x
- Required Python packages:
  - pyaudio
  - RPi.GPIO
  - termios
  - tty


## Installation

1. Install required packages:
```bash
sudo apt-get update
sudo apt-get install python3-pyaudio python3-rpi.gpio
```

2. Clone this repository:
```bash
git clone [https://github.com/jwirfs-brock/sonic-archives]
cd sonic-archives
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Hardware Setup 

If you want to use a physical button:
1. Connect a push button to GPIO pin 2 (BCM numbering)
2. Connect one side of the button to GPIO pin 2
3. Connect the other side to ground (GND)

## Usage

### Starting the Recorder
```bash
python3 recorder.py
```

### Recording Controls
The device can be controlled in two ways:

1. **Hardware Button (if connected)**
   - Press the button to start recording
   - The device will save the last 30 seconds of audio plus 10 seconds after the button press

2. **Keyboard Controls(for testing)**
   - Press 'r' to start recording
   - Press 'q' to quit the program

### Current Recording Features
- Continuously buffers 30 seconds of audio (customizable)
- When triggered, saves:
  - The last 30 seconds of buffered audio 
  - An additional 10 seconds of new audio
- Automatically detects and uses the best available microphone
- Saves recordings in WAV format with timestamped filenames
- Recordings are stored in the `audios` directory

### Recording Specifications
- Format: WAV
- Sample Rate: 16kHz (or best available)
- Channels: Mono
- Bit Depth: 16-bit

## Troubleshooting

1. **No Audio Input Detected**
   - Check if your microphone is properly connected
   - Verify the microphone is recognized by the system
   - Try a different USB port if using a USB microphone

2. **GPIO Button Not Working**
   - Verify the button is properly connected to GPIO pin 2
   - Check the wiring connections


## File Management
- Recordings are saved in the `audios` directory
- Files are named with the format: `recording_YYYYMMDD_HHMMSS.wav`
- The program automatically creates the `audios` directory if it doesn't exist

