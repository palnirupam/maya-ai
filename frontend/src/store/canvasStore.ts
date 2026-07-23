import { create } from 'zustand';

interface CanvasState {
  isOpen: boolean;
  canvasSessionId: string | null;
  lastUpdate: number;
  openCanvas: (sessionId: string) => void;
  closeCanvas: () => void;
  triggerUpdate: (sessionId: string) => void;
}

export const useCanvasStore = create<CanvasState>((set) => ({
  isOpen: false,
  canvasSessionId: null,
  lastUpdate: 0,
  openCanvas: (sessionId) => set({ isOpen: true, canvasSessionId: sessionId, lastUpdate: Date.now() }),
  closeCanvas: () => set({ isOpen: false }),
  triggerUpdate: (sessionId) => set({
    isOpen: true,
    canvasSessionId: sessionId,
    lastUpdate: Date.now(),
  }),
}));
