import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import "./toast.css";

const ToastContext = createContext(null);
const SYSTEM_MESSAGES_KEY = "etl.systemMessages";

export function useToast() {
  return useContext(ToastContext);
}

function loadSystemMessages() {
  try {
    const raw = sessionStorage.getItem(SYSTEM_MESSAGES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function ToastItem({ id, message, type, onDismiss }) {
  const [out, setOut] = useState(false);
  const timerRef = useRef(null);
  const outRef   = useRef(false);

  function dismiss() {
    if (outRef.current) return;
    outRef.current = true;
    setOut(true);
    setTimeout(() => onDismiss(id), 260);
  }

  function stopTimer() {
    clearTimeout(timerRef.current);
  }

  function startTimer() {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(dismiss, 10000);
  }

  useEffect(() => {
    startTimer();
    return () => clearTimeout(timerRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className={`toast-item toast-item--${type}${out ? " toast-item--out" : ""}`}
      onMouseEnter={stopTimer}
      onMouseLeave={startTimer}
    >
      {message}
    </div>
  );
}

function ToastContainer({ toasts, onDismiss }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || toasts.length === 0) return;
    const raf = requestAnimationFrame(() => {
      if (!containerRef.current) return;
      const { bottom } = containerRef.current.getBoundingClientRect();
      if (bottom > window.innerHeight) {
        onDismiss(toasts[0].id);
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [toasts, onDismiss]);

  return (
    <div className="toast-container" ref={containerRef}>
      {toasts.map(t => (
        <ToastItem key={t.id} id={t.id} message={t.message} type={t.type} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [systemMessages, setSystemMessages] = useState(loadSystemMessages);

  useEffect(() => {
    try {
      sessionStorage.setItem(SYSTEM_MESSAGES_KEY, JSON.stringify(systemMessages));
    } catch {
      // sessionStorage unavailable (e.g. private mode) — persistence best-effort only
    }
  }, [systemMessages]);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const notify = useCallback((message, type = "system") => {
    setToasts(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, message, type }]);
    if (type === "system") {
      setSystemMessages(prev => [
        { id: `${Date.now()}-${Math.random()}`, text: message, ts: Date.now() },
        ...prev,
      ]);
    }
  }, []);

  const notifySystem     = useCallback((message) => notify(message, "system"), [notify]);
  const notifyValidation = useCallback((message) => notify(message, "validation"), [notify]);
  const notifySuccess    = useCallback((message) => notify(message, "success"), [notify]);

  const addToast = useCallback((message) => {
    setToasts(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, message, type: "neutral" }]);
  }, []);

  const removeSystemMessage = useCallback((id) => {
    setSystemMessages(prev => prev.filter(m => m.id !== id));
  }, []);

  const clearSystemMessages = useCallback(() => {
    setSystemMessages([]);
  }, []);

  return (
    <ToastContext.Provider value={{
      addToast,
      notify,
      notifySystem,
      notifyValidation,
      notifySuccess,
      systemMessages,
      removeSystemMessage,
      clearSystemMessages,
    }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  );
}
