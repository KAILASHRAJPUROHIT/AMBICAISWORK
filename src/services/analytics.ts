/**
 * Lightweight analytics service for 3D/AR events.
 * Logs to console in dev; swap for a real provider (Mixpanel, Amplitude, etc.) in production.
 */

type AnalyticsEvent =
  | '3d_view_started'
  | '3d_view_loaded'
  | '3d_view_failed'
  | 'hotspot_opened'
  | 'variant_changed'
  | 'purity_changed'
  | 'set_created'
  | 'set_item_added'
  | 'set_item_removed'
  | 'enquiry_started'
  | 'enquiry_completed'
  | 'ar_session_started'
  | 'ar_session_ended'
  | 'ar_tracking_lost';

type EventPayload = Record<string, string | number | boolean | null | undefined>;

class Analytics {
  private enabled: boolean;

  constructor() {
    this.enabled = __DEV__;
  }

  track(event: AnalyticsEvent, payload?: EventPayload) {
    if (!this.enabled) return;
    const ts = new Date().toISOString();
    console.log(`[Analytics] ${ts} ${event}`, payload ?? '');
  }

  setEnabled(enabled: boolean) {
    this.enabled = enabled;
  }
}

export const analytics = new Analytics();
