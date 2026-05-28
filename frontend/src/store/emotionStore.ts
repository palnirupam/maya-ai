import { create } from 'zustand';

export type Emotion = 'happy' | 'sad' | 'angry' | 'cute' | 'romantic' | 'neutral';

interface EmotionState {
  currentEmotion: Emotion;
  previousEmotion: Emotion;
  emotionIntensity: number;
  setEmotion: (emotion: Emotion) => void;
  resetEmotion: () => void;
}

export const useEmotionStore = create<EmotionState>((set) => ({
  currentEmotion: 'neutral',
  previousEmotion: 'neutral',
  emotionIntensity: 0.5,
  setEmotion: (emotion) =>
    set((state) => ({
      previousEmotion: state.currentEmotion,
      currentEmotion: emotion,
      emotionIntensity: emotion === 'neutral' ? 0.5 : 1.0,
    })),
  resetEmotion: () =>
    set({ currentEmotion: 'neutral', previousEmotion: 'neutral', emotionIntensity: 0.5 }),
}));
