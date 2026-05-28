import React from 'react';
import { motion } from 'framer-motion';
import { useAssistantStore } from '../../store/assistantStore';
import type { Emotion } from '../../store/emotionStore';

const themeColors: Record<string, string> = {
  cyan: "rgba(34, 211, 238, 0.6)",
  purple: "rgba(192, 132, 252, 0.6)",
  white: "rgba(255, 255, 255, 0.6)",
  orange: "rgba(251, 146, 60, 0.6)",
  light: "rgba(192, 132, 252, 0.6)",
};

const emotionColors: Record<Emotion, string> = {
  happy: "rgba(250, 204, 21, 0.7)",
  sad: "rgba(96, 165, 250, 0.7)",
  angry: "rgba(239, 68, 68, 0.7)",
  cute: "rgba(244, 114, 182, 0.7)",
  romantic: "rgba(251, 113, 133, 0.7)",
  neutral: "rgba(192, 132, 252, 0.6)",
};

export const VoiceOrb: React.FC = () => {
  const { appState, activeTheme, currentEmotion } = useAssistantStore();

  const showEmotionColor = appState === 'speaking' && currentEmotion !== 'neutral';
  const baseColor = showEmotionColor
    ? emotionColors[currentEmotion] || emotionColors.neutral
    : themeColors[activeTheme] || themeColors.purple;

  const variants = {
    offline: { scale: 1, opacity: 0.2, backgroundColor: "rgba(100, 100, 100, 0.5)", transition: { duration: 1.5 } },
    error: { scale: [1, 1.1, 1], backgroundColor: "rgba(239, 68, 68, 0.6)", transition: { duration: 0.5, repeat: Infinity } },
    idle: {
      scale: [1, 1.05, 1],
      opacity: [0.6, 0.8, 0.6],
      backgroundColor: baseColor,
      boxShadow: `0 0 40px ${baseColor}`,
      transition: { duration: 3, repeat: Infinity, ease: "easeInOut", backgroundColor: { duration: 1.5 } }
    },
    listening: {
      scale: [1, 1.1, 1],
      backgroundColor: "rgba(74, 222, 128, 0.6)",
      boxShadow: `0 0 60px rgba(74, 222, 128, 0.6)`,
      transition: { duration: 1.5, repeat: Infinity, ease: "easeInOut", backgroundColor: { duration: 0.5 } }
    },
    thinking: {
      rotate: 360,
      scale: [1, 1.05, 1],
      backgroundColor: baseColor,
      boxShadow: `0 0 60px ${baseColor}`,
      transition: { rotate: { duration: 2, repeat: Infinity, ease: "linear" }, scale: { duration: 2, repeat: Infinity }, backgroundColor: { duration: 1.5 } }
    },
    speaking: {
      scale: [1, 1.2, 1.1, 1.3, 1],
      opacity: [0.8, 1, 0.8],
      backgroundColor: baseColor,
      boxShadow: `0 0 80px ${baseColor}`,
      transition: { duration: 0.5, repeat: Infinity, repeatType: "reverse" as const, ease: "easeInOut", backgroundColor: { duration: 1.5 } }
    }
  };

  return (
    <div className="relative flex items-center justify-center w-64 h-64">
      <motion.div
        className="absolute w-full h-full rounded-full blur-3xl"
        animate={appState}
        variants={variants}
      />
      <motion.div
        className="relative w-40 h-40 rounded-full border-2 border-white/20 shadow-[0_0_50px_rgba(0,0,0,0.5)] flex items-center justify-center overflow-hidden z-10"
        animate={appState}
        variants={variants}
      >
        <img src="/src/assets/avatar/maya_core.png" alt="Maya Avatar" className="w-full h-full object-cover mix-blend-screen opacity-90" />
        <motion.div
          className="absolute inset-0 mix-blend-overlay"
          animate={{ backgroundColor: baseColor }}
          transition={{ duration: 0.8, ease: "easeInOut" }}
        />
      </motion.div>
    </div>
  );
};
