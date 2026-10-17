// On the web (react-native-web), a Pressable's style function also gets `hovered` and
// `focused`, which power the hover effects on a computer. React Native's own types
// don't list them, so add them here. On a phone they're simply always undefined.
import "react-native";

declare module "react-native" {
  interface PressableStateCallbackType {
    readonly hovered?: boolean;
    readonly focused?: boolean;
  }
}
