import { create } from "zustand";

interface FlagsState {
  aiMockupsEnabled: boolean;
  inChatAiEnabled: boolean;
  adsEnabled: boolean;
  marketingNotifications: boolean;
  regionAllowlist: string[];

  setFlags: (flags: Partial<Omit<FlagsState, "setFlags">>) => void;
}

export const useFlagsStore = create<FlagsState>((set) => ({
  aiMockupsEnabled: true,
  inChatAiEnabled: true,
  adsEnabled: false,
  marketingNotifications: false,
  regionAllowlist: ["US", "CA", "AU", "NZ", "IN"],

  setFlags: (flags) => set(flags),
}));
