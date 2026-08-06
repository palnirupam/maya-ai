/**
 * useVoiceSession — Gemini Live-style continuous voice session hook.
 *
 * Flow:
 *   startSession() → mic open → VAD loop begins
 *   User speaks     → RECORDING state (waveform animates)
 *   User pauses     → 1500ms silence → audio blob sent → THINKING
 *   Maya replies    → MAYA_SPEAKING (audio plays from WebSocket)
 *   Audio ends      → back to LISTENING (loop)
 *   User speaks mid-reply → INTERRUPT → Maya stops → LISTENING
 *   endSession()    → everything stops cleanly
 */

import { useRef, useState, useCallback, useEffect } from 'react';
import { wsClient } from '../services/websocket';
import { useAssistantStore } from '../store/assistantStore';

// ── Types ──────────────────────────────────────────────────────────────────────

export type SessionState =
  | 'SESSION_IDLE'
  | 'LISTENING'
  | 'RECORDING'
  | 'SENDING'
  | 'THINKING'
  | 'MAYA_SPEAKING'
  | 'SESSION_ERROR';

// ── Constants ──────────────────────────────────────────────────────────────────

/** ms of silence before treating speech as complete (1500ms for Bengali rhythm) */
const SILENCE_THRESHOLD_MS = 1500;

/** Volume (0–255) above which we consider the user to be speaking */
const SPEAKING_VOLUME_THRESHOLD = 30;

/** Volume threshold for INTERRUPT detection — higher to avoid false positives */
const INTERRUPT_VOLUME_THRESHOLD = 50;

/** Max WebSocket blob size in bytes — skip send if exceeded to prevent overflow */
const MAX_BLOB_BYTES = 10 * 1024 * 1024; // 10 MB

/** Hard cap on recording duration — prevents 1-min+ recordings that freeze Whisper */
const MAX_RECORDING_MS = 25_000; // 25 seconds

/** Delay before auto-resetting from SESSION_ERROR → SESSION_IDLE */
const ERROR_RESET_DELAY_MS = 3000;

// ── Hook ───────────────────────────────────────────────────────────────────────

