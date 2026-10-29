'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, stream } from './api';

/** Load a GET endpoint. `reload()` fetches again; a failed request leaves `error` set. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null });
  const reload = useCallback(async () => {
    try {
      setState({ data: await api(path), error: null });
    } catch (error) {
      setState((s) => ({ ...s, error }));
    }
  }, [path]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { ...state, reload };
}

/** Follow a server-sent event stream while `enabled`; `onEvent` always sees the latest closure. */
export function useEventStream(path, enabled, onEvent) {
  const latest = useRef(onEvent);
  latest.current = onEvent;
  useEffect(() => {
    if (!enabled) return undefined;
    const stop = new AbortController();
    stream(path, (name, data) => latest.current(name, data), stop.signal).catch(() => {});
    return () => stop.abort();
  }, [path, enabled]);
}

/** A transient message at the foot of the page. */
export function toast(message, tone = 'ok') {
  const t = document.createElement('div');
  t.className = `toast ${tone}`;
  t.setAttribute('role', 'status');
  t.textContent = message;
  document.body.append(t);
  setTimeout(() => t.remove(), 5200);
}
