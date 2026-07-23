/**
 * WaveformVisualizer — Gemini Live-style real-time audio waveform bars.
 *
 * Shows animated bars that react to microphone volume.
 * Bars are taller and brighter when the user speaks.
 * During Maya's speaking state the bars glow in the theme color.
 */

import React from 'react';
import { motion } from 'framer-motion';
import type { SessionState } from '../../hooks/useVoiceSession';

interface WaveformVisualizerProps {
  volume: number;         // 0–255, from useVoiceSession
  sessionState: SessionState;
}

const BAR_COUNT = 5;

// Heights (in px) for each bar when at max volume
const MAX_HEIGHTS = [18, 32, 48, 32, 18];

export const WaveformVisualizer: React.FC<WaveformVisualizerProps> = ({
  volume,
  sessionState,
}) => {
  const isRecording = sessionState === 'RECORDING';
  const isSpeaking  = sessionState === 'MAYA_SPEAKING';
  const isListening = sessionState === 'LISTENING';
  const isVisible   = isRecording || isSpeaking || isListening;

  if (!isVisible) return null;

  // Normalize volume 0→1
  const norm = Math.min(volume / 180, 1);

  // Bar color
  const barColor = isRecording
    ? 'rgba(74, 222, 128, 0.9)'    // green — user speaking
    : isSpeaking
    ? 'rgba(192, 132, 252, 0.9)'   // purple — Maya speaking
    : 'rgba(148, 163, 184, 0.5)';  // slate — waiting/idle

  const glowColor = isRecording
    ? 'rgba(74, 222, 128, 0.4)'
    : isSpeaking
    ? 'rgba(192, 132, 252, 0.4)'
    : 'transparent';

  return (
    <div className="flex items-center justify-center gap-1.5 h-14">
      {Array.from({ length: BAR_COUNT }).map((_, i) => {
        // Each bar gets a slightly different multiplier for a natural look
        const offset = Math.sin((i / BAR_COUNT) * Math.PI) * 0.4 + 0.6;
        const heightPx = isListening
          ? 4  // idle pulse — minimal
          : Math.max(4, MAX_HEIGHTS[i] * norm * offset);

        return (
          <motion.div
            key={i}
            style={{
              width: 5,
              borderRadius: 4,
              backgroundColor: barColor,
              boxShadow: `0 0 8px ${glowColor}`,
            }}
            animate={{ height: heightPx }}
            transition={{
              duration: 0.08,
              ease: 'easeOut',
            }}
          />
        );
      })}
    </div>
  );
};
