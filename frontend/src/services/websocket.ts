import { useAssistantStore } from '../store/assistantStore';
import { useEmotionStore } from '../store/emotionStore';

class AudioQueue {
  private queue: string[] = [];
  private isPlaying: boolean = false;
  private lastChunk: string = "";
  private audioCtx: AudioContext | null = null;
  private nextStartTime: number = 0;
  private activeSources: AudioBufferSourceNode[] = [];

  private initAudioContext() {
    if (!this.audioCtx) {
      this.audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
  }

  async addChunk(base64Audio: string) {
    if (this.lastChunk === base64Audio) return; // Deduplicate
    this.lastChunk = base64Audio;
    this.queue.push(base64Audio);
    
    this.initAudioContext();
    if (!this.isPlaying) {
      this.isPlaying = true;
      useAssistantStore.getState().setAppState('speaking');
      this.playNext();
    }
  }

  private async playNext() {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      // Wait briefly before switching to idle state in case new chunks are incoming
      setTimeout(() => {
        if (!this.isPlaying && this.queue.length === 0) {
          useAssistantStore.getState().setAppState('idle');
        }
      }, 300);
      return;
    }

    const base64Audio = this.queue.shift()!;
    
    try {
      const binaryString = window.atob(base64Audio);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);

      if (this.audioCtx) {
        // Decode the MP3/WAV array buffer
        const audioBuffer = await this.audioCtx.decodeAudioData(arrayBuffer);
        const source = this.audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.audioCtx.destination);

        const currentTime = this.audioCtx.currentTime;
        // Align schedule target time
        if (this.nextStartTime < currentTime) {
          this.nextStartTime = currentTime;
        }

        source.start(this.nextStartTime);
        this.activeSources.push(source);

        source.onended = () => {
          this.activeSources = this.activeSources.filter(s => s !== source);
        };

        this.nextStartTime += audioBuffer.duration;
      }
    } catch (e) {
      console.error("Failed to decode or play Web Audio chunk:", e);
    }

    // Recursively process and queue the next item
    this.playNext();
  }

  clear() {
    this.queue = [];
    this.isPlaying = false;
    this.lastChunk = "";
    this.nextStartTime = 0;
    
    // Instantly stop all active sources to interrupt/clear audio immediately
    this.activeSources.forEach((source) => {
      try {
        source.stop();
      } catch (err) {
        // Ignore if already stopped
      }
    });
    this.activeSources = [];
  }
}

class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private audioQueue = new AudioQueue();

  constructor(url: string) {
    this.url = url;
  }

  connect() {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log("WebSocket Connected");
      useAssistantStore.getState().setConnected(true);
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleEvent(data.type, data.data);
      } catch (e) {
        console.error("Invalid WS Message:", event.data);
      }
    };

    this.ws.onclose = () => {
      console.log("WebSocket Disconnected");
      useAssistantStore.getState().setConnected(false);
      this.attemptReconnect();
    };
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      setTimeout(() => {
        this.reconnectAttempts++;
        this.connect();
      }, 2000);
    }
  }

  private handleEvent(type: string, payload: any) {
    const store = useAssistantStore.getState();

    switch (type) {
      case 'status_update':
        // Don't override 'speaking' state from backend while audio is playing locally
        if (payload.appState && payload.appState !== 'speaking') {
          store.setAppState(payload.appState);
        } else if (payload.appState === 'idle') {
          store.setAppState('idle');
        }
        break;
      case 'assistant_message':
        store.addMessage('assistant', payload.text);
        break;
      case 'user_message':
        store.addMessage('user', payload.text);
        break;
      case 'audio_response':
        this.audioQueue.addChunk(payload.audio);
        if (payload.emotion) {
          useAssistantStore.getState().setCurrentEmotion(payload.emotion);
          useEmotionStore.getState().setEmotion(payload.emotion);
        }
        break;
      case 'app_shutdown':
        console.log("Shutting down app natively...");
        try {
          if ((window as any).__TAURI__) {
            (window as any).__TAURI__.window.appWindow.close();
          } else {
            window.close();
          }
        } catch(e) {
          console.error("Failed to close window natively", e);
        }
        break;
      case 'mode_changed':
        console.log("Mode changed natively:", payload.mode);
        store.setActiveTheme(payload.theme);
        break;
    }
  }

  clearAudioQueue() {
    this.audioQueue.clear();
    this.send('user_interrupted', {});
  }

  send(type: string, data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }


  disconnect() {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.audioQueue.clear();
  }
}

export const wsClient = new WebSocketClient('ws://127.0.0.1:8000/ws');
