import sounddevice as sd
import numpy as np

print("Speak loudly during each test!\n")

devs = sd.query_devices()
input_devs = [(i, d) for i, d in enumerate(devs) if d['max_input_channels'] > 0 and i < 20]

for idx, dev in input_devs:
    try:
        data = sd.rec(8000, samplerate=16000, channels=1, dtype='float32', device=idx)
        sd.wait()
        rms = float(np.sqrt(np.mean(data ** 2)))
        peak = float(np.max(np.abs(data)))
        name = dev['name'][:45]
        status = '<<< AUDIO DETECTED >>>' if peak > 0.001 else 'silent'
        print(f'[{idx:2d}] {name:45s}  Peak={peak:.5f}  {status}')
    except Exception as e:
        name = dev['name'][:45]
        print(f'[{idx:2d}] {name:45s}  ERROR: {str(e)[:40]}')
