import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

/**
 * App-wide error boundary. A render throw anywhere below this would otherwise
 * blank the page; instead we catch it and show a friendly fallback with a
 * Reload action. Class component is required — hooks can't catch render errors.
 */
export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Uncaught render error:", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-bg px-6 text-center">
        <h1 className="text-xl font-semibold text-fg">Something went wrong</h1>
        <p className="mt-2 max-w-md text-sm text-cold">
          An unexpected error interrupted the page. Reloading usually clears it.
        </p>
        <button
          type="button"
          onClick={() => location.reload()}
          className="mt-6 inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg transition hover:opacity-90"
        >
          Reload
        </button>
      </div>
    );
  }
}
