import type { LinkingOptions } from "@react-navigation/native";
import { Linking } from "react-native";
import type { RootStackParamList } from "./RootNavigator";

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ["colab://", "https://app.colab.app"],
  config: {
    screens: {
      Auth: {
        screens: {
          Welcome: "",
          SignIn: "sign-in",
          SignUp: "sign-up",
          Verify: "verify",
        },
      },
      Main: {
        screens: {
          Home: "home",
          Discover: "discover",
          Chats: "chats",
          Me: "me",
        },
      },
    },
  },
  async getInitialURL() {
    const url = await Linking.getInitialURL();
    return url;
  },
  subscribe(listener) {
    const sub = Linking.addEventListener("url", ({ url }) => listener(url));
    return () => sub.remove();
  },
};
