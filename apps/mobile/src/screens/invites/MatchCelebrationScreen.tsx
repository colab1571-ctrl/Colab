/**
 * MatchCelebrationScreen — "Match!" notification celebration.
 *
 * Displayed when:
 *   - User accepts an invite and the other party had already accepted (mutual accept)
 *   - OR user receives a push notification for match.created event
 *
 * FR-B-13: Mutual accept → "Match!" notification → §007 chat room opens.
 */

import React, { useCallback, useEffect, useRef } from "react";
import {
  Animated,
  Easing,
  Image,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";

type MatchParams = {
  profileId?: string;
  displayName?: string | null;
  avatarUrl?: string | null;
};

type Props = {
  navigation: NativeStackNavigationProp<any>;
  route: RouteProp<{ MatchCelebration: MatchParams }, "MatchCelebration">;
};

export function MatchCelebrationScreen({ navigation, route }: Props): React.ReactElement {
  const { profileId, displayName, avatarUrl } = route.params ?? {};

  // Celebration animations
  const scaleAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const confettiAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Sequence: fade in → scale pop → confetti
    Animated.sequence([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }),
      Animated.spring(scaleAnim, {
        toValue: 1,
        damping: 8,
        stiffness: 100,
        useNativeDriver: true,
      }),
      Animated.timing(confettiAnim, {
        toValue: 1,
        duration: 800,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start();
  }, [fadeAnim, scaleAnim, confettiAnim]);

  const handleOpenChat = useCallback(() => {
    // Navigate to chat with matched profile
    navigation.replace("Chat", {
      profileId,
      displayName,
    });
  }, [navigation, profileId, displayName]);

  const handleDismiss = useCallback(() => {
    navigation.goBack();
  }, [navigation]);

  return (
    <View className="flex-1 bg-brand-primary items-center justify-center px-8">
      {/* Confetti emoji decoration */}
      <Animated.Text
        style={{
          opacity: confettiAnim,
          transform: [
            {
              translateY: confettiAnim.interpolate({
                inputRange: [0, 1],
                outputRange: [-20, 0],
              }),
            },
          ],
        }}
        className="text-5xl absolute top-20"
      >
        🎉
      </Animated.Text>

      <Animated.View
        style={{
          opacity: fadeAnim,
          transform: [{ scale: scaleAnim }],
          alignItems: "center",
        }}
      >
        {/* Match! header */}
        <Text className="text-white text-5xl font-black mb-2 tracking-wide">
          Match!
        </Text>
        <Text className="text-white/80 text-lg text-center mb-8">
          You and {displayName ?? "this creator"} both vibed!{"\n"}
          Start collaborating now.
        </Text>

        {/* Matched profile avatar */}
        {avatarUrl ? (
          <Image
            source={{ uri: avatarUrl }}
            className="w-24 h-24 rounded-full border-4 border-white mb-6"
          />
        ) : (
          <View className="w-24 h-24 rounded-full border-4 border-white bg-white/20 items-center justify-center mb-6">
            <Text className="text-white text-3xl font-bold">
              {displayName?.[0]?.toUpperCase() ?? "?"}
            </Text>
          </View>
        )}

        {displayName && (
          <Text className="text-white text-xl font-bold mb-8">{displayName}</Text>
        )}

        {/* CTA */}
        <TouchableOpacity
          className="bg-white py-4 px-10 rounded-2xl mb-4 w-full items-center"
          onPress={handleOpenChat}
          testID="open-chat-btn"
        >
          <Text className="text-brand-primary font-bold text-base">Start Chatting</Text>
        </TouchableOpacity>

        <TouchableOpacity
          className="py-3 px-6"
          onPress={handleDismiss}
          testID="dismiss-btn"
        >
          <Text className="text-white/70 text-sm">Maybe later</Text>
        </TouchableOpacity>
      </Animated.View>

      {/* Bottom confetti */}
      <Animated.Text
        style={{ opacity: confettiAnim }}
        className="text-5xl absolute bottom-20"
      >
        ✨
      </Animated.Text>
    </View>
  );
}
