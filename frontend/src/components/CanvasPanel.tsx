import { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, RotateCw, ShieldCheck } from 'lucide-react';
import { useCanvasStore } from '../store/canvasStore';
import { backendHttpUrl, wsClient } from '../services/websocket';

export function CanvasPanel() {
  const { canvasSessionId, lastUpdate, closeCanvas, triggerUpdate } = useCanvasStore();
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // 1. Reference check to ensure message comes from our specific iframe instance
      if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) {
        return;
      }

      // 2. Strict payload schema validation to block malformed or malicious messages
      if (
        !event.data ||
        typeof event.data !== 'object' ||
        event.data.type !== 'trigger_agent' ||
        typeof event.data.prompt !== 'string'
      ) {
        console.warn('[Canvas] Ignored invalid message payload:', event.data);
        return;
      }

      const { prompt } = event.data;
      console.log('[Canvas] Executing trigger_agent prompt:', prompt);
      
      // Send the prompt to the backend WebSocket
      wsClient.send('text_message', { text: prompt });
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [canvasSessionId]);

  if (!canvasSessionId) return null;

  // Use the backend directly so startup retries do not spam the Vite proxy.
  const iframeSrc = `${backendHttpUrl}/canvas/${canvasSessionId}/index.html?t=${lastUpdate}`;

  const handleRefresh = () => {
    triggerUpdate(canvasSessionId);
  };

  return (
    <motion.div
      initial={{ x: '100%', opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: '100%', opacity: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
      className="flex flex-col h-full w-[55%] bg-zinc-950 border-l border-white/10 z-10 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-white/[0.02] border-b border-white/10 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white/90">Canvas Workspace</h2>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <ShieldCheck size={14} />
            <span>Sandboxed</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Refresh button */}
          <button
            onClick={handleRefresh}
            title="Refresh workspace"
            className="p-2 text-zinc-400 hover:text-white hover:bg-white/5 rounded-lg transition-all"
          >
            <RotateCw size={18} />
          </button>

          {/* Close button */}
          <button
            onClick={closeCanvas}
            title="Close workspace"
            className="p-2 text-zinc-400 hover:text-white hover:bg-white/5 rounded-lg transition-all"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Frame body */}
      <div className="flex-1 w-full h-full bg-zinc-900 relative">
        <iframe
          ref={iframeRef}
          src={iframeSrc}
          // sandbox="allow-scripts allow-forms" strictly omits "allow-same-origin"
          sandbox="allow-scripts allow-forms"
          className="w-full h-full border-none bg-white"
          title="Maya Live Canvas"
        />
      </div>
    </motion.div>
  );
}
