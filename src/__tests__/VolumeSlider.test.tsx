import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { VolumeSlider } from '../components/repair/VolumeSlider';

describe('VolumeSlider', () => {
  it('should render with default volume', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={0} onChange={onChange} />);
    
    expect(screen.getByText(/输出音量/i)).toBeTruthy();
    expect(screen.getByText('+0.0 dB')).toBeTruthy();
  });

  it('should render with positive volume', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={3.5} onChange={onChange} />);
    
    expect(screen.getByText('+3.5 dB')).toBeTruthy();
  });

  it('should render with negative volume', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={-6} onChange={onChange} />);
    
    expect(screen.getByText('-6.0 dB')).toBeTruthy();
  });

  it('should call onChange when slider value changes', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={0} onChange={onChange} />);
    
    const slider = screen.getByRole('slider') as HTMLInputElement;
    fireEvent.change(slider, { target: { value: '-3' } });
    
    expect(onChange).toHaveBeenCalledWith(-3);
  });

  it('should have correct min, max, and step attributes', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={0} onChange={onChange} />);
    
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.min).toBe('-12');
    expect(slider.max).toBe('6');
    expect(slider.step).toBe('0.5');
  });

  it('should be disabled when disabled prop is true', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={0} onChange={onChange} disabled />);
    
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.disabled).toBe(true);
  });

  it('should not be disabled by default', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={0} onChange={onChange} />);
    
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.disabled).toBe(false);
  });

  it('should display scale markers', () => {
    const onChange = vi.fn();
    render(<VolumeSlider outputVolume={0} onChange={onChange} />);
    
    expect(screen.getByText('-12')).toBeTruthy();
    expect(screen.getByText('-6')).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getByText('+6 dB')).toBeTruthy();
  });
});
