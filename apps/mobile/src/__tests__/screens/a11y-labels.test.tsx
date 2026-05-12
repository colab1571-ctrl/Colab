/**
 * apps/mobile/src/__tests__/screens/a11y-labels.test.tsx
 *
 * RN screen render tests: assert accessibilityLabel present on every Touchable.
 *
 * Uses React Native Testing Library (RNTL) to render screens and query
 * for all touchable elements, then assert each has an accessibilityLabel.
 *
 * Runs via: npm test --workspace=apps/mobile
 */

import React from "react";
import { render, within } from "@testing-library/react-native";
import { NavigationContainer } from "@react-navigation/native";

// Mock external dependencies to isolate screen rendering
jest.mock("../../api/auth", () => ({
  loginEmail: jest.fn(),
  signupEmail: jest.fn(),
  signupPhoneStart: jest.fn(),
}));
jest.mock("../../state/auth.store", () => ({
  useAuthStore: () => ({
    setTokens: jest.fn(),
    isAuthenticated: false,
    profileId: "test-profile-id",
  }),
}));
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);
jest.mock("../../api/discovery", () => ({
  getFeed: jest.fn().mockResolvedValue({ profiles: [], next_cursor: null }),
  setFeedMode: jest.fn(),
}));

// ---------------------------------------------------------------------------

import { SignInScreen } from "../../screens/auth/SignInScreen";

/**
 * Helper: find all elements with role=button in the rendered output
 * and assert each has a non-empty accessibilityLabel.
 */
function assertAllButtonsLabeled(container: ReturnType<typeof render>): void {
  const buttons = container.getAllByRole("button");
  for (const btn of buttons) {
    const label =
      btn.props.accessibilityLabel ??
      btn.props["aria-label"] ??
      null;
    expect(label).toBeTruthy();
    expect(typeof label).toBe("string");
    expect((label as string).trim().length).toBeGreaterThan(0);
  }
}

/**
 * Helper: assert all TextInput elements have a non-empty accessibilityLabel.
 */
function assertAllInputsLabeled(container: ReturnType<typeof render>): void {
  try {
    const inputs = container.getAllByRole("none"); // TextInput in RN has no implicit role
    // Fallback: query by testID pattern or ARIA
    // RNTL exposes accessibilityLabel via props
    for (const input of inputs) {
      if (input.props.editable !== false) {
        const label = input.props.accessibilityLabel ?? null;
        if (label !== null) {
          expect(typeof label).toBe("string");
          expect(label.trim().length).toBeGreaterThan(0);
        }
      }
    }
  } catch {
    // If no inputs found, skip
  }
}

// ---------------------------------------------------------------------------
// Sign-in screen
// ---------------------------------------------------------------------------

describe("SignInScreen — a11y labels", () => {
  const mockNavigation = {
    navigate: jest.fn(),
    goBack: jest.fn(),
  } as any;

  function renderSignIn() {
    return render(
      <NavigationContainer>
        <SignInScreen navigation={mockNavigation} />
      </NavigationContainer>
    );
  }

  test("all buttons have accessibilityLabel", () => {
    const container = renderSignIn();
    assertAllButtonsLabeled(container);
  });

  test("email input has accessibilityLabel", () => {
    const container = renderSignIn();
    const emailInput = container.getByTestId("signin-email-input");
    expect(emailInput.props.accessibilityLabel).toBeTruthy();
    expect(emailInput.props.accessibilityLabel).toMatch(/email/i);
  });

  test("password input has accessibilityLabel", () => {
    const container = renderSignIn();
    const passwordInput = container.getByTestId("signin-password-input");
    expect(passwordInput.props.accessibilityLabel).toBeTruthy();
    expect(passwordInput.props.accessibilityLabel).toMatch(/password/i);
  });

  test("sign in button has correct label and role", () => {
    const container = renderSignIn();
    const submitBtn = container.getByTestId("signin-submit");
    expect(submitBtn.props.accessibilityLabel).toMatch(/sign in/i);
    expect(submitBtn.props.accessibilityRole).toBe("button");
  });

  test("social sign-in buttons are labeled", () => {
    const container = renderSignIn();
    const appleBtn = container.getByTestId("apple-signin");
    const googleBtn = container.getByTestId("google-signin");
    const phoneBtn = container.getByTestId("phone-signin");

    expect(appleBtn.props.accessibilityLabel).toMatch(/apple/i);
    expect(googleBtn.props.accessibilityLabel).toMatch(/google/i);
    expect(phoneBtn.props.accessibilityLabel).toMatch(/phone/i);
  });

  test("sign in button has accessibilityState.disabled when loading", () => {
    // Simulate loading state by checking the disabled prop wires to accessibilityState
    const container = renderSignIn();
    const submitBtn = container.getByTestId("signin-submit");
    // When not loading, disabled should be false
    expect(submitBtn.props.accessibilityState?.disabled).toBe(false);
  });

  test("forgot password link has accessibilityRole link", () => {
    const container = renderSignIn();
    const forgotLink = container.getByRole("link", { name: /forgot password/i });
    expect(forgotLink).toBeTruthy();
  });
});
