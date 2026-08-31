import React, { Component, ErrorInfo, ReactNode } from 'react';
import * as Sentry from '@sentry/react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/primitives';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false };

  public static getDerivedStateFromError(_: Error): State {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    Sentry.captureException(error, { extra: errorInfo });
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-64 flex-col items-center justify-center p-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger mb-4">
                <AlertTriangle className="h-6 w-6" />
            </div>
          <h2 className="text-lg font-semibold text-ink">Application Error</h2>
          <p className="mt-2 text-sm text-muted max-w-sm">
            Something went wrong. Our team has been notified.
          </p>
          <Button className="mt-4" onClick={() => window.location.reload()}>
            Refresh Dashboard
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
