## Architecture

### Frontend
- **Framework**: React 18 + TypeScript + Vite
- **Styling**: Tailwind CSS
- **Audio Playback**: Web Audio API (AudioContext, AudioBufferSourceNode, AnalyserNode)
- **State Management**: React useState/useCallback/useRef (no external state library)
- **Core Hook**: `useAudioProcessor` — single hook managing all audio processing state and operations
- **Backend Communication**: REST API + WebSocket (with HTTP polling fallback)

### Backend
- **Framework**: FastAPI (Python 3.10+)
- **Audio Processing**: NumPy + SciPy (custom `dsp_utils.py`, librosa removed except for training)
- **Audio Loading**: miniaudio only (no librosa, no pydub)
- **Database**: SQLite
- **Task Management**: Async task queue with WebSocket progress reporting
- **Type Checking**: pyright strict mode

### Key Design Decisions
- **No browser-side repair**: All audio repair runs on the backend. Frontend handles playback, visualization, and UI only.
- **Streaming spectral processing**: `dsp_utils.py::streaming_spectral_process` processes audio in 10s chunks with overlap-add, keeping STFT memory fixed at ~15MB regardless of audio length.
- **Memory optimization**: 4-layer system (corrected estimation, float32 auto-conversion, streaming processing, in-place operations) enables 60min audio @ 4GB RAM.
- **Smart caching**: Upload-level dedup by file hash, repair result cache by file+algorithm+params triple match.
- **Algorithm versioning**: Multiple repair algorithm versions (v1.0~v2.4a) with lightweight variants (a-suffix) for memory-constrained environments.

### Route Structure
| Route | Page | Purpose |
|-------|------|---------|
| `/` | LandingPage | Feature overview, recent updates, stats |
| `/repair` | RepairPage | Full audio repair workflow |
| `/home` | Home | Alternative repair interface with player |
| `/detect` | DetectPage | Independent AI detection with A/B comparison |
| `/compare` | ComparePage | Server-side audio A/B comparison |
| `/profile-manager` | ProfileManagerPage | Save/manage repair parameter presets |
| `/quality-tests` | QualityTestPage | Automated repair quality test suite |
| `/cache-manager` | CacheManagerPage | Backend/frontend cache management |
| `/training-upload` | TrainingUploadPage | Training data upload |

### Component Architecture
```
src/
├── components/
│   ├── AIRepairPanel.tsx      # Repair parameter controls
│   ├── AIDetectionCard.tsx    # AI detection result display
│   ├── AudioPlayer.tsx        # Play/pause/mode switch controls
│   ├── DownloadModal.tsx      # Export/download dialog
│   ├── RepairCacheModal.tsx   # Cache hit prompt
│   ├── Header.tsx             # Navigation header
│   └── SpectrumVisualizer.tsx # Real-time spectrum display
├── hooks/
│   └── useAudioProcessor.ts   # Core audio processing hook (~900 lines)
├── pages/
│   ├── LandingPage.tsx        # Landing page
│   ├── RepairPage.tsx         # Repair page
│   ├── Home.tsx               # Home page with player
│   ├── DetectPage.tsx         # AI detection page
│   └── ComparePage.tsx        # A/B comparison page
├── services/
│   └── api.ts                 # REST API + WebSocket client
└── utils/
    ├── advancedAudioProcessing.ts  # AIRepairParams types, detectAudioIssues
    ├── settingsStorage.ts          # Persistent settings
    └── renderCache.ts              # Render cache management
```

### Data Flow
```
User uploads audio
  → useAudioProcessor.loadAudioFile()
    → miniaudio decode (backend) → AudioBuffer (frontend)
  → User clicks "Apply Repair"
    → useAudioProcessor.applySettings()
      → POST /api/v1/repair (upload + start task)
      → WebSocket progress updates
      → Backend repair (numpy+scipy dsp_utils)
      → GET /api/v1/preview/{task_id} (load repaired audio)
      → Auto-render: POST /api/v1/render (generate download)
  → User downloads via DownloadModal
```
