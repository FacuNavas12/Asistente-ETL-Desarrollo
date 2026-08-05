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
  const [dragPos, setDragPos] = useState(null);
  const [dragging, setDragging] = useState(false);
  const timerRef    = useRef(null);
  const outRef      = useRef(false);
  const dragOffset  = useRef({ x: 0, y: 0 });
  const dragWidth   = useRef(null);

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
    timerRef.current = setTimeout(dismiss, 2000);
  }

  useEffect(() => {
    startTimer();
    return () => clearTimeout(timerRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handlePointerDown(e) {
    if (e.target.closest(".toast-item__close")) return;
    const rect = e.currentTarget.getBoundingClientRect();
    dragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    dragWidth.current = rect.width;
    setDragPos({ left: rect.left, top: rect.top });
    setDragging(true);
    stopTimer();
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function handlePointerMove(e) {
    if (!dragging) return;
    setDragPos({
      left: e.clientX - dragOffset.current.x,
      top: e.clientY - dragOffset.current.y,
    });
  }

  function handlePointerUp() {
    if (!dragging) return;
    setDragging(false);
    startTimer();
  }

  const style = dragPos
    ? { position: "fixed", left: dragPos.left, top: dragPos.top, width: dragWidth.current }
    : undefined;

  return (
    <div
      className={`toast-item toast-item--${type}${out ? " toast-item--out" : ""}${dragging ? " toast-item--dragging" : ""}`}
      style={style}
      onMouseEnter={stopTimer}
      onMouseLeave={() => { if (!dragging) startTimer(); }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <span className="toast-item__text">{message}</span>
      <button
        type="button"
        className="toast-item__close"
        aria-label="Cerrar"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={dismiss}
      >
        →
      </button>
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
