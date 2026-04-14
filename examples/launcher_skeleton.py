"""Unified game launcher with voice control and cursor management."""
import pygame
import threading
import sounddevice as sd
import numpy as np
import time
from transcriptions import Transcriber
from collections import deque

# Config
SAMPLE_RATE = 16000
CHUNK_SIZE = 512
BUFFER_DURATION = 2.0  # seconds to hold for voice commands
SILENCE_THRESHOLD = 300.0

class VoiceListener:
    """Background voice capture and transcription."""
    
    def __init__(self, transcriber):
        self.t = transcriber
        self.model = self.t.load_model("tiny", device="cpu")
        self.is_recording = False
        self.buffer = []
        self.lock = threading.Lock()
        self.last_command = None
        
    def start(self):
        """Start background listening thread."""
        self.is_recording = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        
    def stop(self):
        self.is_recording = False
        
    def _listen_loop(self):
        """Continuously listen and accumulate audio."""
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=CHUNK_SIZE,
            dtype='int16'
        )
        stream.start()
        
        max_chunks = int(SAMPLE_RATE * BUFFER_DURATION / CHUNK_SIZE)
        ring_buffer = deque(maxlen=max_chunks)
        
        try:
            while self.is_recording:
                data, _ = stream.read(CHUNK_SIZE)
                ring_buffer.append(data.copy().flatten())
                
        finally:
            stream.stop()
            stream.close()
    
    def transcribe_on_silence(self):
        """Transcribe accumumlated audio when silence detected."""
        # This would be called by your controller logic
        # when you want to finalize a voice command
        pass


class GameLauncher:
    """Main launcher with voice search and cursor control."""
    
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.t = Transcriber()
        self.voice = VoiceListener(self.t)
        self.games = []
        self.selected_index = 0
        
    def setup_controller(self):
        if pygame.joystick.get_count() == 0:
            print("No controller found")
            return False
        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        print(f"Controller: {self.controller.get_name()}")
        return True
    
    def load_games(self):
        """Load available games from config."""
        self.games = [
            {"name": "Game 1", "path": "path/to/game1.exe"},
            {"name": "Game 2", "path": "path/to/game2.exe"},
        ]
    
    def run(self):
        """Main loop."""
        self.setup_controller()
        self.load_games()
        self.voice.start()
        
        print("Launcher ready. Press A to record voice command, Y to launch.\n")
        
        try:
            while True:
                pygame.event.pump()
                
                # TODO: implement controller logic here
                # voice recording on A press
                # cursor movement on stick
                # game launch on Y press
                
                pygame.time.wait(10)
        finally:
            self.voice.stop()
            pygame.quit()


if __name__ == "__main__":
    launcher = GameLauncher()
    launcher.run()
