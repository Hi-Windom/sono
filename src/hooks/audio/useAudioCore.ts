import { useRef, useState, useCallback, useEffect } from 'react';
import { useAudioWorker } from '../../workers/useAudioWorker';
import { loadSettings } from '../../utils/settingsStorage';
import {
  WSProgressControl,
  ProcessingOptions,
  AlgorithmVersion,
  QueueStatus,
} from '../../services/backendApi';
import { CacheHitInfo } from '../../components/RepairCacheModal';
import { AIRepairParams, RepairMode } from '../../utils/advancedAudioProcessing';
import { WavInfo } from '../../utils/wavParser';
import {
  AudioAnalysis,
  PlayMode,
  RepairResult,
  StuckInfo,
  AutoRenderInfo,
} from './types';

export function useAudioCore() {
  const savedSettings = loadSettings();
  const audioWorker = useAudioWorker();

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);
  const [backendProcessedBuffer, setBackendProcessedBuffer] = useState<AudioBuffer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isDecodingAudio, setIsDecodingAudio] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processingStep, setProcessingStep] = useState('');
  const [processingSource, setProcessingSource] = useState<'backend' | null>(null);
  const [isRenderLoading, setIsRenderLoading] = useState(false);
  const [fileHash, setFileHash] = useState<string | null>(null);
  const [params, setParams] = useState<AIRepairParams>(savedSettings.aiRepairParams);
  const [audioAnalysis, setAudioAnalysis] = useState<AudioAnalysis | null>(null);
  const [selectedMode, setSelectedMode] = useState<string>(savedSettings.selectedMode);
  const [playMode, setPlayMode] = useState<PlayMode>('original');
  const [processingOptions, setProcessingOptionsState] = useState<ProcessingOptions>(savedSettings.exportOptions);
  const [hasBeenProcessed, setHasBeenProcessed] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [backendDiag, setBackendDiag] = useState<string>('未检测');
  const [taskId, setTaskIdState] = useState<string | null>(null);
  const [algorithmVersion, setAlgorithmVersionState] = useState<string>(savedSettings.algorithmVersion);
  const [availableAlgorithms, setAvailableAlgorithms] = useState<AlgorithmVersion[]>([]);
  const [repairModes, setRepairModes] = useState<RepairMode[]>([]);
  const [wavInfo, setWavInfoState] = useState<WavInfo | null>(null);
  const [repairResult, setRepairResult] = useState<RepairResult | null>(null);
  const [backendWaveformPeaks, setBackendWaveformPeaks] = useState<number[][] | null>(null);
  const [originalWaveformPeaks, setOriginalWaveformPeaks] = useState<number[][] | null>(null);
  const [isTaskStuck, setIsTaskStuck] = useState(false);
  const [stuckInfo, setStuckInfo] = useState<StuckInfo | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [backendPreviewUrl, setBackendPreviewUrl] = useState<string | null>(null);
  const [renderDownloadUrl, setRenderDownloadUrl] = useState<string | null>(null);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [cacheHitInfo, setCacheHitInfo] = useState<CacheHitInfo | null>(null);
  const [showRepairCacheModal, setShowRepairCacheModal] = useState(false);
  const [autoRenderInfo, setAutoRenderInfo] = useState<AutoRenderInfo | null>(null);

  const versionInitializedRef = useRef(false);
  const taskIdRef = useRef<string | null>(null);
  const wsControlRef = useRef<WSProgressControl | null>(null);
  const wavInfoRef = useRef<WavInfo | null>(null);
  const pendingObjectURLRef = useRef<string | null>(null);
  const pendingPlayRef = useRef(false);
  const durationRef = useRef(0);
  const loadAudioSeqRef = useRef(0);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const startTimeRef = useRef(0);
  const playStartTimeRef = useRef(0);
  const pausedAtRef = useRef(0);
  const animationFrameRef = useRef<number>();
  const isPlayingRef = useRef(false);
  const fileHashRef = useRef<string | null>(null);
  const sessionRestoredRef = useRef(false);
  const restoreSeqRef = useRef(0);
  const forceReRepairRef = useRef(false);
  const forceRenderRef = useRef(false);
  const renderActiveRef = useRef(false);
  const streamingAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaSourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const playRef = useRef<(() => void) | null>(null);
  const audioBufferRef = useRef<AudioBuffer | null>(null);
  const backendProcessedBufferRef = useRef<AudioBuffer | null>(null);
  const seekInProgressRef = useRef(false);
  const processingOptionsRef = useRef<ProcessingOptions>(processingOptions);
  const algorithmVersionRef = useRef(algorithmVersion);
  const userEditingParamRef = useRef(false);
  const pendingSessionRef = useRef<{
    file: File;
    fileName: string;
    fileHash: string;
    taskId: string;
    hasBeenProcessed: boolean;
    wavInfo?: string;
    repairResult?: string;
    processingOptions?: string;
  } | null>(null);
  const backendAvailableRef = useRef(backendAvailable);
  const healthFailCountRef = useRef(0);

  const modeNodesRef = useRef<Record<PlayMode, { source: AudioBufferSourceNode; gain: GainNode } | null>>({
    original: null,
    backend: null,
  });
  const activeModeRef = useRef<PlayMode>('original');

  const setTaskId = useCallback((id: string | null) => {
    setTaskIdState(id);
    taskIdRef.current = id;
  }, []);

  const setWavInfo = useCallback((info: WavInfo | null) => {
    wavInfoRef.current = info;
    setWavInfoState(info);
  }, []);

  useEffect(() => { processingOptionsRef.current = processingOptions; }, [processingOptions]);
  useEffect(() => { algorithmVersionRef.current = algorithmVersion; }, [algorithmVersion]);

  useEffect(() => {
    audioBufferRef.current = audioBuffer;
  }, [audioBuffer]);

  useEffect(() => {
    backendProcessedBufferRef.current = backendProcessedBuffer;
  }, [backendProcessedBuffer]);

  const state = {
    audioFile, setAudioFile,
    audioBuffer, setAudioBuffer,
    backendProcessedBuffer, setBackendProcessedBuffer,
    isPlaying, setIsPlaying,
    currentTime, setCurrentTime,
    duration, setDuration,
    isProcessing, setIsProcessing,
    isDecodingAudio, setIsDecodingAudio,
    processingProgress, setProcessingProgress,
    processingStep, setProcessingStep,
    processingSource, setProcessingSource,
    isRenderLoading, setIsRenderLoading,
    fileHash, setFileHash,
    params, setParams,
    audioAnalysis, setAudioAnalysis,
    selectedMode, setSelectedMode,
    playMode, setPlayMode,
    processingOptions, setProcessingOptionsState,
    hasBeenProcessed, setHasBeenProcessed,
    backendAvailable, setBackendAvailable,
    backendDiag, setBackendDiag,
    taskId,
    algorithmVersion, setAlgorithmVersionState,
    availableAlgorithms, setAvailableAlgorithms,
    repairModes, setRepairModes,
    wavInfo,
    repairResult, setRepairResult,
    backendWaveformPeaks, setBackendWaveformPeaks,
    originalWaveformPeaks, setOriginalWaveformPeaks,
    isTaskStuck, setIsTaskStuck,
    stuckInfo, setStuckInfo,
    queueStatus, setQueueStatus,
    backendError, setBackendError,
    backendPreviewUrl, setBackendPreviewUrl,
    renderDownloadUrl, setRenderDownloadUrl,
    showDownloadModal, setShowDownloadModal,
    cacheHitInfo, setCacheHitInfo,
    showRepairCacheModal, setShowRepairCacheModal,
    autoRenderInfo, setAutoRenderInfo,
  };

  const refs = {
    versionInitializedRef,
    taskIdRef,
    wsControlRef,
    wavInfoRef,
    pendingObjectURLRef,
    pendingPlayRef,
    durationRef,
    loadAudioSeqRef,
    audioContextRef,
    sourceNodeRef,
    gainNodeRef,
    analyserRef,
    startTimeRef,
    playStartTimeRef,
    pausedAtRef,
    animationFrameRef,
    isPlayingRef,
    fileHashRef,
    sessionRestoredRef,
    restoreSeqRef,
    forceReRepairRef,
    forceRenderRef,
    renderActiveRef,
    streamingAudioRef,
    mediaSourceRef,
    playRef,
    audioBufferRef,
    backendProcessedBufferRef,
    seekInProgressRef,
    processingOptionsRef,
    algorithmVersionRef,
    userEditingParamRef,
    pendingSessionRef,
    backendAvailableRef,
    healthFailCountRef,
    modeNodesRef,
    activeModeRef,
  };

  return {
    audioWorker,
    savedSettings,
    state,
    refs,
    setTaskId,
    setWavInfo,
  };
}

export type AudioCoreState = ReturnType<typeof useAudioCore>['state'];
export type AudioCoreRefs = ReturnType<typeof useAudioCore>['refs'];
