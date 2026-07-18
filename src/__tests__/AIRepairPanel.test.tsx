// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { defaultVocalRepairParams, defaultInstrumentRepairParams } from '../utils/settingsStorage';
import { AIRepairPanel } from '../components/AIRepairPanel';
import { defaultAIRepairParams, RepairMode } from '../utils/advancedAudioProcessing';
import { AlgorithmVersion, ProcessingOptions } from '../services/backendApi';

vi.mock('../services/backendApi', () => ({
  fetchMemoryInfo: vi.fn().mockResolvedValue({
    estimated_memory_bytes: 1024 * 1024 * 100,
    is_sufficient: true,
    working_sr: 48000,
    use_float32: false,
    has_streaming: true,
    memory_saving: 0,
    available_memory_bytes: 1024 * 1024 * 1024,
    total_memory_bytes: 1024 * 1024 * 1024 * 4,
    used_memory_bytes: 1024 * 1024 * 512,
  }),
  fetchStorageEstimate: vi.fn().mockResolvedValue({
    estimated_storage_bytes: 1024 * 1024 * 50,
    estimated_output_mb: 50,
    estimated_output_bytes: 1024 * 1024 * 50,
    available_disk_bytes: 1024 * 1024 * 1024,
    total_disk_bytes: 1024 * 1024 * 1024 * 10,
    used_disk_bytes: 1024 * 1024 * 512,
    is_sufficient: true,
  }),
  fetchRenderCache: vi.fn().mockResolvedValue([]),
}));

const mockAlgorithms: AlgorithmVersion[] = [
  {
    name: 'v2.4a',
    label: 'v2.4a 移动版',
    description: '移动端优化版本',
    defaultParams: {},
    paramRanges: {},
    modes: [],
    supportsDualTrack: false,
  },
  {
    name: 'v3.1a',
    label: 'v3.1a 双轨移动版',
    description: '双轨移动端优化版本',
    defaultParams: {},
    paramRanges: {},
    modes: [],
    supportsDualTrack: true,
  },
];

const mockModes: RepairMode[] = [
  {
    name: '轻度修复',
    description: '轻微修复，保留原始音质',
    icon: 'soft',
    params: { ...defaultAIRepairParams },
  },
  {
    name: '标准修复',
    description: '平衡修复效果和音质',
    icon: 'standard',
    params: { ...defaultAIRepairParams, deClipping: 0.5 },
  },
];

const defaultProcessingOptions: ProcessingOptions = {
  sampleRate: 48000,
  bitDepth: 24,
  outputVolume: 0,
};

describe('AIRepairPanel', () => {
  const defaultProps = {
    params: { ...defaultAIRepairParams },
    analysis: null,
    selectedMode: '轻度修复',
    modes: mockModes,
    processingOptions: defaultProcessingOptions,
    algorithmVersion: 'v2.4a',
    availableAlgorithms: mockAlgorithms,
    onAlgorithmChange: vi.fn(),
    onParamChange: vi.fn(),
    onReset: vi.fn(),
    onModeSelect: vi.fn(),
    onApply: vi.fn(),
    onOptionsChange: vi.fn(),
    disabled: false,
    duration: 60,
    channels: 2,
    backendAvailable: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the panel title', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('AI音频修复')).toBeTruthy();
  });

  it('should render algorithm selector section', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('算法版本')).toBeTruthy();
  });

  it('should render repair mode selector with modes', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('轻度修复')).toBeTruthy();
    expect(screen.getByText('标准修复')).toBeTruthy();
  });

  it('should render volume slider', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('输出音量')).toBeTruthy();
  });

  it('should render reset and apply buttons', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('重置')).toBeTruthy();
    expect(screen.getByText('开始修复')).toBeTruthy();
  });

  it('should call onReset when reset button is clicked', () => {
    const onReset = vi.fn();
    render(<AIRepairPanel {...defaultProps} onReset={onReset} />);
    
    const resetButton = screen.getByText('重置');
    fireEvent.click(resetButton);
    
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('should call onApply when apply button is clicked', () => {
    const onApply = vi.fn();
    render(<AIRepairPanel {...defaultProps} onApply={onApply} />);
    
    const applyButton = screen.getByText('开始修复');
    fireEvent.click(applyButton);
    
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('should have disabled styling when disabled prop is true', () => {
    const { container } = render(<AIRepairPanel {...defaultProps} disabled />);
    
    const buttons = container.querySelectorAll('button');
    const disabledButtons = Array.from(buttons).filter(btn => 
      btn.classList.contains('opacity-50') || btn.classList.contains('cursor-not-allowed')
    );
    expect(disabledButtons.length).toBeGreaterThan(0);
  });

  it('should show dual track repair button in dual track mode', () => {
    render(
      <AIRepairPanel
        {...defaultProps}
        isDualTrackMode
        onDualTrackRepair={vi.fn()}
        vocalParams={defaultVocalRepairParams}
        accompanimentParams={defaultInstrumentRepairParams}
        mixRatio={0.5}
      />
    );
    
    expect(screen.getByText('双轨修复')).toBeTruthy();
  });

  it('should display analysis data when provided', () => {
    const analysis = {
      spectralFlatness: 0.3,
      dynamicRange: 60,
      stereoBalance: 0.95,
      peakLevel: 0.8,
      issues: ['clipping', 'noise'],
    };
    
    render(<AIRepairPanel {...defaultProps} analysis={analysis} />);
    
    expect(screen.getByText(/频谱平坦度/)).toBeTruthy();
    expect(screen.getByText(/动态范围/)).toBeTruthy();
    expect(screen.getByText(/峰值电平/)).toBeTruthy();
    expect(screen.getByText(/立体声/)).toBeTruthy();
    expect(screen.getByText(/问题:/)).toBeTruthy();
  });

  it('should display output specification section', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('交付规格')).toBeTruthy();
  });

  it('should display storage estimate card', () => {
    render(<AIRepairPanel {...defaultProps} />);
    expect(screen.getByText('预估输出大小')).toBeTruthy();
  });

  it('should not show analysis section when analysis is null', () => {
    render(<AIRepairPanel {...defaultProps} analysis={null} />);
    expect(screen.queryByText(/频谱平坦度/)).toBeNull();
  });
});
