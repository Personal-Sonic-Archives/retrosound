import pyaudio

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    print(f"Index {i}: {dev['name']}, Input Channels: {dev['maxInputChannels']}")

stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=11,
                frames_per_buffer=CHUNK)
print("Recording 5 seconds...")
data = stream.read(CHUNK * 5, exception_on_overflow=False)
with open('recording1.wav', 'wb') as f:
    f.write(data)
print("Done.")
stream.stop_stream()
stream.close()
p.terminate()

