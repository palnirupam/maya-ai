import { useRef, useState, useCallback } from 'react';
import { wsClient } from '../services/websocket';
import { useAssistantStore } from '../store/assistantStore';

export const useVoice = () => {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const startRecording = useCallback(async () => {
    try {
      wsClient.clearAudioQueue();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      mediaRecorderRef.current = mediaRecorder;

      const audioChunks: Blob[] = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm;codecs=opus' });
        const reader = new FileReader();
        reader.onload = () => {
          const base64Audio = (reader.result as string).split(',')[1];
          wsClient.send('audio_end', { audio: base64Audio });
        };
        reader.readAsDataURL(audioBlob);
      };

      // Start recording without timeslice
      mediaRecorder.start();
      setIsRecording(true);
      useAssistantStore.getState().setAppState('listening');

    } catch (err) {
      console.error("Microphone access denied:", err);
      useAssistantStore.getState().setAppState('error');
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      useAssistantStore.getState().setAppState('thinking');

      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    }
  }, [isRecording]);

  return { isRecording, startRecording, stopRecording };
};
