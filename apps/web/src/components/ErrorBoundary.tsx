import { AlertTriangle } from 'lucide-react';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled application error', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex min-h-dvh items-center justify-center bg-ink-50 p-6 dark:bg-ink-950">
        <div className="panel w-full max-w-md p-6 text-center">
          <span className="mx-auto mb-4 inline-flex rounded-xl bg-red-100 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">
            <AlertTriangle className="size-6" aria-hidden="true" />
          </span>
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="mt-2 text-sm leading-6 text-ink-500 dark:text-ink-300">
            {this.state.error.message || 'An unexpected error interrupted the app.'} Reloading
            usually fixes this.
          </p>
          <button type="button" className="button-primary mt-5" onClick={() => location.reload()}>
            Reload app
          </button>
        </div>
      </div>
    );
  }
}
