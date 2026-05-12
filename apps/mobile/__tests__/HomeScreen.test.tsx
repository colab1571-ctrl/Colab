/**
 * Smoke test for HomeScreen — verifies it renders without crashing.
 */

import React from "react";
import { render } from "@testing-library/react-native";
import { HomeScreen } from "../src/screens/home/HomeScreen";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

jest.mock("../src/api/client", () => ({
  helloClient: { hello: jest.fn().mockResolvedValue({ msg: "Hello, Colab", env: "test", request_id: "test-id", secret_present: false }) },
  queryClient: new QueryClient(),
  gatewayClient: {},
}));

const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

test("HomeScreen renders without crashing", () => {
  const { getByText } = render(
    <QueryClientProvider client={testQueryClient}>
      <HomeScreen />
    </QueryClientProvider>
  );
  expect(getByText("Colab")).toBeTruthy();
});
