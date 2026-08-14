"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  /** Render your own fallback. `reset` clears the error and re-renders children. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /**
   * Clearing the error when one of these changes — typically the pathname.
   *
   * Without it a boundary that caught an error on one route stays broken after
   * navigating away, because nothing else ever resets its state.
   */
  resetKeys?: readonly unknown[];
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  error: Error | null;
}

/**
 * Last-resort net for exceptions thrown while rendering.
 *
 * This catches *programmer* errors — a component that reads a property of
 * undefined, a bad assumption about a shape. It deliberately does not, and
 * cannot, handle API failures: React only catches what is thrown during render,
 * and a rejected fetch settles outside it. Those are data, and `ErrorState`
 * renders them in place without unmounting anything.
 *
 * A class is required. There is still no hook equivalent of
 * `getDerivedStateFromError`.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  componentDidUpdate(prevProps: Props) {
    if (!this.state.error) return;
    if (!keysChanged(prevProps.resetKeys, this.props.resetKeys)) return;
    this.reset();
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <Alert variant="destructive">
        <AlertTitle>This section failed to render</AlertTitle>
        <AlertDescription>
          {/*
            The message is shown because this is a bug, and a bug the user can
            quote is a bug that gets fixed. It is not server output — it was
            thrown by this app's own code.
          */}
          {error.message || "An unexpected rendering error occurred."}
        </AlertDescription>
        <AlertAction>
          <Button size="sm" variant="outline" onClick={this.reset}>
            Try again
          </Button>
        </AlertAction>
      </Alert>
    );
  }
}

function keysChanged(prev: readonly unknown[] = [], next: readonly unknown[] = []) {
  if (prev.length !== next.length) return true;
  return prev.some((key, index) => !Object.is(key, next[index]));
}
