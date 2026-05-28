import { motion, AnimatePresence } from 'framer-motion';
import { useAssistantStore } from '../../store/assistantStore';

const emotionConfig: Record<string, { label: string; icon: string; color: string }> = {
  happy:    { label: 'Happy',    icon: '😊', color: 'text-yellow-400' },
  sad:      { label: 'Sad',      icon: '😢', color: 'text-blue-300' },
  angry:    { label: 'Angry',    icon: '😤', color: 'text-red-400' },
  cute:     { label: 'Cute',     icon: '🥰', color: 'text-pink-300' },
  romantic: { label: 'Romantic', icon: '💕', color: 'text-rose-300' },
  neutral:  { label: 'Calm',     icon: '💫', color: 'text-white/60' },
};

export const EmotionIndicator = () => {
  const { currentEmotion, appState } = useAssistantStore();

  if (appState !== 'speaking' || currentEmotion === 'neutral') return null;

  const config = emotionConfig[currentEmotion] || emotionConfig.neutral;

  return (
    <AnimatePresence>
      <motion.div
        key={currentEmotion}
        initial={{ opacity: 0, y: 10, scale: 0.8 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -10, scale: 0.8 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className={`flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 backdrop-blur-sm border border-white/10 ${config.color}`}
      >
        <span className="text-lg">{config.icon}</span>
        <span className="text-sm font-medium tracking-wide">{config.label}</span>
      </motion.div>
    </AnimatePresence>
  );
};
