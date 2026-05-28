import { create } from 'zustand';
import type { Emotion } from './emotionStore';

type AppState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error' | 'offline';
export type CodingMode = 'suggest' | 'assisted' | 'autonomous';

export interface PendingToolRequest {
  request_id: string;
  tool_name: string;
  payload: any;
  risk_level: string;
}

interface AssistantState {
  isConnected: boolean;
  appState: AppState;
  messages: Array<{ role: 'user' | 'assistant', text: string }>;
  codingMode: CodingMode;
  pendingToolRequests: PendingToolRequest[];
  activeTheme: string;
  currentEmotion: Emotion;
  
  setConnected: (status: boolean) => void;
  setAppState: (state: AppState) => void;
  addMessage: (role: 'user' | 'assistant', text: string) => void;
  setCodingMode: (mode: CodingMode) => void;
  addToolRequest: (request: PendingToolRequest) => void;
  removeToolRequest: (request_id: string) => void;
  setActiveTheme: (theme: string) => void;
  setCurrentEmotion: (emotion: Emotion) => void;
}

export const useAssistantStore = create<AssistantState>((set) => ({
  isConnected: false,
  appState: 'offline',
  messages: [],
  codingMode: 'suggest',
  pendingToolRequests: [],
  activeTheme: 'light',
  currentEmotion: 'neutral',
  
  setConnected: (status) => set({ 
    isConnected: status, 
    appState: status ? 'idle' : 'offline' 
  }),
  setAppState: (state) => set({ appState: state }),
  addMessage: (role, text) => set((state) => ({ 
    messages: [...state.messages, { role, text }] 
  })),
  setCodingMode: (mode) => set({ codingMode: mode }),
  addToolRequest: (request) => set((state) => ({
    pendingToolRequests: [...state.pendingToolRequests, request]
  })),
  removeToolRequest: (request_id) => set((state) => ({
    pendingToolRequests: state.pendingToolRequests.filter(req => req.request_id !== request_id)
  })),
  setActiveTheme: (theme) => set({ activeTheme: theme }),
  setCurrentEmotion: (emotion) => set({ currentEmotion: emotion }),
}));
