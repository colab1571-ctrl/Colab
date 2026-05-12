import { useQuery } from "@tanstack/react-query";
import type { HelloResponse } from "@colab/api-types/hello";
import { helloClient } from "../client";

export const helloKeys = {
  all: ["hello"] as const,
  hello: () => [...helloKeys.all, "hello"] as const,
};

export function useHelloQuery() {
  return useQuery({
    queryKey: helloKeys.hello(),
    queryFn: () => helloClient.hello(),
    retry: false,
    staleTime: 10_000,
  });
}