export const useVoiceSession = () => {
  const [sessionState, setSessionState] = useState<SessionState>('SESSION_IDLE');

  // Refs — avoid stale closures inside audio callbacks
  const sessionActiveRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxRecordingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isRecordingRef = useRef(false);
  const isMayaSpeakingRef = useRef(false);
  const vadLoopRef = useRef<number | null>(null);
  const errorResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Expose real-time volume for WaveformVisualizer (0–255)
  const [volume, setVolume] = useState(0);

  const { setAppState } = useAssistantStore();

  // ── Internal helpers ────────────────────────────────────────────────────────

  const _setState = useCallback((s: SessionState) => {
    setSessionState(s);
    // Keep global appState in sync for VoiceOrb / EmotionIndicator
    switch (s) {
      case 'LISTENING':    setAppState('listening'); break;
      case 'RECORDING':    setAppState('listening'); break; // orb stays green
      case 'SENDING':
      case 'THINKING':     setAppState('thinking');  break;
      case 'MAYA_SPEAKING':setAppState('speaking');  break;
      case 'SESSION_IDLE': setAppState('idle');       break;
      case 'SESSION_ERROR':setAppState('error');      break;
    }
  }, [setAppState]);

  const _clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const _clearMaxRecordingTimer = useCallback(() => {
    if (maxRecordingTimerRef.current) {
      clearTimeout(maxRecordingTimerRef.current);
      maxRecordingTimerRef.current = null;
    }
  }, []);

  /** Stop and discard the current MediaRecorder without sending audio. */
  const _abortRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecordingRef.current) {
      mediaRecorderRef.current.onstop = null; // prevent onstop from sending
      mediaRecorderRef.current.stop();
      isRecordingRef.current = false;
    }
    audioChunksRef.current = [];
    _clearSilenceTimer();
    _clearMaxRecordingTimer();
  }, [_clearSilenceTimer, _clearMaxRecordingTimer]);

  /** Finalize current recording and send blob over WebSocket. */
  const _finalizeAndSend = useCallback(() => {
    if (!mediaRecorderRef.current || !isRecordingRef.current) return;
    _clearSilenceTimer();
    _clearMaxRecordingTimer();

    // onstop fires after .stop() — we send audio there
    mediaRecorderRef.current.stop();
    isRecordingRef.current = false;
    _setState('SENDING');
  }, [_clearSilenceTimer, _clearMaxRecordingTimer, _setState]);

  /** Start a fresh MediaRecorder on the existing stream. */
  const _startRecorder = useCallback(() => {
    if (!streamRef.current) return;

    const chunks: Blob[] = [];
    audioChunksRef.current = chunks;

    const recorder = new MediaRecorder(streamRef.current, {
      mimeType: 'audio/webm;codecs=opus',
    });
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });

      // Blob size guard — skip if too large
      if (blob.size > MAX_BLOB_BYTES) {
        console.warn('[VoiceSession] Audio blob too large — skipping send.');
        if (sessionActiveRef.current) _setState('LISTENING');
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const b64 = (reader.result as string).split(',')[1];
        wsClient.send('audio_end', { audio: b64 });
        _setState('THINKING');
      };
      reader.readAsDataURL(blob);
    };

    recorder.start();
    isRecordingRef.current = true;

    // Hard cap: auto-send after MAX_RECORDING_MS regardless of silence
    maxRecordingTimerRef.current = setTimeout(() => {
      console.warn('[VoiceSession] Max recording duration reached — auto-finalizing.');
      if (isRecordingRef.current) _finalizeAndSend();
    }, MAX_RECORDING_MS);
  }, [_finalizeAndSend, _setState]);

  // ── VAD loop ────────────────────────────────────────────────────────────────

  const _startVADLoop = useCallback(() => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);

    const tick = () => {
      if (!sessionActiveRef.current) return;

      analyserRef.current!.getByteFrequencyData(dataArray);
      const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
      setVolume(avg);

      // ── Interrupt: user speaks while Maya is speaking ──
      if (isMayaSpeakingRef.current) {
        if (avg > INTERRUPT_VOLUME_THRESHOLD) {
          console.log('[VoiceSession] Interrupt detected!');
          wsClient.send('user_interrupted', {});
          wsClient.clearAudioQueue?.();
          isMayaSpeakingRef.current = false;
          _abortRecording();
          _setState('LISTENING');
          // Do not start a recorder just because playback was interrupted.
          // The normal VAD branch will start it only while speech is actually
          // present, which avoids uploading Maya's speaker echo / trailing noise.
        }
        vadLoopRef.current = requestAnimationFrame(tick);
        return;
      }

      // ── Normal VAD: detect speech start / silence ──
      if (avg > SPEAKING_VOLUME_THRESHOLD) {
        // User is speaking
        _clearSilenceTimer();

        if (!isRecordingRef.current) {
          // Speech just started
          _startRecorder();
          _setState('RECORDING');
        }
      } else {
        // Silence
        if (isRecordingRef.current && !silenceTimerRef.current) {
          // Start silence countdown
          silenceTimerRef.current = setTimeout(() => {
            silenceTimerRef.current = null;
            if (isRecordingRef.current) {
              _finalizeAndSend();
            }
          }, SILENCE_THRESHOLD_MS);
        }
      }

      vadLoopRef.current = requestAnimationFrame(tick);
    };

    vadLoopRef.current = requestAnimationFrame(tick);
  }, [_abortRecording, _clearSilenceTimer, _finalizeAndSend, _startRecorder, _setState]);

  // ── WebSocket event listeners ────────────────────────────────────────────────

  useEffect(() => {
    const onMayaSpeaking = () => {
      if (!sessionActiveRef.current) return;
      isMayaSpeakingRef.current = true;
      _setState('MAYA_SPEAKING');
    };

    const onSessionReady = () => {
      if (!sessionActiveRef.current) return;
      // session_ready fires after all audio chunks sent;
      // actual restart happens after audio.onended in wsClient — see websocket.ts
    };

    const onAudioEnded = () => {
      // Called by wsClient after the last audio chunk finishes playing
      if (!sessionActiveRef.current) return;
      isMayaSpeakingRef.current = false;
      _setState('LISTENING');
      // Stay armed but idle. The VAD loop starts MediaRecorder only after it
      // detects the user's voice. Starting it here records pure silence and
      // sends that silence 1.5s later, which can make STT invent a new turn.
    };

    const onError = () => {
      if (!sessionActiveRef.current) return;
      _setState('SESSION_ERROR');
      errorResetTimerRef.current = setTimeout(() => {
        if (sessionActiveRef.current) _setState('LISTENING');
      }, ERROR_RESET_DELAY_MS);
    };

    wsClient.on?.('speaking_start', onMayaSpeaking);
    wsClient.on?.('session_ready', onSessionReady);
    wsClient.on?.('audio_ended', onAudioEnded);
    wsClient.on?.('error', onError);

    return () => {
      wsClient.off?.('speaking_start', onMayaSpeaking);
      wsClient.off?.('session_ready', onSessionReady);
      wsClient.off?.('audio_ended', onAudioEnded);
      wsClient.off?.('error', onError);
    };
  }, [_setState]);

  // ── Public API ───────────────────────────────────────────────────────────────

  const startSession = useCallback(async () => {
    if (sessionActiveRef.current) return;

    try {
      wsClient.clearAudioQueue?.();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 },
      });
      streamRef.current = stream;

      const ctx = new AudioContext();
      audioContextRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      sessionActiveRef.current = true;
      isMayaSpeakingRef.current = false;
      _setState('LISTENING');

      _startVADLoop();

    } catch (err) {
      console.error('[VoiceSession] Mic access denied:', err);
      _setState('SESSION_ERROR');
      errorResetTimerRef.current = setTimeout(() => {
        _setState('SESSION_IDLE');
      }, ERROR_RESET_DELAY_MS);
    }
  }, [_setState, _startVADLoop]);

  const endSession = useCallback(() => {
    sessionActiveRef.current = false;

    // Cancel VAD loop
    if (vadLoopRef.current !== null) {
      cancelAnimationFrame(vadLoopRef.current);
      vadLoopRef.current = null;
    }

    // Stop any active recording
    _abortRecording();

    // Stop mic tracks
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    // Close AudioContext
    audioContextRef.current?.close();
    audioContextRef.current = null;
    analyserRef.current = null;

    // Clear timers
    _clearSilenceTimer();
    _clearMaxRecordingTimer();
    if (errorResetTimerRef.current) {
      clearTimeout(errorResetTimerRef.current);
      errorResetTimerRef.current = null;
    }

    isMayaSpeakingRef.current = false;
    setVolume(0);
    _setState('SESSION_IDLE');
  }, [_abortRecording, _clearSilenceTimer, _clearMaxRecordingTimer, _setState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { endSession(); };
  }, [endSession]);

  return {
    sessionState,
    volume,         // 0–255, use for WaveformVisualizer
    startSession,
    endSession,
    isSessionActive: sessionState !== 'SESSION_IDLE',
  };
};
