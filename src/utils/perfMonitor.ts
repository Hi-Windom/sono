export interface PerfMetric {
  name: string;
  durationMs: number;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface PerfSummary {
  pageLoad: {
    fp?: number;
    fcp?: number;
    lcp?: number;
    ttfb?: number;
    domContentLoaded?: number;
    loadEvent?: number;
  };
  audioDecoding: {
    count: number;
    avgMs: number;
    minMs: number;
    maxMs: number;
    recent: PerfMetric[];
  };
  apiCalls: {
    count: number;
    avgMs: number;
    minMs: number;
    maxMs: number;
    byEndpoint: Record<string, { count: number; avgMs: number }>;
    recent: PerfMetric[];
  };
  repairFlow: {
    count: number;
    avgMs: number;
    minMs: number;
    maxMs: number;
    byStage: Record<string, number>;
    recent: PerfMetric[];
  };
}

class PerfMonitor {
  private metrics: PerfMetric[] = [];
  private maxMetrics = 100;
  private pageLoadMetrics: Record<string, number> = {};
  private repairStages: Record<string, number> = {};
  private repairStartTime = 0;

  constructor() {
    this.initPageLoadTracking();
  }

  private initPageLoadTracking() {
    if (typeof window === 'undefined') return;

    if (document.readyState === 'complete') {
      this.capturePageLoadMetrics();
    } else {
      window.addEventListener('load', () => {
        setTimeout(() => this.capturePageLoadMetrics(), 0);
      });
    }

    if ('PerformanceObserver' in window) {
      try {
        const fcpObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.name === 'first-contentful-paint') {
              this.pageLoadMetrics.fcp = entry.startTime;
              console.log(`[perf] FCP: ${entry.startTime.toFixed(1)}ms`);
            }
          }
        });
        fcpObserver.observe({ type: 'paint', buffered: true });
      } catch (e) {
        console.warn('[perf] FCP observer not supported');
      }

      try {
        const lcpObserver = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const lastEntry = entries[entries.length - 1];
          if (lastEntry) {
            this.pageLoadMetrics.lcp = lastEntry.startTime;
            console.log(`[perf] LCP: ${lastEntry.startTime.toFixed(1)}ms`);
          }
        });
        lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
      } catch (e) {
        console.warn('[perf] LCP observer not supported');
      }
    }
  }

  private capturePageLoadMetrics() {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    if (nav) {
      this.pageLoadMetrics.ttfb = nav.responseStart - nav.requestStart;
      this.pageLoadMetrics.domContentLoaded = nav.domContentLoadedEventEnd;
      this.pageLoadMetrics.loadEvent = nav.loadEventEnd;
      console.log(`[perf] Page load: TTFB=${this.pageLoadMetrics.ttfb?.toFixed(1)}ms, DCL=${this.pageLoadMetrics.domContentLoaded?.toFixed(1)}ms, Load=${this.pageLoadMetrics.loadEvent?.toFixed(1)}ms`);
    }

    const paintEntries = performance.getEntriesByType('paint');
    for (const entry of paintEntries) {
      if (entry.name === 'first-paint') {
        this.pageLoadMetrics.fp = entry.startTime;
        console.log(`[perf] FP: ${entry.startTime.toFixed(1)}ms`);
      }
    }
  }

  startTimer(name: string, metadata?: Record<string, unknown>): () => number {
    const startTime = performance.now();
    return () => {
      const duration = performance.now() - startTime;
      this.recordMetric(name, duration, metadata);
      return duration;
    };
  }

  recordMetric(name: string, durationMs: number, metadata?: Record<string, unknown>) {
    const metric: PerfMetric = {
      name,
      durationMs,
      timestamp: Date.now(),
      metadata,
    };
    this.metrics.push(metric);
    if (this.metrics.length > this.maxMetrics) {
      this.metrics.shift();
    }
    console.debug(`[perf] ${name}: ${durationMs.toFixed(2)}ms`);
  }

  startRepairFlow() {
    this.repairStartTime = performance.now();
    this.repairStages = {};
  }

  recordRepairStage(stage: string, durationMs: number) {
    this.repairStages[stage] = (this.repairStages[stage] || 0) + durationMs;
  }

  endRepairFlow() {
    const total = performance.now() - this.repairStartTime;
    this.recordMetric('repair_flow_total', total, { stages: { ...this.repairStages } });
    return total;
  }

  recordApiCall(endpoint: string, durationMs: number, success = true) {
    this.recordMetric(`api_${endpoint}`, durationMs, { endpoint, success });
  }

  recordAudioDecoding(durationMs: number, fileSize: number, format: string) {
    this.recordMetric('audio_decode', durationMs, { fileSize, format });
  }

  getSummary(): PerfSummary {
    const filterByName = (prefix: string) => this.metrics.filter(m => m.name.startsWith(prefix));

    const calcStats = (items: PerfMetric[]) => {
      if (items.length === 0) return { count: 0, avgMs: 0, minMs: 0, maxMs: 0 };
      const durations = items.map(m => m.durationMs);
      return {
        count: items.length,
        avgMs: durations.reduce((a, b) => a + b, 0) / durations.length,
        minMs: Math.min(...durations),
        maxMs: Math.max(...durations),
      };
    };

    const apiMetrics = filterByName('api_');
    const audioMetrics = filterByName('audio_decode');
    const repairMetrics = filterByName('repair_flow_');

    const byEndpoint: Record<string, { count: number; avgMs: number }> = {};
    const endpointMap = new Map<string, number[]>();
    for (const m of apiMetrics) {
      const ep = m.metadata?.endpoint as string || m.name;
      if (!endpointMap.has(ep)) {
        endpointMap.set(ep, []);
      }
      endpointMap.get(ep)!.push(m.durationMs);
    }
    for (const [ep, durations] of endpointMap) {
      byEndpoint[ep] = {
        count: durations.length,
        avgMs: durations.reduce((a, b) => a + b, 0) / durations.length,
      };
    }

    return {
      pageLoad: {
        fp: this.pageLoadMetrics.fp,
        fcp: this.pageLoadMetrics.fcp,
        lcp: this.pageLoadMetrics.lcp,
        ttfb: this.pageLoadMetrics.ttfb,
        domContentLoaded: this.pageLoadMetrics.domContentLoaded,
        loadEvent: this.pageLoadMetrics.loadEvent,
      },
      audioDecoding: {
        ...calcStats(audioMetrics),
        recent: audioMetrics.slice(-10),
      },
      apiCalls: {
        ...calcStats(apiMetrics),
        byEndpoint,
        recent: apiMetrics.slice(-10),
      },
      repairFlow: {
        ...calcStats(repairMetrics),
        byStage: { ...this.repairStages },
        recent: repairMetrics.slice(-10),
      },
    };
  }

  reset() {
    this.metrics = [];
    this.repairStages = {};
  }
}

export const perfMonitor = new PerfMonitor();

export function withPerf<T>(name: string, fn: () => T | Promise<T>, metadata?: Record<string, unknown>): Promise<T> {
  const endTimer = perfMonitor.startTimer(name, metadata);
  return Promise.resolve(fn()).then(result => {
    endTimer();
    return result;
  });
}
