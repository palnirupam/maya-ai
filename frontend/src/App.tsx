import { useEffect, useState } from 'react';
import { VoiceOrb } from './components/assistant/VoiceOrb';
import { EmotionIndicator } from './components/assistant/EmotionIndicator';
import { ToolApprovalCard } from './components/chat/ToolApprovalCard';
import { SettingsModal } from './components/ui/SettingsModal';
import { wsClient } from './services/websocket';
import { useAssistantStore } from './store/assistantStore';
import { useVoice } from './hooks/useVoice';
import { Mic, Settings } from 'lucide-react';

function App() {
  const { appState, pendingToolRequests } = useAssistantStore();
  const { isRecording, startRecording, stopRecording } = useVoice();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    wsClient.connect();
    return () => wsClient.disconnect();
  }, []);

  return (
    <div className="relative flex flex-col items-center justify-center h-screen w-full bg-background text-foreground overflow-hidden">
      
      {/* Settings Button */}
      <button 
        onClick={() => setIsSettingsOpen(true)}
        className="absolute top-6 right-6 text-slate-400 hover:text-white transition-colors z-20"
      >
        <Settings size={28} />
      </button>

      {/* Settings Modal */}
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />

      {/* Background Decor */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
        <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-primary/10 rounded-full blur-[120px]"></div>
      </div>

      <div className="z-10 flex flex-col items-center gap-12 w-full max-w-2xl px-4">
        <div className="relative">
          <VoiceOrb />
          <div className="absolute -bottom-2 left-1/2 -translate-x-1/2">
            <EmotionIndicator />
          </div>
        </div>
        
        <div className="text-center">
          <h1 className="text-4xl font-bold tracking-tight text-white/90 drop-shadow-lg">Maya</h1>
          <p className="text-sm mt-2 text-white/50 tracking-widest uppercase">
            {appState.toUpperCase()}
          </p>
        </div>

        {/* Tool Approval Queue */}
        {pendingToolRequests.length > 0 && (
          <div className="w-full flex flex-col gap-2 max-h-64 overflow-y-auto pr-2">
            {pendingToolRequests.map((req) => (
              <ToolApprovalCard key={req.request_id} request={req} />
            ))}
          </div>
        )}

        {/* Tap to Talk Button */}
        <button
          onClick={isRecording ? stopRecording : startRecording}
          disabled={appState === 'offline'}
          className={`flex items-center gap-2 px-8 py-4 rounded-full font-semibold transition-all shadow-xl ${
            isRecording 
              ? 'bg-red-500 hover:bg-red-600 text-white animate-pulse' 
              : 'bg-primary hover:bg-primary/90 text-primary-foreground'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <Mic size={24} />
          {isRecording ? "Tap to Stop" : "Tap to Speak"}
        </button>

        {/* Text Input Fallback */}
        <form 
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.target as HTMLFormElement;
            const input = form.elements.namedItem('textInput') as HTMLInputElement;
            if (input.value.trim() && appState !== 'offline') {
              wsClient.clearAudioQueue();
              wsClient.send('text_message', { text: input.value.trim() });
              input.value = '';
            }
          }}
          className="w-full max-w-md mt-4 flex gap-2"
        >
          <input 
            type="text" 
            name="textInput"
            placeholder="Or type your message here..." 
            disabled={appState === 'offline' || appState === 'thinking'}
            className="flex-1 bg-black/20 border border-white/10 rounded-full px-6 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 text-white placeholder:text-white/30 backdrop-blur-sm transition-all"
          />
          <button 
            type="submit"
            disabled={appState === 'offline' || appState === 'thinking'}
            className="bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-3 rounded-full text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

export default App;
