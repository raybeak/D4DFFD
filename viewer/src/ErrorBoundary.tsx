import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  name: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Contains render errors to one part of the UI and offers a retry. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[${this.props.name}] render error`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-box" role="alert">
          <strong>{this.props.name} crashed:</strong> {this.state.error.message}
          <button type="button" onClick={() => this.setState({ error: null })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
