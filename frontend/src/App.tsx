import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { VoiceOrb } from './components/assistant/VoiceOrb';
import { EmotionIndicator } from './components/assistant/EmotionIndicator';
import { WaveformVisualizer } from './components/assistant/WaveformVisualizer';
import { ToolApprovalCard } from './components/chat/ToolApprovalCard';
import { SettingsModal } from './components/ui/SettingsModal';
import { backendHttpUrl, wsClient } from './services/websocket';
import { useAssistantStore } from './store/assistantStore';
import { useVoiceSession } from './hooks/useVoiceSession';
import { MicOff, Settings, Radio } from 'lucide-react';
import { useCanvasStore } from './store/canvasStore';
import { CanvasPanel } from './components/CanvasPanel';

// Status labels for each session state
const SESSION_LABELS: Record<string, string> = {
  SESSION_IDLE:    'Tap to start a conversation',
  LISTENING:       'Listening...',
  RECORDING:       "I'm listening...",
  SENDING:         'Processing your voice...',
  THINKING:        'Thinking...',
  MAYA_SPEAKING:   'Maya is speaking',
  SESSION_ERROR:   'Something went wrong — retrying...',
};

function App() {
  const { appState, pendingToolRequests } = useAssistantStore();
  const { sessionState, volume, startSession, endSession, isSessionActive } = useVoiceSession();
  const { isOpen: isCanvasOpen } = useCanvasStore();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Also keep text input available as fallback
  const [textValue, setTextValue] = useState('');

  useEffect(() => {
    wsClient.connect();
    return () => wsClient.disconnect();
  }, []);

  // ── Canvas polling fallback ──────────────────────────────────────────────────
  // Polls /canvas/latest every 2s. If a newer canvas was written (mtime changed),
  // opens the panel automatically — even if the WebSocket broadcast was missed.
  useEffect(() => {
    let lastMtime = 0;
    const poll = async () => {
      try {
        const r = await fetch(`${backendHttpUrl}/canvas/latest`);
        if (!r.ok) return;
        const { session_id, updated_at } = await r.json();
        if (session_id && updated_at > lastMtime) {
          lastMtime = updated_at;
          useCanvasStore.getState().triggerUpdate(session_id);
        }
      } catch { /* backend not ready yet */ }
    };
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  const handleTextSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (textValue.trim() && appState !== 'offline') {
      wsClient.clearAudioQueue?.();
      wsClient.send('text_message', { text: textValue.trim() });
      setTextValue('');
    }
  };

  return (
    <div className="relative flex flex-row items-stretch h-screen w-full bg-background text-foreground overflow-hidden">
      {/* Left Panel: Chat Assistant */}
      <div className={`relative flex flex-col items-center justify-center h-full transition-all duration-500 ease-in-out ${isCanvasOpen ? 'w-[45%] border-r border-white/10' : 'w-full'}`}>
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
          <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-primary/10 rounded-full blur-[120px]" />
          {/* Extra glow when session active */}
          <AnimatePresence>
            {isSessionActive && (
              <motion.div
                key="session-glow"
                className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full blur-[160px]"
                style={{ backgroundColor: sessionState === 'RECORDING' ? 'rgba(34,197,94,0.08)' : 'rgba(192,132,252,0.08)' }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1 }}
              />
            )}
          </AnimatePresence>
        </div>

        <div className="z-10 flex flex-col items-center gap-8 w-full max-w-2xl px-4">
          {/* Maya Orb — pass sessionState as appState override when session is active */}
          <div className="relative">
            <VoiceOrb />
            <div className="absolute -bottom-2 left-1/2 -translate-x-1/2">
              <EmotionIndicator />
            </div>
          </div>

          {/* Name + Status */}
          <div className="text-center">
            <h1 className="text-4xl font-bold tracking-tight text-white/90 drop-shadow-lg">Maya</h1>
            <motion.p
              key={sessionState}
              className="text-sm mt-2 text-white/50 tracking-widest"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              {SESSION_LABELS[sessionState] ?? appState.toUpperCase()}
            </motion.p>
          </div>

          {/* Live Waveform (visible during session) */}
          <AnimatePresence>
            {isSessionActive && (
              <motion.div
                key="waveform"
                initial={{ opacity: 0, scaleY: 0 }}
                animate={{ opacity: 1, scaleY: 1 }}
                exit={{ opacity: 0, scaleY: 0 }}
                transition={{ duration: 0.3 }}
              >
                <WaveformVisualizer volume={volume} sessionState={sessionState} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Tool Approval Queue */}
          {pendingToolRequests.length > 0 && (
            <div className="w-full flex flex-col gap-2 max-h-64 overflow-y-auto pr-2">
              {pendingToolRequests.map((req) => (
                <ToolApprovalCard key={req.request_id} request={req} />
              ))}
            </div>
          )}

          {/* ── Main Session Button ── */}
          {!isSessionActive ? (
            <motion.button
              id="start-session-btn"
              onClick={startSession}
              disabled={appState === 'offline'}
              className="flex items-center gap-3 px-10 py-5 rounded-full font-semibold text-base transition-all shadow-2xl bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
            >
              <Radio size={22} />
              Start Session
            </motion.button>
          ) : (
            <div className="flex flex-col items-center gap-3">
              {/* Interrupt button — shown while Maya is speaking */}
              <AnimatePresence>
                {sessionState === 'MAYA_SPEAKING' && (
                  <motion.p
                    key="interrupt-hint"
                    className="text-xs text-white/40 tracking-wide"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    Speak to interrupt Maya
                  </motion.p>
                )}
              </AnimatePresence>

              {/* End Session button */}
              <motion.button
                id="end-session-btn"
                onClick={endSession}
                className="flex items-center gap-3 px-8 py-4 rounded-full font-semibold text-sm transition-all shadow-xl bg-red-500/20 hover:bg-red-500/40 text-red-300 border border-red-500/30"
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.97 }}
              >
                <MicOff size={18} />
                End Session
              </motion.button>
            </div>
          )}

          {/* Text Input Fallback */}
          <form
            onSubmit={handleTextSend}
            className="w-full max-w-md flex gap-2"
          >
            <input
              type="text"
              value={textValue}
              onChange={(e) => setTextValue(e.target.value)}
              placeholder="Or type your message here..."
              disabled={appState === 'offline' || appState === 'thinking'}
              className="flex-1 bg-black/20 border border-white/10 rounded-full px-6 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 text-white placeholder:text-white/30 backdrop-blur-sm transition-all"
            />
            <button
              type="submit"
              disabled={appState === 'offline' || appState === 'thinking' || !textValue.trim()}
              className="bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-3 rounded-full text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </form>
        </div>
      </div>

      {/* Right Panel: Live Canvas */}
      <AnimatePresence>
        {isCanvasOpen && <CanvasPanel />}
      </AnimatePresence>
    </div>
  );
}

export default App;
