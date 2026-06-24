import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import "./toast.css";

const ToastContext = createContext(null);

export function useToast() {
  return useContext(ToastContext);
}

function ToastItem({ id, message, onDismiss }) {
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
    timerRef.current = setTimeout(dismiss, 2000);
  }

  useEffect(() => {
    startTimer();
    return () => clearTimeout(timerRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className={`toast-item${out ? " toast-item--out" : ""}`}
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
        <ToastItem key={t.id} id={t.id} message={t.message} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message) => {
    setToasts(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, message }]);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  );
}
