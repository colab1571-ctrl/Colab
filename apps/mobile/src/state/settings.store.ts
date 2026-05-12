import { create } from "zustand";

type Theme = "light" | "dark" | "system";

interface SettingsState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  notificationsEnabled: boolean;
  setNotificationsEnabled: (v: boolean) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  theme: "system",
  setTheme: (theme) => set({ theme }),
  notificationsEnabled: true,
  setNotificationsEnabled: (v) => set({ notificationsEnabled: v }),
}));
