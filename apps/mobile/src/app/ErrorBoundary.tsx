import React from "react";
import { Text, TouchableOpacity, View } from "react-native";

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error): void {
    // Sentry captures automatically via SentryReactNativeIntegration
    console.error("ErrorBoundary caught:", error);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <View className="flex-1 items-center justify-center bg-white px-6">
          <Text className="text-xl font-semibold text-neutral-900 mb-2">
            Something went wrong
          </Text>
          <Text className="text-sm text-neutral-500 text-center mb-6">
            {this.state.error?.message ?? "An unexpected error occurred."}
          </Text>
          <TouchableOpacity
            onPress={this.handleReset}
            className="bg-brand-primary px-6 py-3 rounded-lg"
          >
            <Text className="text-white font-medium">Try again</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}
